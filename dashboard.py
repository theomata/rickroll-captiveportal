#!/usr/bin/env bash
#!/usr/bin/env python3

import curses
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

# Base Directory Resolution
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Global State
class LabState:
    def __init__(self):
        self.running = True
        self.start_time = time.time()
        self.ssid = "Free_Wifi"
        self.channel = "6"
        self.interface = "wlan0"
        self.gateway = "10.13.37.1"

        # Service statuses: "STARTING", "RUNNING", "STOPPED", "ERROR"
        self.services = {
            "hostapd": "STOPPED",
            "dnsmasq": "STOPPED",
            "portal": "STOPPED"
        }

        # Clients: mac -> {ip, mac, hostname, status, details, time}
        self.clients = {}
        self.rickrolled_ips = set()
        self.victim_count = 0

        # Logs: list of (timestamp, tag, message, level)
        self.logs = []
        self.log_lock = threading.Lock()
        self.log_scroll_offset = 0

state = LabState()
subprocesses = {}

# ------------------------------------------------------------
# Logging & Event Parsing
# ------------------------------------------------------------
def add_log(tag, message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    with state.log_lock:
        state.logs.append((timestamp, tag, message, level))
        if len(state.logs) > 300:
            state.logs.pop(0)

def read_stream(proc, name):
    for raw_line in iter(proc.stdout.readline, ''):
        if not state.running:
            break
        line = raw_line.strip()
        if not line:
            continue
        parse_service_output(name, line)
    proc.stdout.close()

def parse_service_output(service, line):
    # ------------------ Hostapd ------------------
    if service == "hostapd":
        sta_connect = re.search(r"AP-STA-CONNECTED\s+([0-9a-fA-F:]{17})", line)
        sta_disconnect = re.search(r"AP-STA-DISCONNECTED\s+([0-9a-fA-F:]{17})", line)
        if sta_connect:
            mac = sta_connect.group(1).lower()
            if mac not in state.clients:
                state.clients[mac] = {
                    "ip": "10.13.37.?",
                    "mac": mac,
                    "hostname": "Unknown Device",
                    "status": "Connected",
                    "details": "-",
                    "time": datetime.now().strftime("%H:%M:%S")
                }
            else:
                state.clients[mac]["status"] = "Connected"
            add_log("AP", f"Device connected: {mac}", "SUCCESS")
            return
        elif sta_disconnect:
            mac = sta_disconnect.group(1).lower()
            if mac in state.clients:
                state.clients[mac]["status"] = "Disconnected"
            add_log("AP", f"Device disconnected: {mac}", "WARN")
            return
        elif "AP-ENABLED" in line:
            state.services["hostapd"] = "RUNNING"
            add_log("AP", "Access Point enabled and broadcasting", "SUCCESS")
            return

    # ------------------ Dnsmasq ------------------
    elif service == "dnsmasq":
        dhcpack = re.search(r"DHCPACK\([^)]+\)\s+(10\.13\.37\.[0-9]+)\s+([0-9a-fA-F:]{17})(?:\s+(.*))?", line)
        if dhcpack:
            ip = dhcpack.group(1)
            mac = dhcpack.group(2).lower()
            raw_host = dhcpack.group(3) or "Unknown Device"
            # Strip MAC if duplicated in hostname field
            hostname = raw_host.split("(")[0].strip() or "Unknown Device"

            if mac in state.clients:
                state.clients[mac]["ip"] = ip
                state.clients[mac]["hostname"] = hostname
                if state.clients[mac]["status"] == "Connected":
                    state.clients[mac]["status"] = "Leased"
            else:
                state.clients[mac] = {
                    "ip": ip,
                    "mac": mac,
                    "hostname": hostname,
                    "status": "Leased",
                    "details": "-",
                    "time": datetime.now().strftime("%H:%M:%S")
                }
            add_log("DHCP", f"Leased {ip} -> {hostname} ({mac})", "SUCCESS")
            return
        elif "started, version" in line:
            state.services["dnsmasq"] = "RUNNING"
            add_log("DNS", "DHCP/DNS server initialized", "SUCCESS")
            return

    # ------------------ Portal ------------------
    elif service == "portal":
        if "Listening on" in line or "Starting Rickroll" in line:
            state.services["portal"] = "RUNNING"
            add_log("PORTAL", "Captive portal HTTP server ready on :80", "SUCCESS")
            return
        elif "Victim #" in line or "Rickrolled!" in line or "Rickrolled client:" in line:
            ip_match = re.search(r"(10\.13\.37\.[0-9]+)", line)
            device_match = re.search(r"\(([^)]+)\)", line)
            if ip_match:
                ip = ip_match.group(1)
                if ip not in state.rickrolled_ips:
                    state.rickrolled_ips.add(ip)
                    state.victim_count = len(state.rickrolled_ips)
                for client in state.clients.values():
                    if client["ip"] == ip:
                        client["status"] = "Rickrolled! 🎉"
                        if device_match:
                            client["details"] = device_match.group(1)
            else:
                state.victim_count += 1

            clean_msg = line.replace("[🎉]", "").strip()
            add_log("🎉 HIT", clean_msg, "HIT")
            return
        elif "POST /connect" in line:
            ip_match = re.search(r"^(\d+\.\d+\.\d+\.\d+)", line)
            if ip_match:
                ip = ip_match.group(1)
                if ip not in state.rickrolled_ips:
                    state.rickrolled_ips.add(ip)
                    state.victim_count = len(state.rickrolled_ips)
                for client in state.clients.values():
                    if client["ip"] == ip:
                        client["status"] = "Rickrolled! 🎉"
                add_log("🎉 HIT", f"Victim {ip} clicked Connect!", "HIT")
            return
        elif "generate_204" in line or "hotspot-detect" in line or "ncsi.txt" in line or "connecttest" in line:
            ip_match = re.search(r"^(\d+\.\d+\.\d+\.\d+)", line)
            src_ip = ip_match.group(1) if ip_match else "Client"
            add_log("PROBE", f"Captive portal probe from {src_ip}", "INFO")
            return
        elif "GET / " in line or "GET / HTTP" in line:
            ip_match = re.search(r"^(\d+\.\d+\.\d+\.\d+)", line)
            src_ip = ip_match.group(1) if ip_match else "Client"
            add_log("PORTAL", f"Served landing page to {src_ip}", "INFO")
            return

    # Fallback to general error capture
    if any(k in line.lower() for k in ["error", "fatal", "failed to bind"]):
        add_log(service.upper(), line, "ERROR")

# ------------------------------------------------------------
# Subprocess Management
# ------------------------------------------------------------
def parse_config_values():
    hostapd_conf = os.path.join(BASE_DIR, "hostapd.conf")
    if os.path.exists(hostapd_conf):
        with open(hostapd_conf, "r") as f:
            for line in f:
                if line.startswith("ssid="):
                    state.ssid = line.split("=", 1)[1].strip()
                elif line.startswith("channel="):
                    state.channel = line.split("=", 1)[1].strip()
                elif line.startswith("interface="):
                    state.interface = line.split("=", 1)[1].strip()

def start_services():
    parse_config_values()
    add_log("INIT", f"Initializing on {state.interface} (SSID: {state.ssid}, Ch: {state.channel})", "INFO")

    # Step 1: Run network setup
    setup_script = os.path.join(BASE_DIR, "setup-network.sh")
    if os.path.exists(setup_script):
        add_log("NET", "Configuring network interfaces and routing...", "INFO")
        ret = subprocess.call(["sudo", setup_script, state.interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ret != 0:
            add_log("NET", "Network setup script encountered an error", "ERROR")
        else:
            add_log("NET", "Network infrastructure configured successfully", "SUCCESS")

    # Step 2: Spawn hostapd
    hostapd_conf = os.path.join(BASE_DIR, "hostapd.conf")
    state.services["hostapd"] = "STARTING"
    proc_ap = subprocess.Popen(
        ["sudo", "hostapd", hostapd_conf],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=BASE_DIR
    )
    subprocesses["hostapd"] = proc_ap
    t_ap = threading.Thread(target=read_stream, args=(proc_ap, "hostapd"), daemon=True)
    t_ap.start()

    # Step 3: Spawn dnsmasq
    dnsmasq_conf = os.path.join(BASE_DIR, "dnsmasq.conf")
    state.services["dnsmasq"] = "STARTING"
    proc_dns = subprocess.Popen(
        ["sudo", "dnsmasq", f"--conf-file={dnsmasq_conf}", "--no-daemon"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=BASE_DIR
    )
    subprocesses["dnsmasq"] = proc_dns
    t_dns = threading.Thread(target=read_stream, args=(proc_dns, "dnsmasq"), daemon=True)
    t_dns.start()

    # Step 4: Spawn portal.py (unbuffered via -u and PYTHONUNBUFFERED=1)
    portal_script = os.path.join(BASE_DIR, "portal.py")
    state.services["portal"] = "STARTING"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc_portal = subprocess.Popen(
        ["sudo", sys.executable, "-u", portal_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=BASE_DIR,
        env=env
    )
    subprocesses["portal"] = proc_portal
    t_portal = threading.Thread(target=read_stream, args=(proc_portal, "portal"), daemon=True)
    t_portal.start()

def stop_services():
    state.running = False
    add_log("SHUTDOWN", "Stopping all services...", "WARN")
    for name, proc in subprocesses.items():
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    kill_script = os.path.join(BASE_DIR, "kill.sh")
    if os.path.exists(kill_script):
        subprocess.call(["sudo", kill_script, state.interface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ------------------------------------------------------------
# TUI Curses Interface
# ------------------------------------------------------------
def safe_addstr(stdscr, y, x, text, attr=0):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass

def draw_dashboard(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.use_default_colors()

    # Color definitions
    if curses.has_colors():
        curses.init_pair(1, curses.COLOR_GREEN, -1)   # Success / Running / Hit
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # Warnings / Connecting
        curses.init_pair(3, curses.COLOR_RED, -1)     # Errors / Disconnected
        curses.init_pair(4, curses.COLOR_CYAN, -1)    # Frame borders / Headers
        curses.init_pair(5, curses.COLOR_MAGENTA, -1) # Counters / Hits
        curses.init_pair(6, curses.COLOR_WHITE, -1)   # Standard labels

    c_green = curses.color_pair(1) | curses.A_BOLD
    c_yellow = curses.color_pair(2) | curses.A_BOLD
    c_red = curses.color_pair(3) | curses.A_BOLD
    c_cyan = curses.color_pair(4) | curses.A_BOLD
    c_magenta = curses.color_pair(5) | curses.A_BOLD
    c_white = curses.color_pair(6)
    c_dim = curses.A_DIM

    start_services()

    while state.running:
        try:
            ch = stdscr.getch()
            if ch in [ord('q'), ord('Q'), 27]: # 'q' or ESC
                break
            elif ch in [ord('c'), ord('C')]:
                with state.log_lock:
                    state.logs.clear()
            elif ch == curses.KEY_UP:
                state.log_scroll_offset = min(state.log_scroll_offset + 1, max(0, len(state.logs) - 5))
            elif ch == curses.KEY_DOWN:
                state.log_scroll_offset = max(0, state.log_scroll_offset - 1)
        except Exception:
            pass

        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Minimum dimensions guard
        if h < 20 or w < 72:
            safe_addstr(stdscr, 0, 0, f"Terminal window too small ({w}x{h}).", c_yellow)
            safe_addstr(stdscr, 1, 0, "Please resize to at least 76x22.", c_white)
            stdscr.refresh()
            time.sleep(0.2)
            continue

        inner_w = w - 2 # width inside vertical borders

        # ----------------------------------------------------
        # 1. Top Border with Title
        # ----------------------------------------------------
        title = " RICKROLL CAPTIVE PORTAL LAB "
        fill_top = max(0, inner_w - len(title) - 2)
        top_bar = "┌─" + title + ("─" * fill_top) + "┐"
        safe_addstr(stdscr, 0, 0, top_bar[:w - 1], c_cyan)

        # ----------------------------------------------------
        # 2. Network Parameters Line
        # ----------------------------------------------------
        net_text = f" SSID: {state.ssid:<18} Channel: {state.channel:<4} Gateway: {state.gateway:<15} Dev: {state.interface}"
        safe_addstr(stdscr, 1, 0, "│", c_cyan)
        safe_addstr(stdscr, 1, 2, f"{net_text:<{inner_w - 2}}"[:inner_w - 2], c_white)
        safe_addstr(stdscr, 1, w - 2, "│", c_cyan)

        # ----------------------------------------------------
        # 3. Service Status Health Line
        # ----------------------------------------------------
        ap_st = state.services.get("hostapd", "STOPPED")
        dns_st = state.services.get("dnsmasq", "STOPPED")
        prt_st = state.services.get("portal", "STOPPED")

        ap_c = c_green if ap_st == "RUNNING" else c_yellow if ap_st == "STARTING" else c_red
        dns_c = c_green if dns_st == "RUNNING" else c_yellow if dns_st == "STARTING" else c_red
        prt_c = c_green if prt_st == "RUNNING" else c_yellow if prt_st == "STARTING" else c_red

        safe_addstr(stdscr, 2, 0, "│", c_cyan)
        safe_addstr(stdscr, 2, 2, " Services:  ", c_white)
        x_pos = 14
        safe_addstr(stdscr, 2, x_pos, f"● Hostapd [{ap_st}]", ap_c)
        x_pos += len(f"● Hostapd [{ap_st}]") + 3
        safe_addstr(stdscr, 2, x_pos, f"● Dnsmasq [{dns_st}]", dns_c)
        x_pos += len(f"● Dnsmasq [{dns_st}]") + 3
        safe_addstr(stdscr, 2, x_pos, f"● Portal:80 [{prt_st}]", prt_c)
        safe_addstr(stdscr, 2, w - 2, "│", c_cyan)

        # ----------------------------------------------------
        # 4. Live Statistics Bar
        # ----------------------------------------------------
        uptime_sec = int(time.time() - state.start_time)
        uptime_str = f"{uptime_sec // 3600:02d}:{(uptime_sec % 3600) // 60:02d}:{uptime_sec % 60:02d}"
        active_count = sum(1 for c in state.clients.values() if c["status"] != "Disconnected")

        safe_addstr(stdscr, 3, 0, "│", c_cyan)
        safe_addstr(stdscr, 3, 2, f" Active Devices: {active_count:<6}", c_white)
        safe_addstr(stdscr, 3, 26, f"🎉 Total Rickrolls: {state.victim_count:<6}", c_magenta)
        safe_addstr(stdscr, 3, 56, f"⏱ Uptime: {uptime_str}", c_white)
        safe_addstr(stdscr, 3, w - 2, "│", c_cyan)

        # ----------------------------------------------------
        # 5. Middle Section: Connected Clients Box
        # ----------------------------------------------------
        client_count = len(state.clients)
        mid_title1 = f" CONNECTED CLIENTS ({client_count}) "
        fill_mid1 = max(0, inner_w - len(mid_title1) - 2)
        safe_addstr(stdscr, 4, 0, "├─" + mid_title1 + ("─" * fill_mid1) + "┤", c_cyan)

        # Table Column Headers
        col_hdr = f"  {'IP ADDRESS':<16} {'MAC ADDRESS':<18} {'DEVICE / HOSTNAME':<24} {'STATUS':<15}"
        safe_addstr(stdscr, 5, 0, "│", c_cyan)
        safe_addstr(stdscr, 5, 1, f"{col_hdr:<{inner_w}}"[:inner_w], curses.A_UNDERLINE | c_white)
        safe_addstr(stdscr, 5, w - 2, "│", c_cyan)

        # Render Client Rows (up to 4 recent)
        client_rows = list(state.clients.values())[-4:]
        cur_y = 6
        for c in client_rows:
            st = c["status"]
            st_color = c_green if "Rickrolled" in st else c_yellow if st in ["Connected", "Leased"] else c_red
            safe_addstr(stdscr, cur_y, 0, "│", c_cyan)
            client_prefix = f"  {c['ip']:<16} {c['mac']:<18} {c['hostname'][:22]:<24} "
            safe_addstr(stdscr, cur_y, 1, client_prefix[:inner_w - 18], c_white)
            safe_addstr(stdscr, cur_y, len(client_prefix) + 1, f"{st:<16}"[:inner_w - len(client_prefix) - 2], st_color)
            safe_addstr(stdscr, cur_y, w - 2, "│", c_cyan)
            cur_y += 1

        # Fill remaining blank client rows if fewer than 3
        while cur_y < 9:
            safe_addstr(stdscr, cur_y, 0, "│", c_cyan)
            if not client_rows and cur_y == 7:
                safe_addstr(stdscr, cur_y, 4, "Awaiting clients... Broadcast is live on " + state.ssid, c_dim)
            safe_addstr(stdscr, cur_y, w - 2, "│", c_cyan)
            cur_y += 1

        # ----------------------------------------------------
        # 6. Activity Feed Divider
        # ----------------------------------------------------
        mid_title2 = " LIVE ACTIVITY FEED "
        fill_mid2 = max(0, inner_w - len(mid_title2) - 2)
        safe_addstr(stdscr, 9, 0, "├─" + mid_title2 + ("─" * fill_mid2) + "┤", c_cyan)

        # ----------------------------------------------------
        # 7. Render Scrollable Activity Feed
        # ----------------------------------------------------
        log_start_y = 10
        log_avail_h = h - log_start_y - 2

        with state.log_lock:
            logs_copy = list(state.logs)

        if logs_copy and log_avail_h > 0:
            if state.log_scroll_offset > 0:
                logs_copy = logs_copy[:-state.log_scroll_offset]
            visible_logs = logs_copy[-log_avail_h:]

            for i, (ts, tag, msg, lvl) in enumerate(visible_logs):
                y = log_start_y + i
                if y >= h - 2:
                    break
                tag_c = (
                    c_green if lvl == "SUCCESS"
                    else c_magenta if lvl == "HIT"
                    else c_red if lvl == "ERROR"
                    else c_yellow if lvl == "WARN"
                    else c_cyan
                )
                safe_addstr(stdscr, y, 0, "│", c_cyan)
                log_prefix = f"  [{ts}] [{tag:<7}] "
                safe_addstr(stdscr, y, 1, log_prefix, tag_c)
                msg_x = len(log_prefix) + 1
                max_msg_len = inner_w - msg_x - 1
                if max_msg_len > 0:
                    safe_addstr(stdscr, y, msg_x, msg[:max_msg_len], c_white)
                safe_addstr(stdscr, y, w - 2, "│", c_cyan)

        # Blank padding for unused log rows
        rendered_logs = len(visible_logs) if logs_copy and log_avail_h > 0 else 0
        for y_pad in range(log_start_y + rendered_logs, h - 2):
            safe_addstr(stdscr, y_pad, 0, "│", c_cyan)
            safe_addstr(stdscr, y_pad, w - 2, "│", c_cyan)

        # ----------------------------------------------------
        # 8. Bottom Frame with Shortcut Keys
        # ----------------------------------------------------
        footer_keys = " [Q] Quit Lab  [C] Clear Log  [↑/↓] Scroll History "
        fill_bottom = max(0, inner_w - len(footer_keys) - 2)
        bottom_bar = "└─" + footer_keys + ("─" * fill_bottom) + "┘"
        safe_addstr(stdscr, h - 2, 0, bottom_bar[:w - 1], c_cyan)

        stdscr.refresh()
        time.sleep(0.15)

def main():
    def sig_handler(sig, frame):
        state.running = False
    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        curses.wrapper(draw_dashboard)
    except KeyboardInterrupt:
        pass
    finally:
        stop_services()
        print("\n" + "=" * 55)
        print("  Rickroll Portal Lab Stopped Cleanly")
        print(f"  Total Rickrolled Victims: {state.victim_count}")
        print("  Network interfaces and iptables rules restored.")
        print("=" * 55 + "\n")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("[-] Error: Root privileges required for network interfaces.")
        print("[+] Please run with: sudo python3 dashboard.py")
        sys.exit(1)
    main()
