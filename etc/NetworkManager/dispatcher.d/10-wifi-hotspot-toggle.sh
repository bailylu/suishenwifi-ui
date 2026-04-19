#!/bin/bash
# WiFi/热点自动切换脚本 v3
# 简化版本：修复锁文件检查问题

INTERFACE=$1
ACTION=$2
LOCK_FILE="/tmp/wifi-hotspot-toggle.lock"

[ "$INTERFACE" != "wlan0" ] && exit 0

# 简单锁文件检查（如果存在则退出，避免重复执行）
if [ -f "$LOCK_FILE" ]; then
    exit 0
fi

# 创建锁文件，10秒后自动删除
touch "$LOCK_FILE"
(sleep 10; rm -f "$LOCK_FILE") &

# 检查是否有已保存的WiFi配置（除了suishenwifi）
SAVED_WIFI=$(nmcli -t -f NAME,TYPE connection show | grep ':wifi:' | grep -v suishenwifi | wc -l)

# 获取当前激活的WiFi连接
ACTIVE_WIFI=$(nmcli -t -f NAME,TYPE connection show --active | grep ':wifi:' | cut -d: -f1)

case "$ACTION" in
    up)
        # WiFi连接成功（排除suishenwifi本身），关闭热点
        if [ "$ACTIVE_WIFI" != "suishenwifi" ] && [ -n "$ACTIVE_WIFI" ]; then
            nmcli connection down suishenwifi 2>/dev/null
        fi
        ;;
    down)
        # WiFi断开
        if [ "$SAVED_WIFI" -eq 0 ]; then
            # 没有已保存的WiFi配置，开启热点
            nmcli connection up suishenwifi 2>/dev/null
        fi
        ;;
esac