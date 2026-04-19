#!/usr/bin/env python3
"""随身WiFi 管理后台 — STA 模式下监听 :80"""
import subprocess, json, os, html, re, urllib.parse, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

PORT = 80
BARK_CONF = "/etc/bark.conf"
SMS_LOG = "/var/log/sms-forward.log"

# ─── 数据获取 ──────────────────────────────────────────────────────────────────

def sh(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

def get_status():
    ip = sh("ip -4 -br addr show wlan0 | awk '{print $3}' | cut -d/ -f1")
    uptime = sh("uptime -p")
    state  = sh("mmcli -m 0 2>/dev/null | awk '/\\| +state:/{gsub(/\\033\\[[0-9;]*m/,\"\"); print $NF; exit}'")
    signal = sh("mmcli -m 0 2>/dev/null | awk '/signal quality/{print $4; exit}'")
    oper   = sh("mmcli -m 0 2>/dev/null | awk '/operator name/{print $4; exit}'")
    ssid   = sh("LANG=C nmcli -t -f active,ssid d wifi | awk -F: '/^yes:/{print $2;exit}'")
    return {"ip": ip, "uptime": uptime, "modem_state": state,
            "signal": signal, "operator": oper, "ssid": ssid}

def get_sms():
    msgs = []
    indices = sh("mmcli -m 0 --messaging-list-sms 2>/dev/null | grep -o 'SMS/[0-9]*' | cut -d/ -f2")
    for idx in indices.splitlines():
        if not idx.strip(): continue
        raw = sh(f"mmcli -s {idx} 2>/dev/null")
        num  = re.search(r'number:\s+(.+)', raw)
        txt  = re.search(r'text:\s+(.+)', raw)
        ts   = re.search(r'timestamp:\s+(.+)', raw)
        msgs.append({
            "from": num.group(1).strip() if num else "?",
            "text": txt.group(1).strip().strip("'\"") if txt else "",
            "time": ts.group(1).strip() if ts else "",
            "idx": idx
        })
    return msgs

def get_forward_log(n=50):
    logs = []
    try:
        lines = open(SMS_LOG).readlines()[-n:]
        for l in reversed(lines):
            parts = l.strip().split("|", 2)
            if len(parts) == 3:
                ts, frm, txt = parts
                try: ts = datetime.fromtimestamp(int(ts)).strftime("%m-%d %H:%M")
                except: pass
                logs.append({"time": ts, "from": frm, "text": txt})
    except FileNotFoundError:
        pass
    return logs

def get_wifi_list():
    sh("nmcli d wifi rescan 2>/dev/null", timeout=10)
    raw = sh("nmcli -t -f SSID,SIGNAL,SECURITY d wifi list")
    nets = {}
    for line in raw.splitlines():
        parts = line.split(":")
        if len(parts) < 3: continue
        ssid = parts[0].strip()
        if not ssid: continue
        try: sig = int(parts[1])
        except: sig = 0
        sec = parts[2].strip()
        if ssid not in nets or nets[ssid]["signal"] < sig:
            nets[ssid] = {"ssid": ssid, "signal": sig, "security": sec}
    return sorted(nets.values(), key=lambda x: -x["signal"])

def get_bark():
    conf = {}
    try:
        for line in open(BARK_CONF):
            m = re.match(r'(\w+)="(.*)"', line.strip())
            if m: conf[m.group(1)] = m.group(2)
    except: pass
    return conf

def save_bark(server, key):
    with open(BARK_CONF, "w") as f:
        f.write(f'BARK_SERVER="{server.rstrip("/")}"\nBARK_KEY="{key}"\n')
    os.chmod(BARK_CONF, 0o600)

def test_bark(server, key):
    url = f"{server.rstrip('/')}/{key}"
    title = urllib.parse.quote("随身WiFi测试")
    body  = urllib.parse.quote("Bark 推送配置正常 ✅")
    r = sh(f'curl -sS --max-time 8 "{url}/{title}/{body}"')
    return r

def modem_reset():
    threading.Thread(target=lambda: (
        sh("mmcli -m 0 --disable", timeout=15),
        __import__('time').sleep(5),
        sh("mmcli -m 0 --enable", timeout=15)
    ), daemon=True).start()

def connect_wifi(ssid, psk):
    # Remove old non-AP profiles
    raw = sh("nmcli -t -f NAME,TYPE c show")
    for line in raw.splitlines():
        name, _, typ = line.partition(":")
        if typ == "802-11-wireless" and name != "suishenwifi":
            sh(f'nmcli c delete "{name}"')
    cmd = f'nmcli c add type wifi ifname wlan0 con-name "{ssid}" ssid "{ssid}" connection.autoconnect yes connection.autoconnect-priority 10'
    if psk:
        cmd += f' wifi-sec.key-mgmt wpa-psk wifi-sec.psk "{psk}"'
    result = sh(cmd)
    # Apply in background (will cause brief disconnect)
    threading.Thread(target=lambda: sh(f'nmcli c up "{ssid}"', timeout=30), daemon=True).start()
    return result

# ─── HTML ──────────────────────────────────────────────────────────────────────

def render_page(content):
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>随身WiFi 管理</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
.topbar{{background:#1e293b;padding:.8rem 1.2rem;display:flex;align-items:center;gap:.8rem;
  border-bottom:1px solid #334155;position:sticky;top:0;z-index:10}}
.topbar h1{{font-size:1rem;font-weight:700;color:#93c5fd}}
.dot{{width:8px;height:8px;border-radius:50%;background:#10b981;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.main{{padding:1rem;max-width:800px;margin:0 auto;display:flex;flex-direction:column;gap:1rem}}
.card{{background:#1e293b;border-radius:12px;overflow:hidden}}
.card-header{{padding:.7rem 1rem;background:#162032;font-size:.8rem;font-weight:600;
  color:#93c5fd;text-transform:uppercase;letter-spacing:.05em;display:flex;justify-content:space-between;align-items:center}}
.card-body{{padding:1rem}}
.stat-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.6rem}}
.stat{{background:#0f172a;border-radius:8px;padding:.7rem;}}
.stat-label{{font-size:.7rem;color:#64748b;margin-bottom:.2rem}}
.stat-value{{font-size:.95rem;font-weight:600;color:#e2e8f0;word-break:break-all}}
.sms-item{{padding:.7rem;border-bottom:1px solid #1e293b;}}
.sms-item:last-child{{border-bottom:0}}
.sms-from{{font-size:.8rem;color:#93c5fd;font-weight:600}}
.sms-time{{font-size:.7rem;color:#475569;float:right}}
.sms-text{{font-size:.9rem;margin-top:.3rem;line-height:1.5;word-break:break-all}}
.log-item{{padding:.5rem .7rem;border-bottom:1px solid #1e293b;font-size:.82rem}}
.log-item:last-child{{border-bottom:0}}
.log-from{{color:#a78bfa;font-weight:600}}
.log-time{{color:#475569;font-size:.72rem}}
.wifi-item{{padding:.6rem .7rem;border-bottom:1px solid #1e293b;display:flex;
  align-items:center;gap:.6rem;cursor:pointer}}
.wifi-item:last-child{{border-bottom:0}}
.wifi-item:hover{{background:#162032}}
.wifi-name{{flex:1;font-size:.9rem}}
.wifi-sig{{font-size:.75rem;color:#64748b}}
.wifi-sec{{font-size:.7rem;color:#f59e0b;background:#f59e0b22;padding:.1rem .4rem;border-radius:4px}}
input,button,select{{border-radius:8px;border:0;font-size:.9rem;outline:0}}
input,select{{background:#0f172a;color:#e2e8f0;border:1px solid #334155;padding:.6rem .8rem;width:100%}}
button{{background:#3b82f6;color:#fff;font-weight:600;cursor:pointer;padding:.6rem 1.2rem}}
button:hover{{background:#2563eb}}
button.sec{{background:#334155}}button.sec:hover{{background:#475569}}
.form-row{{display:flex;gap:.5rem;margin-top:.6rem}}
.form-row input{{flex:1}}
.badge{{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.72rem;font-weight:600}}
.badge-ok{{background:#10b98133;color:#10b981}}
.badge-warn{{background:#f59e0b33;color:#f59e0b}}
.toast{{position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%);
  background:#1e293b;border:1px solid #334155;border-radius:10px;padding:.7rem 1.2rem;
  font-size:.85rem;z-index:99;opacity:0;transition:opacity .3s;pointer-events:none}}
.toast.show{{opacity:1}}
.empty{{color:#475569;font-size:.85rem;padding:.5rem 0;text-align:center}}
</style></head>
<body>
<div class="topbar"><div class="dot"></div><h1>🛰️ 随身WiFi 管理</h1>
  <span id="clock" style="margin-left:auto;font-size:.8rem;color:#64748b"></span></div>
<div class="main">{content}</div>
<div class="toast" id="toast"></div>
<script>
function toast(msg,ok=true){{
  const t=document.getElementById('toast');
  t.textContent=msg; t.style.borderColor=ok?'#10b981':'#ef4444';
  t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),3000);
}}
setInterval(()=>{{
  const d=new Date();
  document.getElementById('clock').textContent=d.toLocaleTimeString('zh-CN');
}},1000);
// Auto-refresh SMS every 5s
let lastSmsCount = {{}};
async function refreshSMS(){{
  try{{
    const r = await fetch('/api/sms'); const data = await r.json();
    const box = document.getElementById('sms-box');
    if(!box) return;
    if(data.length===0){{box.innerHTML='<div class="empty">暂无短信</div>';return;}}
    box.innerHTML = data.map(m=>`
      <div class="sms-item">
        <span class="sms-from">${{m.from}}</span><span class="sms-time">${{m.time}}</span>
        <div class="sms-text">${{m.text}}</div>
      </div>`).join('');
  }}catch(e){{}}
}}
setInterval(refreshSMS, 5000);
// WiFi password modal
function selectWifi(ssid,secured){{
  document.getElementById('wifi-ssid-input').value=ssid;
  document.getElementById('wifi-psk-row').style.display=secured?'flex':'none';
  document.getElementById('wifi-psk-input').value='';
  document.getElementById('wifi-form').style.display='block';
  document.getElementById('wifi-ssid-label').textContent=ssid;
}}
async function connectWifi(){{
  const ssid=document.getElementById('wifi-ssid-input').value;
  const psk=document.getElementById('wifi-psk-input').value;
  toast('正在连接，页面将短暂断开...');
  await fetch('/api/wifi/connect',{{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{ssid,psk}})}});
}}
async function saveBark(){{
  const url=document.getElementById('bark-url').value.trim();
  let server='https://api.day.app',key='';
  const m=url.match(/^(https?:\/\/[^/]+)\/([A-Za-z0-9_\-]+)\/?/);
  if(m){{server=m[1];key=m[2];}}else{{key=url;}}
  const r=await fetch('/api/bark',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{server,key}})}});
  const d=await r.json();
  toast(d.ok?'Bark 配置已保存':'保存失败',d.ok);
}}
async function resetModem(){{
  toast('正在重置蜂窝信号，约 10 秒后刷新页面...');
  await fetch('/api/modem/reset',{{method:'POST'}});
  setTimeout(()=>location.reload(),12000);
}}
async function testBark(){{
  toast('发送测试通知...');
  const r=await fetch('/api/bark/test',{{method:'POST'}});
  const d=await r.json();
  toast(d.ok?'测试通知已发送 ✅':'发送失败，请检查 Key',d.ok);
}}
</script></body></html>"""

def build_dashboard():
    s = get_status()
    sms = get_sms()
    logs = get_forward_log(30)
    bark = get_bark()
    wifi_list = get_wifi_list()

    sig_pct = s.get("signal","")
    sig_badge = f'<span class="badge badge-ok">{sig_pct}%</span>' if sig_pct else '<span class="badge badge-warn">未知</span>'

    # Status card
    status_card = f"""<div class="card">
  <div class="card-header">📊 设备状态</div>
  <div class="card-body">
    <div class="stat-grid">
      <div class="stat"><div class="stat-label">本机 IP</div><div class="stat-value">{s['ip'] or '--'}</div></div>
      <div class="stat"><div class="stat-label">运行时长</div><div class="stat-value">{s['uptime'] or '--'}</div></div>
      <div class="stat"><div class="stat-label">已连 WiFi</div><div class="stat-value">{html.escape(s['ssid'] or '--')}</div></div>
      <div class="stat"><div class="stat-label">蜂窝状态</div><div class="stat-value">{s['modem_state'] or '--'}</div></div>
      <div class="stat" style="display:flex;align-items:flex-end">
        <button onclick="resetModem()" style="width:100%;padding:.5rem;font-size:.8rem;background:#334155">📡 重新搜索信号</button>
      </div>
      <div class="stat"><div class="stat-label">信号强度</div><div class="stat-value">{sig_badge}</div></div>
      <div class="stat"><div class="stat-label">运营商</div><div class="stat-value">{s['operator'] or '--'}</div></div>
    </div>
  </div>
</div>"""

    # SMS inbox
    if sms:
        sms_html = "".join(f"""<div class="sms-item">
  <span class="sms-from">{html.escape(m['from'])}</span>
  <span class="sms-time">{html.escape(m['time'])}</span>
  <div class="sms-text">{html.escape(m['text'])}</div>
</div>""" for m in sms)
    else:
        sms_html = '<div class="empty">暂无短信</div>'

    sms_card = f"""<div class="card">
  <div class="card-header">💬 短信收件箱 <span class="badge badge-ok">{len(sms)}</span></div>
  <div class="card-body" style="padding:0" id="sms-box">{sms_html}</div>
</div>"""

    # Forward log
    if logs:
        log_html = "".join(f"""<div class="log-item">
  <span class="log-from">{html.escape(l['from'])}</span>
  <span class="log-time" style="float:right">{html.escape(l['time'])}</span>
  <div style="margin-top:.2rem;color:#94a3b8">{html.escape(l['text'][:80])}{'…' if len(l['text'])>80 else ''}</div>
</div>""" for l in logs)
    else:
        log_html = '<div class="empty">暂无转发记录</div>'

    log_card = f"""<div class="card">
  <div class="card-header">📤 转发记录 (最近30条)</div>
  <div class="card-body" style="padding:0">{log_html}</div>
</div>"""

    # WiFi management
    wifi_items = "".join(f"""<div class="wifi-item" onclick="selectWifi('{html.escape(w['ssid'])}',{str(bool(w['security'])).lower()})">
  <span class="wifi-name">{html.escape(w['ssid'])}</span>
  <span class="wifi-sig">{w['signal']}%</span>
  {'<span class="wifi-sec">🔒</span>' if w['security'] else ''}
</div>""" for w in wifi_list)

    bark_url_val = f"{bark.get('BARK_SERVER','https://api.day.app')}/{bark.get('BARK_KEY','')}" if bark.get('BARK_KEY') else ""

    wifi_card = f"""<div class="card">
  <div class="card-header">📶 WiFi 管理</div>
  <div class="card-body" style="padding:0">
    {wifi_items if wifi_items else '<div class="empty" style="padding:.8rem">扫描中...</div>'}
    <div id="wifi-form" style="display:none;padding:1rem;border-top:1px solid #334155">
      <div style="font-size:.85rem;color:#93c5fd;margin-bottom:.6rem">连接：<b id="wifi-ssid-label"></b></div>
      <input type="hidden" id="wifi-ssid-input">
      <div id="wifi-psk-row" class="form-row" style="display:none">
        <input type="password" id="wifi-psk-input" placeholder="WiFi 密码">
      </div>
      <div class="form-row" style="margin-top:.6rem">
        <button onclick="connectWifi()">连接</button>
        <button class="sec" onclick="document.getElementById('wifi-form').style.display='none'">取消</button>
      </div>
      <div style="font-size:.75rem;color:#64748b;margin-top:.5rem">⚠️ 切换后页面将短暂断开，约 30 秒后用新 IP 重新访问</div>
    </div>
  </div>
</div>"""

    bark_card = f"""<div class="card">
  <div class="card-header">🔔 Bark 推送配置</div>
  <div class="card-body">
    <input type="text" id="bark-url" placeholder="https://api.day.app/YOUR_KEY/" value="{html.escape(bark_url_val)}">
    <div class="form-row" style="margin-top:.6rem">
      <button onclick="saveBark()">保存</button>
      <button class="sec" onclick="testBark()">发送测试</button>
    </div>
  </div>
</div>"""

    return render_page(status_card + sms_card + log_card + wifi_card + bark_card)


# ─── HTTP Handler ───────────────────────────────────────────────────────────────

class H(BaseHTTPRequestHandler):
    def log_message(self, f, *a): pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def _html(self, body):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/sms":
            self._json(get_sms()); return
        if self.path == "/api/status":
            self._json(get_status()); return
        if self.path == "/api/wifi":
            self._json(get_wifi_list()); return
        if self.path == "/api/bark":
            self._json(get_bark()); return
        self._html(build_dashboard())

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(ln).decode()) if ln else {}
        if self.path == "/api/wifi/connect":
            connect_wifi(body.get("ssid",""), body.get("psk",""))
            self._json({"ok": True}); return
        if self.path == "/api/bark":
            save_bark(body.get("server","https://api.day.app"), body.get("key",""))
            self._json({"ok": True}); return
        if self.path == "/api/modem/reset":
            modem_reset()
            self._json({"ok": True}); return
        if self.path == "/api/bark/test":
            b = get_bark()
            r = test_bark(b.get("BARK_SERVER","https://api.day.app"), b.get("BARK_KEY",""))
            self._json({"ok": '"code":200' in r, "raw": r}); return
        self._json({"ok": False}, 404)

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"Admin panel on :{PORT}")
    srv.serve_forever()
