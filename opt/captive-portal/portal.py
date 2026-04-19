#!/usr/bin/env python3
"""随身WiFi 配置门户 — STA 凭据 + Bark 配置"""
import subprocess, html, urllib.parse, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTAL_IP = "10.42.1.1"
PORT = 80
BARK_CONF = "/etc/bark.conf"
AP_NAME = "suishenwifi"

PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>随身WiFi 配置</title><style>
body{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1rem}
.card{background:#1e293b;border-radius:16px;padding:1.8rem;max-width:420px;width:100%;
box-shadow:0 20px 50px rgba(0,0,0,.4)}
h1{margin:0 0 .3rem;font-size:1.4rem} h2{margin:1.2rem 0 .4rem;font-size:1rem;color:#93c5fd}
p{color:#94a3b8;line-height:1.5;font-size:.9rem;margin:.3rem 0}
label{display:block;margin-top:.8rem;font-size:.85rem;color:#cbd5e1}
input,select,button{width:100%;padding:.7rem .9rem;border-radius:10px;border:0;font-size:.95rem;box-sizing:border-box;margin-top:.3rem}
input,select{background:#0f172a;color:#e2e8f0;border:1px solid #334155}
button{background:#3b82f6;color:#fff;font-weight:600;cursor:pointer;margin-top:1.2rem}
button:hover{background:#2563eb} button:disabled{background:#475569}
.muted{color:#64748b;font-size:.8rem;margin-top:.3rem}
.ok{background:#10b98133;border:1px solid #10b981;padding:1rem;border-radius:10px;margin-top:.5rem}
.warn{background:#f59e0b22;border:1px solid #f59e0b;padding:.8rem;border-radius:10px;font-size:.85rem;line-height:1.5;margin:.8rem 0;color:#fbbf24}
.fail{background:#ef444433;border:1px solid #ef4444;padding:.8rem;border-radius:10px;font-size:.9rem;margin:.8rem 0;color:#fca5a5}
.err{background:#ef444433;border:1px solid #ef4444;padding:.7rem;border-radius:10px;margin-top:.5rem;font-size:.85rem}
</style></head><body><div class="card">__BODY__</div></body></html>"""

FORM = """<h1>🛰️ 随身WiFi 配置</h1>
<p>请填写要连接的 WiFi 与 Bark 推送信息。保存后设备将重启并自动联网。</p>
__FAILBANNER__
<div class="warn">⚠️ <b>请仔细核对 WiFi 名称和密码（注意大小写、中英文符号）</b>。支持中文名称。提交后设备会重启尝试连接，若填错，约 2 分钟后将自动回到本页，请耐心等待，<b>不要反复断电</b>。</div>
<form method="POST" action="/save" accept-charset="UTF-8">
  <h2>📶 上行 WiFi</h2>
  <label>WiFi 名称
    <input name="ssid" type="text" required placeholder="家里的 WiFi 名称（支持中文）" autocomplete="off" inputmode="text" lang="zh" autocapitalize="off" spellcheck="false">
  </label>
  <label>密码（开放网络留空）
    <input type="password" name="psk" autocomplete="new-password" autocapitalize="off" spellcheck="false">
  </label>
  <h2>🔔 Bark 推送</h2>
  <p class="muted">用于重启联网后推送本机 IP。留空则不启用。</p>
  <label>Bark 完整地址
    <input name="bark_url" placeholder="https://api.day.app/xxxxxxxxxxxx/" autocomplete="off">
  </label>
  <button type="submit">保存并重启</button>
</form>"""

OK_T = """<h1>✅ 配置已保存</h1>
<div class="ok">设备将在 3 秒后重启，之后自动连接 <b>__SSID__</b>。<br>
联网成功后会通过 Bark 推送 IP。</div>
<p class="muted" style="margin-top:1rem">此页面可关闭。</p>"""

ERR_T = """<h1>❌ 保存失败</h1><div class="err">__MSG__</div>
<p><a href="/" style="color:#93c5fd">← 返回重试</a></p>"""


def render(body): return PAGE.replace("__BODY__", body)


def scan_ssids():
    try:
        subprocess.run(["nmcli", "d", "wifi", "rescan"], capture_output=True, timeout=8)
        r = subprocess.run(["nmcli", "-t", "-f", "SSID,SIGNAL", "d", "wifi", "list"],
                           capture_output=True, text=True, timeout=8)
        seen = {}
        for line in r.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 2: continue
            ssid = parts[0].strip()
            try: sig = int(parts[1])
            except ValueError: sig = 0
            if ssid and ssid not in seen: seen[ssid] = sig
        return sorted(seen.items(), key=lambda x: -x[1])
    except Exception as e:
        print("scan err:", e); return []


def build_ssid_options():
    opts = ['<option value="">-- 选择 WiFi --</option>']
    for ssid, sig in scan_ssids():
        s = html.escape(ssid)
        opts.append(f'<option value="{s}">{s} ({sig}%)</option>')
    opts.append('<option value="__manual__">[手动输入]</option>')
    return "".join(opts)


def save_wifi(ssid, psk):
    # Remove old STA profiles on wlan0 (except AP)
    r = subprocess.run(["nmcli", "-t", "-f", "NAME,TYPE", "c", "show"],
                       capture_output=True, text=True)
    for line in r.stdout.splitlines():
        name, _, typ = line.partition(":")
        if typ == "802-11-wireless" and name != AP_NAME:
            subprocess.run(["nmcli", "c", "delete", name], capture_output=True)
    cmd = ["nmcli", "c", "add", "type", "wifi", "ifname", "wlan0",
           "con-name", ssid, "ssid", ssid,
           "connection.autoconnect", "yes",
           "connection.autoconnect-priority", "10"]
    if psk:
        cmd += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", psk]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())


def save_bark(key, server):
    if not key:
        try: os.remove(BARK_CONF)
        except FileNotFoundError: pass
        return
    with open(BARK_CONF, "w") as f:
        f.write(f'BARK_SERVER="{server.rstrip("/")}"\nBARK_KEY="{key}"\n')
    os.chmod(BARK_CONF, 0o600)


def reboot_later():
    time.sleep(3)
    subprocess.run(["systemctl", "reboot"])


class H(BaseHTTPRequestHandler):
    def log_message(self, f, *a): print("[portal]", self.client_address[0], f % a)

    def _send(self, body, code=200, ctype="text/html; charset=utf-8", extra=None):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        host = self.headers.get("Host", "").lower()
        path = self.path
        portal_url = f"http://{PORTAL_IP}/"
        # Any request not aimed at our portal IP: redirect to trigger captive-portal popup
        if host and PORTAL_IP not in host:
            self.send_response(302)
            self.send_header("Location", portal_url)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            body = (f'<html><head><meta http-equiv="refresh" content="0; url={portal_url}">'
                    f'</head><body><a href="{portal_url}">Click to configure</a></body></html>').encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        banner = ""
        try:
            with open("/var/lib/captive-portal/last_failed") as f:
                info = f.read().strip()
            banner = f'<div class="fail">❌ 上次连接失败：{info}。请仔细检查 WiFi 名称和密码是否正确。</div>'
        except FileNotFoundError:
            pass
        self._send(render(FORM.replace("__FAILBANNER__", banner)))

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", "0"))
        data = urllib.parse.parse_qs(self.rfile.read(ln).decode(errors="ignore"))
        ssid = (data.get("ssid", [""])[0] or "").strip()
        psk = (data.get("psk", [""])[0] or "").strip()
        bark_url = (data.get("bark_url", [""])[0] or "").strip()
        bark_server, bark_key = "https://api.day.app", ""
        if bark_url:
            import re
            m = re.match(r"^(https?://[^/]+)/([A-Za-z0-9_\-]+)/?", bark_url)
            if m:
                bark_server, bark_key = m.group(1), m.group(2)
            else:
                bark_key = bark_url
        if not ssid:
            self._send(render(ERR_T.replace("__MSG__", "请填写 WiFi 名称。"))); return
        try:
            save_wifi(ssid, psk)
            save_bark(bark_key, bark_server)
            try: os.remove("/var/lib/captive-portal/last_failed")
            except FileNotFoundError: pass
        except Exception as e:
            self._send(render(ERR_T.replace("__MSG__", html.escape(str(e))))); return
        self._send(render(OK_T.replace("__SSID__", html.escape(ssid))))
        threading.Thread(target=reboot_later, daemon=True).start()


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"Portal on :{PORT}")
    srv.serve_forever()
