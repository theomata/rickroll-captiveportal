#!/usr/bin/env bash

# Resolve project base directory dynamically (independent of where script is invoked)
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="rickroll"

# Default configuration values
SSID="Free_Wifi"
CHANNEL="6"
INTERFACE="wlan0"
MODE="tui"
FORCE_RESTART=false

# ------------------------------------------------------------
# Parse CLI Options
# ------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--ssid)
            SSID="$2"
            shift 2
            ;;
        -c|--channel)
            CHANNEL="$2"
            shift 2
            ;;
        -i|--interface)
            INTERFACE="$2"
            shift 2
            ;;
        --tui)
            MODE="tui"
            shift
            ;;
        --tmux)
            MODE="tmux"
            shift
            ;;
        -r|--restart)
            FORCE_RESTART=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo
            echo "Options:"
            echo "  -s, --ssid <name>      Set Wi-Fi network SSID (default: Free_Wifi)"
            echo "  -c, --channel <num>    Set Wi-Fi channel (default: 6)"
            echo "  -i, --interface <dev>  Set wireless interface (default: wlan0)"
            echo "  --tui                  Launch unified TUI dashboard (Default)"
            echo "  --tmux                 Launch in 3-pane tmux session"
            echo "  -r, --restart          Restart active session without prompting"
            echo "  -h, --help             Show this help menu"
            exit 0
            ;;
        *)
            echo "[!] Unknown option: $1"
            echo "Run '$0 --help' for available options."
            exit 1
            ;;
    esac
done

echo "=============================================="
echo "          RICKROLL CAPTIVE PORTAL             "
echo "=============================================="
echo " Mode:      $MODE"
echo " SSID:      $SSID"
echo " Channel:   $CHANNEL"
echo " Interface: $INTERFACE"
echo "=============================================="
echo

# ------------------------------------------------------------
# 1. Dependency Check
# ------------------------------------------------------------
REQUIRED_PKGS=(hostapd dnsmasq python3 iptables iw)
if [ "$MODE" = "tmux" ]; then
    REQUIRED_PKGS+=(tmux)
fi

MISSING_PKGS=()
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! command -v "$pkg" >/dev/null 2>&1; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "[!] Missing required dependencies: ${MISSING_PKGS[*]}"
    echo "[+] Install them with:"
    echo
    echo "    sudo apt update && sudo apt install -y ${MISSING_PKGS[*]}"
    echo
    exit 1
fi

# ------------------------------------------------------------
# 2. Check Sudo Privileges Early
# ------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    echo "[*] Validating root privileges..."
    sudo -v || exit 1
fi

# ------------------------------------------------------------
# 3. Synchronize Configuration Files
# ------------------------------------------------------------
if [ -f "$BASE/hostapd.conf" ]; then
    sed -i "s/^ssid=.*/ssid=$SSID/" "$BASE/hostapd.conf"
    sed -i "s/^channel=.*/channel=$CHANNEL/" "$BASE/hostapd.conf"
    sed -i "s/^interface=.*/interface=$INTERFACE/" "$BASE/hostapd.conf"
fi

if [ -f "$BASE/dnsmasq.conf" ]; then
    sed -i "s/^interface=.*/interface=$INTERFACE/" "$BASE/dnsmasq.conf"
fi

# ------------------------------------------------------------
# 4. Launch in Selected Mode
# ------------------------------------------------------------

if [ "$MODE" = "tui" ]; then
    echo "[+] Launching Unified TUI Dashboard..."
    sudo python3 "$BASE/dashboard.py"
    exit 0
fi

# Tmux Mode
if tmux has-session -t "$SESSION" 2>/dev/null; then
    if [ "$FORCE_RESTART" = true ]; then
        echo "[*] Force restarting existing tmux session..."
        "$BASE/kill.sh" "$INTERFACE" >/dev/null 2>&1
        sleep 1
    else
        echo "[!] Rickroll tmux session is already running."
        echo "    - Attach to session: tmux attach -t $SESSION"
        echo "    - Restart fresh:     $0 --tmux --restart"
        echo "    - Stop lab:          $BASE/kill.sh"
        echo
        read -p "[?] Kill existing session and restart? [Y/n] " -r REPLY
        echo
        if [[ "$REPLY" =~ ^[Nn]$ ]]; then
            echo "[+] Attaching to existing session..."
            tmux attach-session -t "$SESSION"
            exit 0
        else
            echo "[*] Resetting stale session..."
            "$BASE/kill.sh" "$INTERFACE" >/dev/null 2>&1
            sleep 1
        fi
    fi
fi

echo "[+] Initializing network configuration on $INTERFACE..."
sudo "$BASE/setup-network.sh" "$INTERFACE"
if [ $? -ne 0 ]; then
    echo "[!] Network setup failed. Aborting."
    exit 1
fi

echo "[+] Starting tmux management console..."
sleep 1

tmux new-session -d -s "$SESSION" -n "Rickroll Lab"

# Pane 0: HOSTAPD
tmux send-keys -t "$SESSION:0.0" \
    "printf '\\033]0;Rickroll - HOSTAPD\\007'; cd '$BASE'; sudo hostapd '$BASE/hostapd.conf'" \
    C-m

# Pane 1: DNSMASQ
tmux split-window -h -t "$SESSION:0"
tmux send-keys -t "$SESSION:0.1" \
    "printf '\\033]0;Rickroll - DNSMASQ\\007'; cd '$BASE'; sudo dnsmasq --conf-file='$BASE/dnsmasq.conf' --no-daemon" \
    C-m

# Pane 2: PORTAL
tmux split-window -v -t "$SESSION:0.1"
tmux send-keys -t "$SESSION:0.2" \
    "printf '\\033]0;Rickroll - PORTAL\\007'; cd '$BASE'; sudo python3 '$BASE/portal.py'" \
    C-m

# Layout adjustments
tmux resize-pane -t "$SESSION:0.2" -y 14
tmux select-pane -t "$SESSION:0.0" -T "HOSTAPD"
tmux select-pane -t "$SESSION:0.1" -T "DNSMASQ"
tmux select-pane -t "$SESSION:0.2" -T "PORTAL"

tmux set-option -t "$SESSION" pane-border-status top
tmux set-option -t "$SESSION" pane-border-format " #[bold]#P #T #[default]"
tmux set-option -t "$SESSION" pane-border-style "fg=colour240"
tmux set-option -t "$SESSION" pane-active-border-style "fg=colour208"

tmux select-pane -t "$SESSION:0.0"

echo
echo "=============================================="
echo "          Rickroll Portal is Active!          "
echo "=============================================="
echo " Network: $SSID (Ch $CHANNEL on $INTERFACE)"
echo " Session: $SESSION"
echo
echo " Panes:"
echo "   [0] HOSTAPD  (Access Point)"
echo "   [1] DNSMASQ  (DHCP / DNS)"
echo "   [2] PORTAL   (Captive Portal Web Server)"
echo
echo " Shortcuts inside tmux:"
echo "   Ctrl+B then Arrow Keys : Switch panes"
echo "   Ctrl+B then Z          : Zoom / Unzoom active pane"
echo "   Ctrl+B then D          : Detach from session"
echo
echo " To stop everything:"
echo "   ./kill.sh"
echo "=============================================="
echo

tmux attach-session -t "$SESSION"
