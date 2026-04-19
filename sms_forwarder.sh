#!/bin/sh
# === 配置区 ===
[ -r /etc/bark.conf ] && . /etc/bark.conf
: "${BARK_SERVER:=https://api.day.app}"
: "${BARK_KEY:=N6zxDBZMj9SyD5UCQuJBY9}"
BARK_URL="${BARK_SERVER%/}/${BARK_KEY}"
LAST_SMS_FILE="/tmp/last_sms_content"
LAST_STATE_FILE="/tmp/last_modem_state"

echo "SMS Gateway V10 running..."

# 1. 系统上线主动报备
curl -k -s -X POST "$BARK_URL" -d "title=系统启动&body=短信网关已上线&group=System" > /dev/null

while true; do
    # 2. 网卡状态监控（去抖：状态连续 3 次相同且与上次推送不同才推送）
    CURRENT_STATE=$(mmcli -m 0 2>/dev/null | awk '/\| +state:/{print $3; exit}')
    PREV_CANDIDATE=$(cat /tmp/modem_candidate_state 2>/dev/null)
    PREV_COUNT=$(cat /tmp/modem_candidate_count 2>/dev/null || echo 0)
    OLD_STATE=$(cat $LAST_STATE_FILE 2>/dev/null)
    if [ "$CURRENT_STATE" = "$PREV_CANDIDATE" ]; then
        PREV_COUNT=$((PREV_COUNT + 1))
    else
        PREV_COUNT=1
        echo "$CURRENT_STATE" > /tmp/modem_candidate_state
    fi
    echo "$PREV_COUNT" > /tmp/modem_candidate_count
    # Require 3 consecutive stable reads (~15s with sleep 5) AND different from last pushed
    if [ "$PREV_COUNT" -ge 3 ] && [ "$CURRENT_STATE" != "$OLD_STATE" ]; then
        if [ "$CURRENT_STATE" = "registered" ] || [ "$CURRENT_STATE" = "connected" ]; then
            INFO="✅ 蜂窝网络已就绪"
        else
            INFO="⏳ 蜂窝网络等待搜索信号"
        fi
        curl -k -s -X POST "$BARK_URL" -d "title=状态提醒&body=$INFO&group=System" > /dev/null
        echo "$CURRENT_STATE" > $LAST_STATE_FILE
    fi

    # 3. 获取短信列表
    SMS_LIST=$(mmcli -m 0 --messaging-list-sms 2>/dev/null | grep -o 'SMS/[0-9]*' | cut -d'/' -f2)
    for i in $SMS_LIST; do
        # 提取数据并清洗
        RAW_TEXT=$(mmcli -s $i 2>/dev/null | grep 'text:' | sed 's/^.*text: //' | tr -d '"' | tr -d '\\' | tr -d '\n' | tr -d '\r')
        FROM=$(mmcli -s $i 2>/dev/null | grep 'number:' | sed 's/^.*number: //' | tr -d '"')
        
        if [ -n "$RAW_TEXT" ]; then
            # 4. 智能去重逻辑
            PREV_CONTENT=$(cat $LAST_SMS_FILE 2>/dev/null)
            if [ "$RAW_TEXT" = "$PREV_CONTENT" ]; then
                mmcli -m 0 --messaging-delete-sms=$i --timeout=20 > /dev/null 2>&1
                continue
            fi
            
            # 5. 构建并发送推送
            PAYLOAD=$(printf '{"title": "短信来自: %s", "body": "%s", "group": "ClubSim"}' "$FROM" "$RAW_TEXT")
            curl -k -m 20 -s -X POST "$BARK_URL" -H "Content-Type: application/json" -d "$PAYLOAD" > /dev/null
            
            if [ $? -eq 0 ]; then
                echo "$RAW_TEXT" > $LAST_SMS_FILE
                mmcli -m 0 --messaging-delete-sms=$i --timeout=20 > /dev/null 2>&1
                # Append to forward log
                echo "$(date +%s)|$FROM|$RAW_TEXT" >> /var/log/sms-forward.log
            fi
        fi
    done
    sleep 5
done
