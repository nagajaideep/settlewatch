#!/usr/bin/env python3
"""
Steady synthetic traffic for demos: books trades that settle today (so the engine processes
them on its next sweep) and mixes in blotter / position / summary reads.
Env: BASE_URL (default http://localhost:8080), RATE trades per second (default 5).
Standard library only, so it runs in a bare python image.
"""
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import date

BASE = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
RATE = float(os.environ.get("RATE", "5"))
CPTYS = ["BROKER-GS", "BROKER-MS", "BROKER-JPM", "BROKER-CITI", "BROKER-BARC", "BROKER-UBS"]


def isin(n: int) -> str:
    return f"US{n:09d}{n % 10}"


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def wait_for_app():
    while call("GET", "/actuator/health") != 200:
        print("waiting for app...")
        time.sleep(3)


def main():
    wait_for_app()
    print(f"loadgen started: {RATE} trades/s against {BASE}")
    sent = errors = 0
    while True:
        start = time.time()
        today = date.today().isoformat()
        status = call("POST", "/api/trades", {
            "clientId": f"CL{random.randint(1, 5000):05d}",
            "isin": isin(random.randint(1, 2000)),
            "side": random.choice(["BUY", "BUY", "SELL"]),
            "quantity": random.randint(1, 5000),
            "price": round(random.uniform(5, 500), 4),
            "currency": random.choice(["USD", "USD", "EUR", "GBP"]),
            "counterparty": random.choice(CPTYS),
            "tradeDate": today,
            "settlementDate": today,
        })
        client = f"CL{random.randint(1, 5000):05d}"
        r = random.random()
        if r < 0.5:
            call("GET", f"/api/trades?clientId={client}&status=SETTLED&size=50")
        elif r < 0.8:
            call("GET", f"/api/clients/{client}/positions")
        else:
            call("GET", "/api/settlements/summary")
        sent += 1
        errors += status >= 400 or status == 0
        if sent % 100 == 0:
            print(f"sent={sent} errors={errors}")
        time.sleep(max(0.0, 1.0 / RATE - (time.time() - start)))


if __name__ == "__main__":
    main()
