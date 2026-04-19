#!/bin/bash
# If after 40s wlan0 has no upstream STA IP, fall back to AP + mark failure
sleep 40
IP=$(ip -4 -br addr show wlan0 2>/dev/null | awk '{print $3}' | cut -d/ -f1)
if [ -z "$IP" ] || [ "$IP" = "10.42.1.1" ]; then
    mkdir -p /var/lib/captive-portal
    SSID=$(nmcli -g 802-11-wireless.ssid c show 2>/dev/null | grep -v '^$' | grep -v '^suishenwifi$' | head -1)
    if [ -n "$SSID" ]; then
        echo "无法连接到「${SSID}」（密码错误或信号弱）" > /var/lib/captive-portal/last_failed
    else
        echo "未配置上行 WiFi" > /var/lib/captive-portal/last_failed
    fi
    echo "watchdog: no STA, activating AP"
    nmcli c up suishenwifi || true
fi
