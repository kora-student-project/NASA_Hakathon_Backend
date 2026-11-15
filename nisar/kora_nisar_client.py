"""KORA — відправник результатів супутникового аналізу в бекенд.

Бекенд НЕ обробляє сирі SAR-знімки. Цей модуль приймає вже обчислене зміщення
(з InSAR-аналізу NISAR або іншого продукту) і надсилає його в POST /api/satellite/data.

Режими:
  csv        — відправити готові результати з CSV-файлу
  simulate   — згенерувати ДЕМО-ряд (source = "DEMO (simulated)", а не NISAR!)

Змінні середовища: API_URL (за замовч. http://localhost:8000), API_KEY_SATELLITE.

Приклади:
  python nisar/kora_nisar_client.py csv results.csv
  python nisar/kora_nisar_client.py simulate --object-id 1 --lon 24.014 --lat 49.8352 --count 6
"""
import argparse
import csv
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

L_BAND_WAVELENGTH_M = 0.238  # NISAR L-діапазон, приблизно 23.8 см


def phase_to_los_mm(unwrapped_phase_rad: float, wavelength_m: float = L_BAND_WAVELENGTH_M) -> float:
    """Переводить розгорнуту інтерферометричну фазу в зміщення вздовж лінії погляду (мм).

    d = -λ / (4π) · φ. Знак залежить від конвенції продукту; перед використанням
    звірте з документацією набору даних. Також потрібні опорна точка та корекція атмосфери.
    """
    return -wavelength_m / (4 * math.pi) * unwrapped_phase_rad * 1000.0


def api_url() -> str:
    return os.environ.get("API_URL", "http://localhost:8000").rstrip("/")


def post_observation(obs: dict) -> dict:
    key = os.environ.get("API_KEY_SATELLITE")
    if not key:
        sys.exit("Задайте API_KEY_SATELLITE у середовищі")
    req = urllib.request.Request(
        f"{api_url()}/api/satellite/data",
        data=json.dumps(obs).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 409:  # те саме спостереження вже є в базі: не помилка
            return {"status": "duplicate", "duplicate": True, "severity": "NORMAL", "alert_created": False}
        raise SystemExit(f"Бекенд відповів HTTP {e.code}: {e.read().decode()[:300]}")


def sent_label(res: dict) -> str:
    """Що показати після відправки: «вже є в базі» для дубліката (409), інакше рівень оцінки."""
    return "вже є в базі" if res.get("duplicate") else res["severity"]


def make_observation(object_id, displacement, obs_date, lon, lat, unit="mm", source="NASA NISAR"):
    return {
        "object_id": int(object_id),
        "displacement": float(displacement),
        "unit": unit,
        "observation_date": obs_date,
        "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
        "source": source,
    }


def cmd_csv(args):
    """CSV-колонки: object_id,displacement,unit,observation_date,longitude,latitude[,source]"""
    with open(args.file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            obs = make_observation(
                row["object_id"], row["displacement"], row["observation_date"],
                row["longitude"], row["latitude"], row.get("unit") or "mm",
                row.get("source") or "NASA NISAR",
            )
            res = post_observation(obs)
            print(row["observation_date"], "->", sent_label(res), "alert" if res["alert_created"] else "")


def cmd_simulate(args):
    """ДЕМО: повільне осідання з шумом. Дані позначаються як симульовані."""
    start = date.today() - timedelta(days=12 * args.count)  # повтор орбіти ~12 діб
    for i in range(args.count):
        d = start + timedelta(days=12 * (i + 1))
        disp = -args.rate * (i + 1) + 0.6 * math.sin(i * 1.7)
        obs = make_observation(args.object_id, round(disp, 2), d.isoformat(), args.lon, args.lat,
                               source="DEMO (simulated)")
        res = post_observation(obs)
        print(d, f"{disp:7.2f} mm ->", sent_label(res))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("csv", help="відправити результати з CSV")
    c.add_argument("file")
    c.set_defaults(func=cmd_csv)
    s = sub.add_parser("simulate", help="ДЕМО: симульований ряд")
    s.add_argument("--object-id", type=int, required=True)
    s.add_argument("--lon", type=float, required=True)
    s.add_argument("--lat", type=float, required=True)
    s.add_argument("--count", type=int, default=10, help="кількість спостережень (крок 12 діб)")
    s.add_argument("--rate", type=float, default=1.5, help="осідання, мм за спостереження")
    s.set_defaults(func=cmd_simulate)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
