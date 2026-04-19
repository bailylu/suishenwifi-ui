#!/bin/bash
while true; do
  sleep 600
  STATE=$(mmcli -m 0 2>/dev/null | awk '/\| +state:/{gsub(/\033\[[0-9;]*m/,""); print $NF; exit}')
  if [ "$STATE" != "registered" ] && [ "$STATE" != "connected" ]; then
    mmcli -m 0 --disable
    sleep 5
    mmcli -m 0 --enable
  fi
done
