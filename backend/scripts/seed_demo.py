"""Заповнює працюючий бекенд демо-даними (об'єкти, датчики, вимірювання, супутник).

Використання:
    API_URL=http://localhost:8000 API_KEY_ADMIN=... API_KEY_DEVICE=... API_KEY_SATELLITE=... \
        python scripts/seed_demo.py
"""
import json
import math
import os
import urllib.request
from datetime import datetime, timedelta, timezone

URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
ADMIN, DEVICE, SAT = (os.environ[k] for k in ("API_KEY_ADMIN", "API_KEY_DEVICE", "API_KEY_SATELLITE"))


def post(path: str, key: str, body: dict) -> dict:
    req = urllib.request.Request(
        URL + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


now = datetime.now(timezone.utc).replace(microsecond=0)
objects = [
    ("Львівська політехніка, корпус 1", "Історична будівля, моніторинг нахилу", 49.8352, 24.0140, 0.4),
    ("Житловий будинок, вул. Городоцька", "Новобудова біля котловану", 49.8397, 23.9985, 3.2),
    ("Міст через Полтву", "Опора №2", 49.8480, 24.0300, 7.5),
    ("Склад (без датчиків)", "Об'єкт без даних", 49.8200, 24.0500, None),
]
for name, desc, lat, lon, amp in objects:
    o = post("/api/objects", ADMIN, {"name": name, "description": desc, "latitude": lat, "longitude": lon})
    if amp is None:
        continue
    s = post("/api/sensors", ADMIN, {"object_id": o["id"], "name": "ESP32 + MPU6050", "sensor_type": "tilt"})
    for i in range(48):  # 48 вимірювань, раз на 30 хв
        ts = now - timedelta(minutes=30 * (47 - i))
        growth = i / 47
        post("/api/sensors/data", DEVICE, {
            "sensor_id": s["id"],
            "tilt_x": round(amp * growth + 0.1 * math.sin(i / 3), 3),
            "tilt_y": round(-0.4 * growth * amp / 3 + 0.05 * math.cos(i / 4), 3),
            "temperature": round(18 + 4 * math.sin(i / 8), 1),
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
        })
    disp = {0.4: -2.1, 3.2: -12.5, 7.5: -31.0}[amp]
    post("/api/satellite/data", SAT, {
        "object_id": o["id"], "displacement": disp, "unit": "mm",
        "observation_date": (now - timedelta(days=4)).date().isoformat(),
        "geometry": {"type": "Point", "coordinates": [lon, lat]}, "source": "NASA NISAR",
    })
print("Готово")
