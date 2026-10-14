#!/usr/bin/env python3
"""Starts several FAKE Pis at once so the dashboard shows a whole room.
The one real Pi runs separately with its own location name.
 
  python3 fake_pis.py                                  # sends to http://127.0.0.1:5000
  python3 fake_pis.py --server http://192.168.x.x:5000
 
Edit FAKE_PIS to rename spots or change how strong each one is. Ctrl+C stops them all.
"""
import argparse
import os
import subprocess
import sys
 
# location name -> signal level in dBm (None = drifts Good/Weak/Dead Zone over time)
FAKE_PIS = {
    "Front Row - Left":    -50,    # Good (close to the router)
    "Front Row - Right":   -58,    # Good
    "Middle of Room":      -72,    # Weak
    "Back Row - Left":     -86,    # Dead Zone
    "Back Row - Right":    None,   # drifting, good for showing colours change live
}
 
ap = argparse.ArgumentParser()
ap.add_argument("--server", default="http://127.0.0.1:5000")
ap.add_argument("--interval", default="5")
args = ap.parse_args()
 
here = os.path.dirname(os.path.abspath(__file__))
procs = []
for loc, rssi in FAKE_PIS.items():
    cmd = [sys.executable, os.path.join(here, "sensor.py"), "--mock", "--location", loc,
           "--server", args.server, "--interval", args.interval]
    if rssi is not None:
        cmd += ["--mock-rssi", str(rssi)]
    procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL))
print(f"Started {len(procs)} fake Pis -> {args.server}: {', '.join(FAKE_PIS)}. Ctrl+C to stop.")
try:
    for p in procs:
        p.wait()
except KeyboardInterrupt:
    for p in procs:
        p.terminate()
    print("Stopped.")
 