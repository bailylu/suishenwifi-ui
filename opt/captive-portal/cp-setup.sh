#!/bin/bash
set -e
IFACE=wlan0
PORTAL=10.42.1.1

# Reject HTTPS so phones fall back to HTTP probe immediately
iptables -N CP_TLS 2>/dev/null || true
iptables -F CP_TLS
iptables -A CP_TLS -d $PORTAL -j ACCEPT
iptables -A CP_TLS -p tcp --dport 443 -j REJECT --reject-with tcp-reset
iptables -C INPUT   -i $IFACE -p tcp --dport 443 -j CP_TLS 2>/dev/null || \
  iptables -I INPUT   -i $IFACE -p tcp --dport 443 -j CP_TLS
iptables -C FORWARD -i $IFACE -p tcp --dport 443 -j REJECT --reject-with tcp-reset 2>/dev/null || \
  iptables -I FORWARD -i $IFACE -p tcp --dport 443 -j REJECT --reject-with tcp-reset

echo "Captive portal rules installed (portal on :80, HTTPS rejected)."
