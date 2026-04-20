#!/bin/bash
# 服务和网络看门狗 v4
# 监控：服务状态 + wlan0接口 + 网络连通性
# 注意：热点模式下不尝试重连wlan0

SERVICES="admin-panel.service sms-forward.service"
CHECK_INTERVAL=60
GATEWAY="192.168.3.1"

log() { echo "$(date): $1"; }

while true; do
    # 检查当前是否在热点模式
    IS_HOTSPOT=$(nmcli -t -f NAME,TYPE connection show --active | grep ':wifi:' | grep 'suishenwifi' | wc -l)

    # 1. 检查并重启崩溃的服务
    for service in $SERVICES; do
        if ! systemctl is-active --quiet "$service"; then
            log "$service is not running, restarting..."
            systemctl restart "$service"
        fi
    done

    # 2. 检查admin-panel进程是否存活
    if ! pgrep -f "/opt/admin/admin.py" > /dev/null; then
        log "admin-panel process missing, restarting..."
        systemctl restart admin-panel.service
    fi

    # 3. 检查wlan0接口是否存在
    if ! ip link show wlan0 > /dev/null 2>&1; then
        if [ "$IS_HOTSPOT" -eq 0 ]; then
            log "wlan0 interface missing, re-enabling WiFi radio..."
            nmcli radio wifi off
            sleep 2
            nmcli radio wifi on
            sleep 5
        fi
    fi

    # 4. 检查网络连通性（只在非热点模式下）
    if [ "$IS_HOTSPOT" -eq 0 ]; then
        if ping -c 2 -W 3 "$GATEWAY" > /dev/null 2>&1; then
            : # 网关可达
        else
            log "Gateway $GATEWAY unreachable, reconnecting wlan0..."
            nmcli device disconnect wlan0 2>/dev/null
            sleep 2
            nmcli device connect wlan0 2>/dev/null
        fi
    fi

    sleep $CHECK_INTERVAL
done