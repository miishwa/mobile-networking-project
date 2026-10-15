#!/usr/bin/env python3
"""Raspberry Pi Wi-Fi sensor (Member A). Standard library only - nothing to pip install.
 
Usage:
  python3 sensor.py --location "Library" --server http://192.168.x.x:5000
  python3 sensor.py --location "Library" --mock        # fake data, works on any laptop
  python3 sensor.py --location "Front-left" --duration 30   # measure one spot for 30s, then stop
 
Every --interval seconds it measures RSSI, latency and packet loss, then POSTs
{location, rssi, latency_ms, packet_loss_pct, timestamp} to the backend's /api/readings.
If the server is unreachable the reading is kept and re-sent later.
"""
import argparse
import collections
import json
import math
import random
import re
import subprocess
import time
import urllib.request
from datetime import datetime
 
# ---- Config: change these here, not in the logic below ----
SERVER_URL = "http://127.0.0.1:5000"   # override with --server (use the laptop's IP on the Pi)
INTERVAL = 5                           # seconds between readings
IFACE = "wlan0"                        # Wi-Fi interface name
PINGS = 4                              # pings per reading
NO_SIGNAL_RSSI = -100                  # sent when the Pi is not connected to Wi-Fi (= Dead Zone)
 
ap = argparse.ArgumentParser()
ap.add_argument("--location", required=True, help='label shown on dashboard, e.g. "Library"')
ap.add_argument("--server", default=SERVER_URL)
ap.add_argument("--interval", type=float, default=INTERVAL)
ap.add_argument("--iface", default=IFACE)
ap.add_argument("--target", default="", help="host to ping (default: Wi-Fi gateway)")
ap.add_argument("--duration", type=float, default=0, help="stop after this many seconds (0 = run until Ctrl+C)")
ap.add_argument("--mock", action="store_true", help="generate random values, no Pi needed")
ap.add_argument("--mock-rssi", type=float, default=None,
                help="with --mock: hold the signal around this dBm (e.g. -50 Good, -72 Weak, -86 Dead Zone). "
                     "Omit to let it drift through all three.")
args = ap.parse_args()
URL = args.server.rstrip("/") + "/api/readings"
 
 
def run(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""
 
 
def get_rssi():
    """Signal in dBm, or None if not connected."""
    m = re.search(r"signal:\s*(-?\d+)", run(["iw", "dev", args.iface, "link"]))
    if m:
        return int(m.group(1))
    try:  # fallback: /proc/net/wireless
        for line in open("/proc/net/wireless"):
            if line.strip().startswith(args.iface + ":"):
                return int(float(line.split()[3].rstrip(".")))
    except (OSError, ValueError, IndexError):
        pass
    return None
 
 
def gateway():
    if args.target:
        return args.target
    m = re.search(r"default via (\S+)", run(["ip", "route", "show", "default"]))
    return m.group(1) if m else None
 
 
def ping(host):
    """(average latency ms or None, packet loss %)."""
    out = run(["ping", "-c", str(PINGS), "-i", "0.2", "-W", "1", "-q", host], timeout=PINGS * 2 + 5)
    loss = re.search(r"([\d.]+)% packet loss", out)
    rtt = re.search(r"= [\d.]+/([\d.]+)/", out)
    return (float(rtt.group(1)) if rtt else None), (float(loss.group(1)) if loss else 100.0)
 
 
def mock_values(t):
    """Fake signal that drifts Good -> Weak -> Dead Zone and back (about 2 min per cycle)."""
    if args.mock_rssi is not None:   # fixed spot: small wobble around the chosen level
        rssi = round(args.mock_rssi + 2 * math.sin(t / 15) + random.uniform(-3, 3))
    else:                            # drifting spot
        rssi = round(-73 + 17 * math.sin(t / 20) + random.uniform(-3, 3))
    bad = max(0.0, (-rssi - 67) / 25)
    return rssi, round(random.uniform(5, 20) + bad * random.uniform(30, 200), 1), \
        round(min(100.0, bad * random.uniform(0, 60)), 1)
 
 
def post(payload):
    req = urllib.request.Request(URL, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()
 
 
pending = collections.deque(maxlen=500)   # readings not yet delivered
start = time.monotonic()
print(f"Sensor '{args.location}' ({'MOCK' if args.mock else args.iface}) -> {URL} "
      f"every {args.interval:g}s. Ctrl+C to stop.")
 
try:
    while True:
        t = time.monotonic()
        if args.mock:
            rssi, latency, loss = mock_values(t - start)
        else:
            rssi = get_rssi()
            host = gateway()
            latency, loss = ping(host) if host else (None, 100.0)
        if rssi is None:
            rssi = NO_SIGNAL_RSSI
        pending.append({"location": args.location, "rssi": rssi, "latency_ms": latency,
                        "packet_loss_pct": loss, "timestamp": datetime.now().isoformat(timespec="seconds")})
        print(f"rssi={rssi} dBm  latency={latency} ms  loss={loss}%")
 
        while pending:
            try:
                post(pending[0])
                pending.popleft()
            except Exception as e:
                print(f"  could not reach server ({e}); {len(pending)} reading(s) waiting")
                break
        if args.duration and time.monotonic() - start >= args.duration:
            print(f"Done: {args.duration:g}s measured at '{args.location}'. Move the Pi to the next spot.")
            break
        time.sleep(max(0.0, args.interval - (time.monotonic() - t)))
except KeyboardInterrupt:
    print("\nStopped.")