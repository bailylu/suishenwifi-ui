#!/bin/bash
IFACE=wlan0
iptables -D INPUT   -i $IFACE -p tcp --dport 443 -j CP_TLS 2>/dev/null || true
iptables -D FORWARD -i $IFACE -p tcp --dport 443 -j REJECT --reject-with tcp-reset 2>/dev/null || true
iptables -F CP_TLS 2>/dev/null || true
iptables -X CP_TLS 2>/dev/null || true
echo "Captive portal rules removed."
