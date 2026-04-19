#!/bin/bash
sleep 600
IP=$(ip -4 -br addr show wlan0 2>/dev/null | awk '{print $3}' | cut -d/ -f1)
[ -z "$IP" ] || [ "$IP" = "10.42.1.1" ] && exit 0
STATE=$(mmcli -m 0 2>/dev/null | awk '/\| +state:/{gsub(/\033\[[0-9;]*m/,""); print $NF; exit}')
if [ "$STATE" != "registered" ] && [ "$STATE" != "connected" ]; then
    systemctl reboot
fi
