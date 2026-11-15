"""Контракт із фронтендом: дашборд розбирає ТЕКСТ попереджень регулярками (NASA_Hakathon_Frontend/src/alertTrigger.ts).

Якщо перефразувати повідомлення в alert_service.py, UI мовчки втратить число й поріг у «причині статусу» і покаже
англійський текст в UA-режимі. Регулярки нижче — копія з alertTrigger.ts; змінюєте одне, змінюйте й друге.
"""
import re

from test_api import DEV, SAT, make_object_and_sensor, reading, sat_body

SATELLITE = re.compile(r"^(?:WARNING|CRITICAL): satellite displacement (-?\d+(?:\.\d+)?) mm exceeds (\d+(?:\.\d+)?) mm \(.+, (\d{4}-\d{2}-\d{2})\)\.")
TILT = re.compile(r"^(?:WARNING|CRITICAL): tilt_([xy])=(-?\d+(?:\.\d+)?)° exceeds (\d+(?:\.\d+)?)° \(")


async def test_alert_messages_match_frontend_regexes(client):
    o, s = await make_object_and_sensor(client)
    await client.post("/api/sensors/data", json=reading(s["id"], x=-3.0, ts="2026-11-01T12:00:00Z"), headers=DEV(s))  # WARNING, від'ємне
    await client.post("/api/sensors/data", json=reading(s["id"], x=6.5, ts="2026-11-01T12:01:00Z"), headers=DEV(s))  # CRITICAL
    await client.post("/api/satellite/data", json={**sat_body(o["id"]), "displacement": -12.5}, headers=SAT)  # WARNING
    await client.post("/api/satellite/data", json={**sat_body(o["id"]), "displacement": 30, "observation_date": "2026-11-11"}, headers=SAT)  # CRITICAL

    alerts = (await client.get("/api/alerts", params={"object_id": o["id"]})).json()
    assert len(alerts) == 4
    for a in alerts:
        pattern = SATELLITE if a["sensor_id"] is None else TILT
        assert pattern.match(a["message"]), f"frontend cannot parse: {a['message']!r}"

    tilt = next(TILT.match(a["message"]) for a in alerts if a["sensor_id"] and a["severity"] == "WARNING")
    assert tilt.groups() == ("x", "-3.00", "2.00")  # вісь, значення, поріг
    sat = next(SATELLITE.match(a["message"]) for a in alerts if a["sensor_id"] is None and a["severity"] == "WARNING")
    assert sat.groups() == ("-12.5", "10.0", "2026-11-10")  # значення мм, поріг, дата
