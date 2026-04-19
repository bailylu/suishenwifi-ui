#!/bin/bash
# 随身WiFi 一键安装脚本
# 适用平台：高通 410 随身WiFi，已刷 ARM Debian/Ubuntu
# 用法：bash install.sh [BARK_SERVER] [BARK_KEY] [WIFI_SSID] [WIFI_PASS]
#   BARK_SERVER 示例：https://api.day.app
#   BARK_KEY    示例：AbCdEfGhIjKlMn
#
# ⚠️ 如果无法连接 GitHub（下载脚本超时），可以先修改网关和DNS：
#    nmcli connection modify [WIFI名称] ipv4.gateway 你的路由器IP
#    nmcli connection modify [WIFI名称] ipv4.dns "8.8.8.8;114.114.114.114"
#    或者指向家里能访问GitHub的设备IP（如电脑IP）
#    然后重新运行此脚本

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

# ── 1. 依赖检查与安装 ────────────────────────────────
info "检查依赖..."
MISSING=""
for cmd in python3 nmcli curl mmcli; do
    command -v $cmd >/dev/null 2>&1 || MISSING="$MISSING $cmd"
done
if [ -n "$MISSING" ]; then
    warn "安装缺失依赖：$MISSING"
    apt-get update -qq
    apt-get install -y -qq python3 curl network-manager modemmanager
fi
info "依赖就绪"

# ── 2. 复制程序文件 ───────────────────────────────────
info "复制程序文件..."
mkdir -p /opt/captive-portal /opt/admin
mkdir -p /etc/NetworkManager/dispatcher.d
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

# SMS 转发脚本
if [ -f "$SCRIPT_DIR/sms_forwarder.sh" ]; then
    cp "$SCRIPT_DIR/sms_forwarder.sh" /root/sms_forwarder.sh
    chmod +x /root/sms_forwarder.sh
fi
touch /var/log/sms-forward.log
info "文件复制完成"

# ── 4. Bark 配置 ──────────────────────────────────────
info "写入 Bark 配置..."
if [ -z "$BARK_KEY" ]; then
    warn "未提供 BARK_KEY，安装后请在后台管理页面配置"
    BARK_KEY="YOUR_BARK_KEY_HERE"
fi
cat > /etc/bark.conf << EOF
BARK_SERVER="${BARK_SERVER}"
BARK_KEY="${BARK_KEY}"
EOF
chmod 600 /etc/bark.conf
info "Bark: ${BARK_SERVER}/${BARK_KEY}"

# ── 5. NM 热点 profile ────────────────────────────────
info "创建热点 profile (suishenwifi)..."
nmcli c delete suishenwifi 2>/dev/null || true
nmcli c add type wifi \
    ifname wlan0 \
    con-name suishenwifi \
    ssid "suishenWiFi" \
    -- \
    wifi.mode ap \
    ipv4.method shared \
    ipv4.addresses 10.42.1.1/24 \
    connection.autoconnect no \
    connection.autoconnect-priority 0
info "热点 profile 就绪（SSID: suishenWiFi，开放无密码）"

# ── 6. 上行 WiFi profile（可选）──────────────────────
if [ -n "$WIFI_SSID" ]; then
    info "创建上行 WiFi profile (${WIFI_SSID})..."
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
    warn "未提供上行 WiFi，首次启动将进入热点配网模式"
fi

# ── 7. systemd 服务 ───────────────────────────────────
info "注册系统服务..."
# 清理遗留 sms.service（旧版 DbusSmsForward，会崩溃重启把 CPU 和短信通道占死）
if systemctl list-unit-files 2>/dev/null | grep -q '^sms\.service'; then
    warn "检测到遗留 sms.service，正在下线"
    systemctl stop sms.service 2>/dev/null || true
    systemctl disable sms.service 2>/dev/null || true
    [ -f /etc/systemd/system/sms.service ] && \
      mv /etc/systemd/system/sms.service /etc/systemd/system/sms.service.disabled
fi
systemctl daemon-reload
systemctl enable bark-notify.service
systemctl enable provision-watchdog.service
systemctl enable modem-watchdog.service
systemctl enable admin-panel.service
systemctl enable sms-forward.service
# captive-portal 由 NM dispatcher 按需启停，不 enable
systemctl disable captive-portal.service 2>/dev/null || true
info "服务注册完成"

# ── 8. 重启 NetworkManager 使配置生效 ────────────────
info "重启 NetworkManager..."
systemctl restart NetworkManager
sleep 2
info "NetworkManager 已重启"

echo ""
echo "================================================"
echo "   安装完成！请执行 reboot 重启设备"
echo ""
if [ -n "$WIFI_SSID" ]; then
echo "   重启后设备将自动连接「${WIFI_SSID}」"
echo "   联网成功后会收到 Bark 推送，点击链接进入后台"
else
echo "   重启后手机连接热点「suishenWiFi」（无密码）"
echo "   自动弹出配网页面，填入 WiFi 和 Bark 信息即可"
fi
echo "================================================"
echo ""