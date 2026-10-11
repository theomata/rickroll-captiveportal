#!/usr/bin/env bash

SESSION="rickroll"
INTERFACE="${1:-wlan0}"

echo "[+] Shutting down Rickroll Portal services..."

echo "[*] Stopping hostapd..."
sudo pkill -x hostapd 2>/dev/null || true

echo "[*] Stopping dnsmasq..."
sudo pkill -x dnsmasq 2>/dev/null || true

echo "[*] Stopping portal..."
sudo pkill -f "portal.py" 2>/dev/null || true

echo "[*] Terminating tmux session '$SESSION'..."
tmux kill-session -t "$SESSION" 2>/dev/null || true

echo "[*] Cleaning up iptables rules..."
sudo iptables -t nat -D PREROUTING -i "$INTERFACE" -s 10.13.37.0/24 -p tcp --dport 80 -j REDIRECT --to-ports 80 2>/dev/null || true
sudo iptables -D INPUT -p tcp --dport 443 -j REJECT --reject-with tcp-reset 2>/dev/null || true

echo "[+] Teardown complete."
echo
echo "Process status:"
ps aux | grep -E '[h]ostapd|[d]nsmasq|[p]ortal.py' || echo "  All services stopped cleanly."
