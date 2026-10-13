import requests
import random
from datetime import datetime

URL = "http://localhost:5000/api/readings"

# location name -> typical RSSI (Good / Weak / Dead Zone)
LOCATIONS = {"Library": -50, "Cafeteria": -72, "Stairwell": -86}

for loc, base in LOCATIONS.items():
    for _ in range(6):
        r = requests.post(URL, json={
            "location": loc,
            "rssi": base + random.randint(-3, 3),
            "latency_ms": random.randint(10, 80),
            "packet_loss_pct": random.choice([0, 0, 2, 5]),
            "timestamp": datetime.now().isoformat()})
        print(loc, r.status_code)