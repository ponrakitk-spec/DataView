"""Start the local worker and an authenticated HTTPS connection for the web app."""
from __future__ import annotations
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".dataview"
SITE = "https://dataview-one.vercel.app"
LOCAL = "http://127.0.0.1:8765"

def request(url, token, method="GET"):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token}, method=method)
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.load(response)

def open_site(connection):
    fragment = urllib.parse.urlencode({"worker": connection["worker"], "key": connection["key"]})
    webbrowser.open(SITE + "/#" + fragment)

def main():
    parser = argparse.ArgumentParser(description="Start DataView's local Chrome worker")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    STATE.mkdir(exist_ok=True)
    token_file, connection_file = STATE / "access.token", STATE / "connection.json"
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(36), encoding="utf-8")
    token = token_file.read_text().strip()
    if args.stop:
        try:
            request(LOCAL + "/shutdown", token, "POST")
            print("Stopping DataView worker and its connection.", flush=True)
        except (OSError, ValueError):
            print("DataView worker is already stopped.", flush=True)
        return
    try:
        health = request(LOCAL + "/health", token)
        if health.get("status") == "online":
            if not connection_file.exists():
                raise RuntimeError("Worker is starting. Wait a moment and try again.")
            connection = json.loads(connection_file.read_text())
            try:
                request(connection["worker"] + "/health", token)
            except OSError:
                raise RuntimeError("The connection is offline. Run Stop-DataView.ps1, then Start-DataView.ps1 again.") from None
            if not args.no_browser: open_site(connection)
            print("DataView is already connected. Keep the original worker running.", flush=True)
            return
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        pass
    import selenium  # fail early, before starting a tunnel, if requirements are missing
    del selenium
    binary = STATE / "cloudflared.exe"
    if not binary.exists():
        print("Downloading cloudflared from the official Cloudflare release...", flush=True)
        temporary = binary.with_suffix(".download")
        urllib.request.urlretrieve("https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe", temporary)
        temporary.replace(binary)
    hidden = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    worker_log = (STATE / "worker.log").open("a", encoding="utf-8")
    tunnel_log = (STATE / "tunnel.log").open("w", encoding="utf-8")
    worker = tunnel = None
    try:
        worker = subprocess.Popen([sys.executable, "-u", str(ROOT / "worker" / "server.py")], cwd=ROOT, stdout=worker_log, stderr=subprocess.STDOUT, creationflags=hidden)
        for _ in range(30):
            if worker.poll() is not None: raise RuntimeError("Worker stopped. See .dataview/worker.log.")
            try:
                request(LOCAL + "/health", token)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Worker did not start.")
        tunnel = subprocess.Popen([str(binary), "tunnel", "--no-autoupdate", "--url", LOCAL], cwd=ROOT, stdout=tunnel_log, stderr=subprocess.STDOUT, creationflags=hidden)
        worker_url = None
        until = time.monotonic() + 90
        while time.monotonic() < until:
            if tunnel.poll() is not None: raise RuntimeError("Connection stopped. See .dataview/tunnel.log.")
            text = (STATE / "tunnel.log").read_text(encoding="utf-8", errors="replace")
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
            if match:
                worker_url = match[0]
                try:
                    request(worker_url + "/health", token)
                    break
                except OSError:
                    pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Could not establish an HTTPS connection. See .dataview/tunnel.log.")
        connection = {"worker": worker_url, "key": token}
        connection_file.write_text(json.dumps(connection), encoding="utf-8")
        print("DataView connected. Website: " + SITE, flush=True)
        print("Connection details saved privately in .dataview/connection.json.", flush=True)
        print("Keep this program and your computer running. Press Ctrl+C to stop.", flush=True)
        if not args.no_browser: open_site(connection)
        while worker.poll() is None and tunnel.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping DataView...", flush=True)
    finally:
        if worker and worker.poll() is None:
            try: request(LOCAL + "/shutdown", token, "POST")
            except OSError: pass
            try: worker.wait(timeout=40)
            except subprocess.TimeoutExpired: worker.terminate()
        if tunnel and tunnel.poll() is None:
            tunnel.terminate()
            try: tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired: tunnel.kill()
        worker_log.close()
        tunnel_log.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"DataView startup failed: {error}", file=sys.stderr)
        sys.exit(1)
