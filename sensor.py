#!/usr/bin/env python3
"""Raspberry Pi Wi-Fi sensor. Standard library only.

Every INTERVAL seconds it measures Wi-Fi signal strength (RSSI) and latency/packet loss
to the Wi-Fi gateway, then POSTs the result to the backend. If the backend can't be
reached (e.g. you are standing in a dead zone) readings are buffered and sent later.

Settings (environment variables):
  SERVER_URL   backend address            default http://127.0.0.1:5000
  LOCATION     name shown on the dashboard default "Pi Sensor" (must match REAL_LOCATION in dashboard.html)
  WIFI_IFACE   Wi-Fi interface            default wlan0
  PING_TARGET  host to ping               default the Wi-Fi default gateway
  INTERVAL     seconds between readings   default 5
  PINGS        pings per reading          default 4
"""
import collections
import json
import os
import re
import subprocess
import time
import urllib.request

SERVER = os.environ.get("SERVER_URL", "http://127.0.0.1:5000").rstrip("/")
LOCATION = os.environ.get("LOCATION", "Pi Sensor")
IFACE = os.environ.get("WIFI_IFACE", "wlan0")
TARGET = os.environ.get("PING_TARGET", "")
INTERVAL = float(os.environ.get("INTERVAL", "5"))
PINGS = int(os.environ.get("PINGS", "4"))


def run(cmd, timeout=15):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def get_rssi():
    """Signal level in dBm of the current Wi-Fi link, or None if not associated."""
    m = re.search(r"signal:\s*(-?\d+)", run(["iw", "dev", IFACE, "link"]))
    if m:
        return int(m.group(1))
    try:  # fallback: /proc/net/wireless  ("wlan0: 0000 70. -40. -256 ...")
        for line in open("/proc/net/wireless"):
            if line.strip().startswith(IFACE + ":"):
                return int(float(line.split()[3].rstrip(".")))
    except (OSError, ValueError, IndexError):
        pass
    return None


def gateway():
    if TARGET:
        return TARGET
    for cmd in (["ip", "route", "show", "default", "dev", IFACE], ["ip", "route", "show", "default"]):
        m = re.search(r"default via (\S+)", run(cmd))
        if m:
            return m.group(1)
    return None


def ping(host):
    """(average latency in ms or None, packet loss in %), sent out of the Wi-Fi interface."""
    out = run(["ping", "-I", IFACE, "-c", str(PINGS), "-i", "0.2", "-W", "1", "-q", host],
              timeout=PINGS * 2 + 5)
    loss = re.search(r"([\d.]+)% packet loss", out)
    rtt = re.search(r"= [\d.]+/([\d.]+)/", out)
    return (float(rtt.group(1)) if rtt else None), (float(loss.group(1)) if loss else 100.0)


def post(payload):
    req = urllib.request.Request(SERVER + "/api/ingest", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


queue = collections.deque(maxlen=500)  # (time measured, payload) waiting to be uploaded

print(f"Sensor '{LOCATION}' on {IFACE} -> {SERVER} every {INTERVAL:g}s (Ctrl+C to stop)")
while True:
    started = time.monotonic()
    rssi = get_rssi()
    host = gateway()
    latency, loss = ping(host) if host else (None, 100.0)
    queue.append((time.monotonic(), {"location": LOCATION, "rssi": rssi,
                                     "latency_ms": latency, "packet_loss_pct": loss}))
    print(f"rssi={rssi} dBm  latency={latency} ms  loss={loss}%  target={host}  queued={len(queue)}")
    while queue:
        measured, payload = queue[0]
        try:
            post({**payload, "age_s": round(time.monotonic() - measured)})
            queue.popleft()
        except Exception as exc:
            print("  upload failed, buffering:", exc)
            break
    time.sleep(max(0.0, INTERVAL - (time.monotonic() - started)))
