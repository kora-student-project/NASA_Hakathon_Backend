import pytest

ADMIN = {"X-API-Key": "admin-key"}
DEVICE = {"X-API-Key": "device-key"}
SAT = {"X-API-Key": "sat-key"}


async def make_object_and_sensor(client):
    o = (await client.post("/api/objects", json={"name": "Lviv bldg", "latitude": 49.84, "longitude": 24.0}, headers=ADMIN)).json()
    s = (await client.post("/api/sensors", json={"object_id": o["id"], "name": "esp32-1", "sensor_type": "tilt"}, headers=ADMIN)).json()
    return o, s


def reading(sensor_id, x=0.1, ts="2026-11-01T12:30:00Z", **kw):
    return {"sensor_id": sensor_id, "tilt_x": x, "tilt_y": -0.4, "temperature": 24.5, "timestamp": ts, **kw}


async def test_health_and_docs(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/docs")).status_code == 200


async def test_write_requires_key(client):
    body = {"name": "x", "latitude": 1, "longitude": 1}
    assert (await client.post("/api/objects", json=body)).status_code == 401
    assert (await client.post("/api/objects", json=body, headers=DEVICE)).status_code == 401
    assert (await client.post("/api/objects", json=body, headers=ADMIN)).status_code == 201


async def test_device_key_scope(client):
    o, s = await make_object_and_sensor(client)
    assert (await client.post("/api/satellite/data", headers=DEVICE, json={})).status_code == 401
    assert (await client.post("/api/sensors/data", headers=SAT, json=reading(s["id"]))).status_code == 401


async def test_status_unknown_without_data(client):
    o, _ = await make_object_and_sensor(client)
    r = (await client.get(f"/api/objects/{o['id']}/status")).json()
    assert r["status"] == "UNKNOWN" and r["active_alerts"] == 0


async def test_ingest_normal_then_status(client):
    o, s = await make_object_and_sensor(client)
    r = await client.post("/api/sensors/data", json=reading(s["id"]), headers=DEVICE)
    assert r.status_code == 201 and r.json()["severity"] == "NORMAL" and r.json()["alert_id"] is None
    st = (await client.get(f"/api/objects/{o['id']}/status")).json()
    assert st["status"] == "NORMAL"
    assert st["latest_sensor_data"]["tilt_x"] == 0.1


async def test_warning_and_critical_alerts(client):
    o, s = await make_object_and_sensor(client)
    r = (await client.post("/api/sensors/data", json=reading(s["id"], x=3.0), headers=DEVICE)).json()
    assert r["severity"] == "WARNING" and r["alert_created"]
    # такий самий активний alert не дублюється
    r2 = (await client.post("/api/sensors/data", json=reading(s["id"], x=3.1, ts="2026-11-01T12:31:00Z"), headers=DEVICE)).json()
    assert not r2["alert_created"] and r2["alert_id"] == r["alert_id"]
    r3 = (await client.post("/api/sensors/data", json=reading(s["id"], x=-6.0, ts="2026-11-01T12:32:00Z"), headers=DEVICE)).json()
    assert r3["severity"] == "CRITICAL" and r3["alert_created"]
    st = (await client.get(f"/api/objects/{o['id']}/status")).json()
    assert st["status"] == "CRITICAL" and st["active_alerts"] == 2
    # закриття
    for a in (await client.get("/api/alerts", params={"object_id": o["id"]})).json():
        assert (await client.patch(f"/api/alerts/{a['id']}/resolve", headers=ADMIN)).json()["is_resolved"]
    st = (await client.get(f"/api/objects/{o['id']}/status")).json()
    assert st["status"] == "NORMAL" and st["active_alerts"] == 0


async def test_unknown_sensor_and_validation(client):
    assert (await client.post("/api/sensors/data", json=reading(999), headers=DEVICE)).status_code == 404
    o, s = await make_object_and_sensor(client)
    assert (await client.post("/api/sensors/data", json=reading(s["id"], x=500), headers=DEVICE)).status_code == 422
    assert (await client.post("/api/sensors/data", json=reading(s["id"], ts="2999-01-01T00:00:00Z"), headers=DEVICE)).status_code == 422
    assert (await client.post("/api/sensors/data", json={"sensor_id": 1}, headers=DEVICE)).status_code == 422


async def test_duplicate_measurement_409(client):
    o, s = await make_object_and_sensor(client)
    assert (await client.post("/api/sensors/data", json=reading(s["id"]), headers=DEVICE)).status_code == 201
    assert (await client.post("/api/sensors/data", json=reading(s["id"]), headers=DEVICE)).status_code == 409


async def test_history_filters(client):
    o, s = await make_object_and_sensor(client)
    for i in range(5):
        await client.post("/api/sensors/data", json=reading(s["id"], ts=f"2026-11-0{i+1}T10:00:00Z"), headers=DEVICE)
    url = f"/api/sensors/{s['id']}/data"
    assert len((await client.get(url)).json()) == 5
    assert len((await client.get(url, params={"limit": 2})).json()) == 2
    r = (await client.get(url, params={"from": "2026-11-02T00:00:00Z", "to": "2026-11-03T23:59:59Z"})).json()
    assert len(r) == 2 and r[0]["timestamp"].startswith("2026-11-03")
    assert (await client.get(url, params={"from": "2026-11-03T00:00:00Z", "to": "2026-11-02T00:00:00Z"})).status_code == 422
    assert (await client.get(url, params={"limit": 0})).status_code == 422


def sat_body(object_id, disp=-12.5):
    return {"object_id": object_id, "displacement": disp, "unit": "mm", "observation_date": "2026-11-10",
            "geometry": {"type": "Point", "coordinates": [23.9985, 49.8397]}, "source": "NASA NISAR"}


async def test_satellite_flow(client):
    o, _ = await make_object_and_sensor(client)
    r = await client.post("/api/satellite/data", json=sat_body(o["id"]), headers=SAT)
    assert r.status_code == 201 and r.json()["severity"] == "WARNING" and r.json()["alert_created"]
    assert (await client.post("/api/satellite/data", json=sat_body(999), headers=SAT)).status_code == 404
    bad = sat_body(o["id"]); bad["geometry"]["coordinates"] = [200, 10]
    assert (await client.post("/api/satellite/data", json=bad, headers=SAT)).status_code == 422
    hist = (await client.get("/api/satellite/data", params={"object_id": o["id"]})).json()
    assert len(hist) == 1 and hist[0]["displacement"] == -12.5
    fc = (await client.get("/api/satellite/map")).json()
    assert fc["type"] == "FeatureCollection" and fc["features"][0]["geometry"]["type"] == "Point"
    alerts = (await client.get("/api/alerts", params={"object_id": o["id"]})).json()
    assert alerts[0]["sensor_id"] is None
    st = (await client.get(f"/api/objects/{o['id']}/status")).json()
    assert st["status"] == "WARNING" and st["latest_satellite_data"]["unit"] == "mm"


async def test_sensor_for_missing_object_404(client):
    r = await client.post("/api/sensors", json={"object_id": 42, "name": "n", "sensor_type": "t"}, headers=ADMIN)
    assert r.status_code == 404


async def test_cors_and_body_limit(client):
    r = await client.options("/api/objects", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    r = await client.post("/api/objects", content=b"x" * 70000, headers={**ADMIN, "Content-Type": "application/json"})
    assert r.status_code == 413


async def test_thresholds_endpoint(client):
    r = (await client.get("/api/thresholds")).json()
    assert r["tilt_warning"] < r["tilt_critical"] and r["displacement_warning_mm"] < r["displacement_critical_mm"]
