#!/bin/bash
# 随身WiFi 一键安装脚本
# 适用平台：高通 410 随身WiFi，已刷 ARM Debian/Ubuntu
# 用法：bash install.sh [BARK_SERVER] [BARK_KEY]
#   BARK_SERVER 示例：https://api.day.app
#   BARK_KEY    示例：AbCdEfGhIjKlMn

set -e

BARK_SERVER="${1:-https://api.day.app}"
BARK_KEY="${2:-}"
WIFI_SSID="${3:-}"
WIFI_PASS="${4:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

[ "$(id -u)" = "0" ] || error "请用 root 运行：sudo bash install.sh"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "================================================"
echo "   随身WiFi 配网 & 管理系统 一键安装"
echo "================================================"
echo ""

# ── 1. 依赖检查 ──────────────────────────────────────
info "检查依赖..."
MISSING=""
for cmd in python3 nmcli curl mmcli; do
    command -v $cmd >/dev/null 2>&1 || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
    warn "安装缺失依赖：$MISSING"
    apt-get update -qq && apt-get install -y -qq python3 curl network-manager modemmanager 2>/dev/null || true
fi
info "依赖就绪"

# ── 2. 复制文件 ──────────────────────────────────────
info "复制程序文件..."
mkdir -p /opt/captive-portal /opt/admin
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
mkdir -p /var/lib/captive-portal

cp "$SCRIPT_DIR/opt/captive-portal/"*.sh /opt/captive-portal/
cp "$SCRIPT_DIR/opt/captive-portal/"*.py /opt/captive-portal/
cp "$SCRIPT_DIR/opt/admin/admin.py"       /opt/admin/
cp "$SCRIPT_DIR/etc/NetworkManager/dispatcher.d/99-portal" \
      /etc/NetworkManager/dispatcher.d/99-portal
cp "$SCRIPT_DIR/etc/NetworkManager/dnsmasq-shared.d/captive.conf" \
      /etc/NetworkManager/dnsmasq-shared.d/captive.conf
cp "$SCRIPT_DIR/etc/systemd/system/"*.service /etc/systemd/system/

chmod +x /opt/captive-portal/*.sh
chmod +x /etc/NetworkManager/dispatcher.d/99-portal

# SMS 转发脚本（如存在原厂版本则替换）
if [ -f "$SCRIPT_DIR/sms_forwarder.sh" ]; then
    cp "$SCRIPT_DIR/sms_forwarder.sh" /root/sms_forwarder.sh
    chmod +x /root/sms_forwarder.sh
fi
info "文件复制完成"

# ── 3. Bark 配置 ──────────────────────────────────────
info "写入 Bark 配置..."
if [ -z "$BARK_KEY" ]; then
    warn "未提供 BARK_KEY，将写入占位符，安装后请在后台管理页面配置"
    BARK_KEY="YOUR_BARK_KEY_HERE"
fi
cat > /etc/bark.conf << EOF
BARK_SERVER="${BARK_SERVER}"
BARK_KEY="${BARK_KEY}"
EOF
chmod 600 /etc/bark.conf
info "Bark 配置：${BARK_SERVER}/${BARK_KEY}"

# ── 4. NM 热点 profile ────────────────────────────────
info "创建热点 profile (suishenwifi)..."
nmcli c delete suishenwifi 2>/dev/null || true
nmcli c add type wifi \
    ifname wlan0 \
    con-name suishenwifi \
    ssid "suishenWiFi" \
    -- \
    wifi.mode ap \
    wifi-sec.key-mgmt none \
    ipv4.method shared \
    ipv4.addresses 10.42.1.1/24 \
    connection.autoconnect no \
    connection.autoconnect-priority 0
info "热点 profile 创建完成（SSID: suishenWiFi，开放无密码）"

# ── 5. 上行 WiFi profile（可选）──────────────────────
if [ -n "$WIFI_SSID" ]; then
    info "创建上行 WiFi profile ($WIFI_SSID)..."
    nmcli c delete "$WIFI_SSID" 2>/dev/null || true
    nmcli c add type wifi \
        ifname wlan0 \
        con-name "$WIFI_SSID" \
        ssid "$WIFI_SSID" \
        -- \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$WIFI_PASS" \
        connection.autoconnect yes \
        connection.autoconnect-priority 10
    info "上行 WiFi 配置完成"
else
    warn "未提供上行 WiFi，设备首次启动将进入热点配网模式"
fi

# ── 6. systemd 服务 ───────────────────────────────────
info "注册系统服务..."
systemctl daemon-reload
systemctl enable bark-notify.service
systemctl enable provision-watchdog.service
systemctl enable modem-watchdog.service
systemctl enable admin-panel.service
# captive-portal 由 NM dispatcher 按需启停，不 enable
systemctl disable captive-portal.service 2>/dev/null || true
info "服务注册完成"

# ── 7. SMS 转发日志目录 ───────────────────────────────
touch /var/log/sms-forward.log
info "SMS 日志文件就绪"

echo ""
echo "================================================"
echo "   安装完成！"
echo ""
echo "   下一步："
if [ -n "$WIFI_SSID" ]; then
echo "   1. 重启设备：reboot"
echo "   2. 设备将自动连接 $WIFI_SSID"
echo "   3. 收到 Bark 推送后，访问通知中的 IP 进入后台"
else
echo "   1. 重启设备：reboot"
echo "   2. 手机连接热点「suishenWiFi」（无密码）"
echo "   3. 自动弹出配网页面，填入 WiFi 和 Bark 信息"
echo "   4. 提交后设备重启，收到 Bark 推送即配置成功"
fi
echo "================================================"
echo ""
