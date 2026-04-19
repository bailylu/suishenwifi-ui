#!/bin/bash
# Modem watchdog: every 10min, try to recover modem if abnormal.
# - registered/connected: OK, skip
# - failed: skip (disable/enable on failed modem errors out and can
#   destabilize firmware; user can recover via admin panel "重新搜索信号")
# - other (searching/enabled/idle/etc): toggle disable/enable with timeout

get_state() {
  timeout 5 mmcli -m any 2>/dev/null | awk '/\| +state:/{gsub(/\033\[[0-9;]*m/,""); print $NF; exit}'
}

while true; do
  sleep 600
  STATE=$(get_state)
  case "$STATE" in
    registered|connected|failed|"")
      continue
      ;;
    *)
      timeout 15 mmcli -m any --disable >/dev/null 2>&1
      sleep 5
      timeout 15 mmcli -m any --enable  >/dev/null 2>&1
      ;;
  esac
done
