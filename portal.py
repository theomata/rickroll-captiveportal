#!/usr/bin/env python3

import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOST = "0.0.0.0"
PORT = 80

TOTAL_VICTIMS = 0
UNIQUE_CLIENTS = set()

PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connect to Wi-Fi</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><text y='20' font-size='20'>🎵</text></svg>">
<style>
:root{color-scheme:dark;--bg:#0b0b0c;--panel:#141416;--border:#29292d;--text:#f5f5f5;--muted:#a1a1aa;--button:#f5f5f5;--button-text:#111113}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;padding:24px;display:grid;place-items:center;background:var(--bg);color:var(--text);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.card{width:100%;max-width:360px;padding:32px 28px;text-align:center;background:var(--panel);border:1px solid var(--border);border-radius:12px}
.status{width:48px;height:48px;margin:0 auto 24px;display:grid;place-items:center;color:var(--text);border:1px solid #39393f;border-radius:50%}
.status svg{width:22px;height:22px}
h1{margin:0 0 10px;font-size:21px;line-height:1.3;font-weight:600;letter-spacing:-.025em}
p{margin:0;color:var(--muted);font-size:14px;line-height:1.6}
.connect{width:100%;min-height:44px;margin-top:26px;padding:0 18px;border:0;border-radius:7px;background:var(--button);color:var(--button-text);font:inherit;font-size:14px;font-weight:600;cursor:pointer}
.connect:hover{background:#dedee2}
.connect:focus-visible{outline:2px solid #fff;outline-offset:3px}
#rickrollScreen{position:fixed;inset:0;z-index:10;display:none;overflow:hidden;background:#000}
#rickrollScreen.active{display:flex;align-items:center;justify-content:center}
#rickrollBackground{position:absolute;inset:0;z-index:0;display:block;width:100%;height:100%;object-fit:cover}
#overlayFrame{
    position:relative;
    z-index:1;
    width:min(82vw, 760px);
    max-height:82vh;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:0;
    overflow:hidden;
    border:1px solid rgba(255,255,255,.32);
    border-radius:10px;
    background:rgba(0,0,0,.16);
    box-shadow:0 18px 60px rgba(0,0,0,.45)
}
#overlayImage{
    display:block;
    width:100%;
    height:auto;
    max-width:100%;
    max-height:82vh;
    object-fit:contain
}
@media(max-width:420px){.card{padding:28px 22px}}
</style>
</head>
<body>
<main class="card" id="connectCard">
<div class="status" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 10.5a11 11 0 0 1 14 0"></path><path d="M8.5 14a5.5 5.5 0 0 1 7 0"></path><path d="M12 18h.01"></path></svg></div>
<h1>Connect to Wi-Fi</h1>
<p>Connect to the network to continue.</p>
<button class="connect" id="connectButton" type="button" onclick="connectToNetwork()">Connect</button>
</main>
<section id="rickrollScreen" aria-label="Connected">
<img id="rickrollBackground" src="/rickroll.gif" alt="" aria-hidden="true">
<div id="overlayFrame"><img id="overlayImage" src="/overlay.png" alt=""></div>
</section>
<audio id="rickrollAudio" src="/rickroll.mp3" preload="auto" loop></audio>
<script>
async function connectToNetwork(){
 const button=document.getElementById('connectButton');
 button.disabled=true;
 button.textContent='Connecting…';
 const audio=document.getElementById('rickrollAudio');
 // Trigger audio playback immediately within the user gesture
 const playPromise=audio.play();
 try{
  await fetch('/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'connect'})});
 }catch(err){
  console.warn('Connect request notice:',err);
 }
 document.getElementById('connectCard').style.display='none';
 document.getElementById('rickrollScreen').classList.add('active');
 if(playPromise!==undefined){
  playPromise.catch(function(audioError){
   console.warn('Audio playback was blocked:',audioError);
  });
 }
}
</script>
</body>
</html>
"""


def parse_user_agent(ua):
    os_name = "Unknown OS"
    browser_name = "Unknown Browser"
    device_type = "Desktop"

    if "Android" in ua:
        os_name = "Android"
        device_type = "Mobile"
    elif "iPhone" in ua:
        os_name = "iOS (iPhone)"
        device_type = "Mobile"
    elif "iPad" in ua:
        os_name = "iOS (iPad)"
        device_type = "Tablet"
    elif "Windows NT 10.0" in ua:
        os_name = "Windows 10/11"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    elif "CrOS" in ua:
        os_name = "Chrome OS"

    if "Edg/" in ua:
        browser_name = "Edge"
    elif "Chrome/" in ua and "Safari/" in ua:
        browser_name = "Chrome"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser_name = "Safari"
    elif "Firefox/" in ua:
        browser_name = "Firefox"
    elif "OPR/" in ua or "Opera" in ua:
        browser_name = "Opera"

    return os_name, browser_name, device_type


class CaptivePortalHandler(BaseHTTPRequestHandler):

    server_version = "RickrollPortal/1.0"

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.client_address[0], format_string % args), flush=True)

    def send_html(self, status=200):
        body = PORTAL_HTML.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        return body

    def redirect_to_portal(self):
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_HEAD(self):
        self.send_html()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Silently satisfy favicon queries without redirection loops
        if path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Connection", "close")
            self.end_headers()
            return

        # Standard OS Captive Portal Probe Detection URLs
        probe_paths = (
            "/generate_204",
            "/gen_204",
            "/hotspot-detect.html",
            "/connecttest.txt",
            "/ncsi.txt",
            "/success.txt",
            "/canonical.html",
            "/library/test/success.html",
            "/ipv6/connecttest.txt",
        )

        if path in probe_paths:
            self.redirect_to_portal()
            return

        if path == "/":
            body = self.send_html()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        # Serve static media files (e.g. overlay.png, rickroll.gif, rickroll.mp3)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        rel_path = path.lstrip("/")
        filename = os.path.abspath(os.path.join(script_dir, rel_path))

        # Ensure requested path stays within the script directory
        if filename.startswith(script_dir) and os.path.isfile(filename):
            ext = os.path.splitext(filename)[1].lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
                ".gif": "image/gif",
                ".mp3": "audio/mpeg",
                ".mp4": "video/mp4",
                ".webp": "image/webp",
            }
            content_type = mime_types.get(ext, "application/octet-stream")
            try:
                with open(filename, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=3600")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)
                return
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as e:
                print(f"[-] Error serving static file {filename}: {e}")

        # Redirect any unknown paths back to portal landing page
        self.redirect_to_portal()

    def do_POST(self):
        global TOTAL_VICTIMS, UNIQUE_CLIENTS
        parsed = urlparse(self.path)
        if parsed.path == "/connect":
            client_ip = self.client_address[0]
            TOTAL_VICTIMS += 1
            UNIQUE_CLIENTS.add(client_ip)

            user_agent = self.headers.get("User-Agent", "Unknown")
            os_name, browser_name, device_type = parse_user_agent(user_agent)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[🎉] [{now}] Victim #{TOTAL_VICTIMS} Rickrolled! IP: {client_ip} ({os_name} | {browser_name} | {device_type}) | Unique Victims: {len(UNIQUE_CLIENTS)}", flush=True)

            response_body = json.dumps({"status": "success"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(response_body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self.redirect_to_portal()


def main():
    print("[+] Starting Rickroll Captive Portal Server...", flush=True)

    server = ThreadingHTTPServer((HOST, PORT), CaptivePortalHandler)
    server.allow_reuse_address = True

    print(f"[+] Listening on {HOST}:{PORT}", flush=True)
    print("[+] Open http://localhost/ or http://127.0.0.1/ in your browser", flush=True)
    print("[+] Press Ctrl+C to stop.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Stopping server...")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
