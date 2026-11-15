"""Математика нахилу та одиниць: ядро ТЗ, помилка тут тиха (хибні попередження), тому закріплена таблицями."""
import pytest

from app.services.telemetry_service import tilt_from_accel
from test_api import DEV, SAT, make_device, make_object_and_sensor, sat_body


@pytest.mark.parametrize(
    "accel, vertical, expected",
    [
        ((0.05, 9.81, -0.12), "y", (0.29, -0.70)),  # приклад пристрою: у спокої y ≈ 9.81
        ((0.981, 0.0, 9.81), "z", (5.71, 0.0)),  # плата лежить рівно, нахил по X
        ((9.81, 0.981, 0.0), "x", (5.71, 0.0)),  # вертикаль — x; горизонтальні осі y, z
        ((0.05, -9.81, -0.12), "y", (0.29, -0.70)),  # плату перевернуто: знак вертикалі не має значення
        ((0.0, 9.81, 0.0), "y", (0.0, 0.0)),  # строго вертикально
    ],
)
def test_tilt_from_accel(accel, vertical, expected):
    assert tilt_from_accel(*accel, vertical) == pytest.approx(expected, abs=0.01)


def test_tilt_rejects_unknown_axis():
    with pytest.raises(ValueError):
        tilt_from_accel(1, 1, 1, "q")


@pytest.mark.parametrize(
    "unit, value, severity",
    [
        ("mm", 10.0, "NORMAL"),  # поріг строгий: рівно 10 мм ще норма
        ("mm", 10.1, "WARNING"),
        ("cm", 2.0, "WARNING"),  # 2 см = 20 мм
        ("cm", 3.0, "CRITICAL"),  # 30 мм > 25
        ("m", 0.03, "CRITICAL"),  # 0.03 м = 30 мм
        ("mm", -26.0, "CRITICAL"),  # напрям не важливий: модуль
    ],
)
async def test_satellite_units_and_thresholds(client, unit, value, severity):
    o, _ = await make_object_and_sensor(client)
    body = {**sat_body(o["id"]), "unit": unit, "displacement": value}
    r = await client.post("/api/satellite/data", json=body, headers=SAT)
    assert r.status_code == 201 and r.json()["severity"] == severity


async def test_vertical_axis_setting_changes_tilt(client, monkeypatch):
    from app.config import get_settings

    payload = {
        "device_id": "kora_tracker_01",
        "imu": {"accel": {"x": 0.981, "y": 0.0, "z": 9.81}},
    }
    o, s = await make_device(client)
    key = DEV(s.json())
    # за замовчуванням вертикаль — y: вісь z (9.81) виглядає як сильний нахил
    r = (await client.post("/api/sensors/data", json=payload, headers=key)).json()
    assert r["severity"] == "CRITICAL"
    # вертикаль — z: та сама плата стоїть майже рівно (5.7° по X) і другий кут нульовий
    monkeypatch.setattr(get_settings(), "device_vertical_axis", "z")
    r = (await client.post("/api/sensors/data", json=payload, headers=key)).json()
    assert r["tilt_x"] == pytest.approx(5.71, abs=0.01) and r["tilt_y"] == pytest.approx(0.0, abs=0.01)


async def test_every_view_reports_the_same_severity(client):
    """Один рахунок на бекенді: приймання, список, GeoJSON для карти й статус об'єкта не можуть розійтись."""
    o, _ = await make_object_and_sensor(client)
    cases = [("cm", 2.0, "2026-11-01", "WARNING"), ("mm", 10.0, "2026-11-02", "NORMAL"), ("m", -0.03, "2026-11-03", "CRITICAL")]
    for unit, value, day, expected in cases:
        body = {**sat_body(o["id"]), "unit": unit, "displacement": value, "observation_date": day}
        r = await client.post("/api/satellite/data", json=body, headers=SAT)
        assert r.json()["severity"] == expected

    listed = (await client.get("/api/satellite/data", params={"object_id": o["id"]})).json()
    mapped = (await client.get("/api/satellite/map", params={"object_id": o["id"]})).json()["features"]
    by_day = {x["observation_date"]: x["severity"] for x in listed}
    assert by_day == {"2026-11-01": "WARNING", "2026-11-02": "NORMAL", "2026-11-03": "CRITICAL"}
    assert {f["properties"]["observation_date"]: f["properties"]["severity"] for f in mapped} == by_day

    status = (await client.get(f"/api/objects/{o['id']}/status")).json()
    assert status["latest_satellite_data"]["severity"] == "CRITICAL"  # остання за датою: 2026-11-03
