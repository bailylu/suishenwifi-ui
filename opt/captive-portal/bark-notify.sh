#!/bin/bash
CONF=/etc/bark.conf
# Clear failure marker since we are online
rm -f /var/lib/captive-portal/last_failed 2>/dev/null

[ -r "$CONF" ] || exit 0
. "$CONF"
[ -n "$BARK_KEY" ] || exit 0
[ -n "$BARK_SERVER" ] || BARK_SERVER="https://api.day.app"

for i in $(seq 1 30); do
  IP=$(ip -4 -br addr show wlan0 2>/dev/null | awk '{print $3}' | cut -d/ -f1)
  SSID=$(nmcli -t -f active,ssid d wifi | awk -F: '$1=="yes"{print $2;exit}')
  if [ -n "$IP" ] && [ "$IP" != "10.42.1.1" ]; then
    TITLE=$(python3 -c "import urllib.parse;print(urllib.parse.quote('随身WiFi已联网'))")
    BODY=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "SSID:${SSID}
后台管理：http://${IP}")
    curl -sS --max-time 10 "${BARK_SERVER%/}/${BARK_KEY}/${TITLE}/${BODY}" > /tmp/bark.log 2>&1
    echo "bark sent: $IP"
    exit 0
  fi
  sleep 2
done
echo "bark: wlan0 STA not ready" >&2
exit 1
