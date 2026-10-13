from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)  # lets the dashboard call this API from another page

DB = "readings.db"
GOOD_THRESHOLD = -67   # RSSI above this = Good
WEAK_THRESHOLD = -80   # RSSI below this = Dead Zone
WINDOW = 5             # average the last 5 readings per location


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT NOT NULL,
            rssi REAL NOT NULL,
            latency_ms REAL,
            packet_loss_pct REAL,
            timestamp TEXT NOT NULL)""")


def classify(rssi):
    if rssi > GOOD_THRESHOLD:
        return "Good"
    if rssi >= WEAK_THRESHOLD:
        return "Weak"
    return "Dead Zone"


@app.route("/api/readings", methods=["POST"])
def add_reading():
    data = request.get_json(silent=True) or {}
    missing = [f for f in ("location", "rssi", "timestamp") if f not in data]
    if missing:
        return jsonify({"error": f"missing fields: {missing}"}), 400
    try:
        rssi = float(data["rssi"])
    except (TypeError, ValueError):
        return jsonify({"error": "rssi must be a number"}), 400

    with get_db() as conn:
        conn.execute(
            "INSERT INTO readings (location, rssi, latency_ms, packet_loss_pct, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (data["location"], rssi, data.get("latency_ms"),
             data.get("packet_loss_pct"), data["timestamp"]))
    return jsonify({"ok": True}), 201


@app.route("/api/status")
def status():
    result = []
    with get_db() as conn:
        locations = [r["location"] for r in
                     conn.execute("SELECT DISTINCT location FROM readings")]
        for loc in locations:
            rows = conn.execute(
                "SELECT rssi, latency_ms, packet_loss_pct FROM readings "
                "WHERE location = ? ORDER BY id DESC LIMIT ?",
                (loc, WINDOW)).fetchall()

            def avg(key):
                return round(sum((r[key] or 0) for r in rows) / len(rows), 1)

            avg_rssi = avg("rssi")
            result.append({
                "location": loc,
                "avg_rssi": avg_rssi,
                "latency_ms": avg("latency_ms"),
                "packet_loss_pct": avg("packet_loss_pct"),
                "status": classify(avg_rssi)})
    return jsonify(result)


@app.route("/api/readings")
def history():
    loc = request.args.get("location")
    with get_db() as conn:
        if loc:
            rows = conn.execute(
                "SELECT * FROM readings WHERE location = ? ORDER BY id DESC LIMIT 100",
                (loc,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM readings ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify([dict(r) for r in reversed(rows)])  # oldest first, for charts


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)