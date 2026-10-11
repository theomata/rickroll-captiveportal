#!/usr/bin/env bash

# Ensure script is run with sudo / root
if [ "$EUID" -ne 0 ]; then
  echo -e "\e[31m[-] Error: Please run this script with sudo or as root.\e[0m"
  exit 1
fi

INTERFACE="${1:-wlan0}"

echo -e "\e[34m[*] 1. Stopping any conflicting host services...\e[0m"
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

echo -e "\e[34m[*] 2. Reloading wireless drivers (clearing stale VM USB states)...\e[0m"
modprobe -r ath9k_htc 2>/dev/null || true
sleep 1
modprobe ath9k_htc 2>/dev/null || true

echo -e "\e[33m[*] 3. Waiting for $INTERFACE to re-initialize in kernel...\e[0m"
timeout=10
while [ ! -d "/sys/class/net/$INTERFACE" ]; do
  sleep 0.5
  let timeout=timeout-1
  if [ $timeout -le 0 ]; then
    echo -e "\e[33m[!] Note: $INTERFACE did not re-initialize via ath9k_htc. If using a different chip, verify with 'ip link'.\e[0m"
    break
  fi
done

if [ -d "/sys/class/net/$INTERFACE" ]; then
  echo -e "\e[34m[*] 4. Applying stability tweaks to $INTERFACE...\e[0m"
  ip link set "$INTERFACE" down 2>/dev/null || true
  iw dev "$INTERFACE" set power_save off 2>/dev/null || true
  iw dev "$INTERFACE" set txpower limit 1500 2>/dev/null || true
  ip link set "$INTERFACE" up 2>/dev/null || true

  echo -e "\e[34m[*] 5. Setting $INTERFACE to unmanaged in NetworkManager...\e[0m"
  nmcli device set "$INTERFACE" managed no 2>/dev/null || true
fi

echo -e "\e[32m[+] Adapter preparation complete.\e[0m"
