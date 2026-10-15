#!/usr/bin/env python3
"""Backend: receives readings from sensor.py, stores them in SQLite, serves the dashboard.

Run:  python3 app.py        (then open http://<this-machine-ip>:5000)
API:  POST /api/ingest | GET /api/status | GET /api/readings?location=X&limit=60
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "readings.db")
app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS readings(
        id INTEGER PRIMARY KEY, location TEXT NOT NULL, ts TEXT NOT NULL,
        rssi INTEGER, latency_ms REAL, packet_loss_pct REAL)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_loc_ts ON readings(location, ts)")


def status_of(rssi):
    if rssi is None:
        return "Dead Zone"
    return "Good" if rssi > -67 else "Weak" if rssi >= -80 else "Dead Zone"


def num(d, key, lo, hi):
    try:
        v = float(d.get(key))
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


@app.after_request
def cors(resp):  # lets the dashboard be opened from another origin / file://
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.post("/api/ingest")
def ingest():
    d = request.get_json(silent=True) or {}
    loc = str(d.get("location", "")).strip()[:60]
    if not loc:
        return jsonify(error="location is required"), 400
    rssi = num(d, "rssi", -120, 0)
    lat = num(d, "latency_ms", 0, 60000)
    loss = num(d, "packet_loss_pct", 0, 100)
    # The sensor sends how old the reading is (age_s), so Pi clock errors never matter.
    age = num(d, "age_s", 0, 86400) or 0
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat(timespec="seconds")
    ts = ts.replace("+00:00", "Z")
    with db() as con:
        con.execute(
            "INSERT INTO readings(location, ts, rssi, latency_ms, packet_loss_pct) VALUES (?,?,?,?,?)",
            (loc, ts, None if rssi is None else round(rssi), lat, loss))
    return jsonify(ok=True)


@app.get("/api/status")
def status():
    with db() as con:
        rows = con.execute(
            """SELECT r.* FROM readings r JOIN
               (SELECT location, MAX(ts) AS m FROM readings GROUP BY location) x
               ON r.location = x.location AND r.ts = x.m""").fetchall()
    latest = {}
    for r in rows:
        latest[r["location"]] = {
            "location": r["location"], "rssi": r["rssi"], "latency_ms": r["latency_ms"],
            "packet_loss_pct": r["packet_loss_pct"], "status": status_of(r["rssi"]),
            "last_seen": r["ts"]}
    return jsonify(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   locations=list(latest.values()))


@app.get("/api/readings")
def readings():
    loc = request.args.get("location", "")
    limit = min(request.args.get("limit", 60, type=int), 2000)
    with db() as con:
        rows = con.execute(
            "SELECT ts, rssi, latency_ms, packet_loss_pct FROM readings "
            "WHERE location = ? ORDER BY ts DESC LIMIT ?", (loc, limit)).fetchall()
    return jsonify(location=loc, readings=[dict(r) for r in reversed(rows)])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
