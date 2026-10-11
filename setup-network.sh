#!/usr/bin/env bash

set -e

INTERFACE="${1:-wlan0}"
# Auto-detect default route interface if available, fallback to eth0
UPSTREAM="${2:-$(ip route show default 2>/dev/null | awk '/default/ {print $5}' | head -n1)}"
if [ -z "$UPSTREAM" ] && ip link show eth0 >/dev/null 2>&1; then
    UPSTREAM="eth0"
fi

echo "[+] Setting up network for Rickroll Portal..."
echo "[+] Wireless interface: $INTERFACE"

# Verify wireless interface exists
if ! ip link show "$INTERFACE" >/dev/null 2>&1; then
    echo "[-] Error: Wireless interface '$INTERFACE' was not found!"
    echo "[!] Available wireless interfaces:"
    iw dev 2>/dev/null | awk '$1=="Interface"{print "    - " $2}' || ip link show | grep -E '^[0-9]+: (wl|wlan)' || echo "    None detected"
    exit 1
fi

echo "[+] Assigning IP 10.13.37.1/24 to $INTERFACE..."
sudo ip addr flush dev "$INTERFACE"
sudo ip addr add 10.13.37.1/24 dev "$INTERFACE"
sudo ip link set "$INTERFACE" up

echo "[+] Enabling IPv4 kernel forwarding..."
sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null

# Clean any existing PREROUTING redirect rule first to avoid duplicates
sudo iptables -t nat -D PREROUTING -i "$INTERFACE" -s 10.13.37.0/24 -p tcp --dport 80 -j REDIRECT --to-ports 80 2>/dev/null || true

echo "[+] Configuring HTTP Captive Portal redirect (Port 80 -> 10.13.37.1:80)..."
sudo iptables -t nat -A PREROUTING -i "$INTERFACE" -s 10.13.37.0/24 -p tcp --dport 80 -j REDIRECT --to-ports 80

echo "[+] Configuring Port 443 TCP reset (prevents mobile TLS timeouts & accelerates captive probe)..."
sudo iptables -D INPUT -p tcp --dport 443 -j REJECT --reject-with tcp-reset 2>/dev/null || true
sudo iptables -A INPUT -p tcp --dport 443 -j REJECT --reject-with tcp-reset

# Configure upstream NAT if available
if [ -n "$UPSTREAM" ] && [ "$UPSTREAM" != "$INTERFACE" ] && ip link show "$UPSTREAM" >/dev/null 2>&1; then
    echo "[+] Upstream interface detected: $UPSTREAM (Enabling internet forwarding)"
    sudo iptables -t nat -D POSTROUTING -o "$UPSTREAM" -s 10.13.37.0/24 -j MASQUERADE 2>/dev/null || true
    sudo iptables -t nat -A POSTROUTING -o "$UPSTREAM" -s 10.13.37.0/24 -j MASQUERADE
    sudo iptables -A FORWARD -i "$INTERFACE" -o "$UPSTREAM" -s 10.13.37.0/24 -j ACCEPT 2>/dev/null || true
    sudo iptables -A FORWARD -i "$UPSTREAM" -o "$INTERFACE" -d 10.13.37.0/24 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
else
    echo "[!] No upstream internet interface detected. Operating in standalone rogue AP mode."
fi

echo "[+] Network configuration complete on $INTERFACE (10.13.37.1)."
