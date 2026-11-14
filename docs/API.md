# KORA API — довідник endpoints

Базова адреса: `https://<сервіс>.onrender.com` (локально `http://localhost:8000`).
Інтерактивна документація: `/docs` (Swagger), схема: `/openapi.json`.

Запис вимагає заголовок `X-API-Key`. Admin-ключ підходить до всіх запитів запису. Читання відкрите.
Усі часові мітки в UTC (ISO 8601, напр. `2026-11-14T12:30:00Z`).

## Запис

| Метод | Шлях | Ключ | Призначення |
|---|---|---|---|
| POST | `/api/sensors/telemetry` | device | Повний JSON пристрою `kora_tracker_*` (клімат, IMU, GPS) |
| POST | `/api/sensors/data` | device | Вимірювання з уже готовим нахилом |
| POST | `/api/satellite/data` | satellite | Результат аналізу NISAR |
| POST | `/api/objects` | admin | Створити об'єкт |
| POST | `/api/sensors` | admin | Зареєструвати датчик / пристрій |
| PATCH | `/api/alerts/{id}/resolve` | admin | Позначити попередження вирішеним |

## Читання

| Метод | Шлях | Параметри | Призначення |
|---|---|---|---|
| GET | `/api/objects` | `limit`, `offset` | Список об'єктів |
| GET | `/api/objects/{id}` | | Один об'єкт |
| GET | `/api/objects/{id}/status` | | Статус: UNKNOWN / NORMAL / WARNING / CRITICAL |
| GET | `/api/sensors` | `object_id`, `limit` | Датчики |
| GET | `/api/sensors/{id}` | | Один датчик |
| GET | `/api/sensors/{id}/data` | `from`, `to`, `limit` | Історія вимірювань (нові першими) |
| GET | `/api/satellite/data` | `object_id`, `from`, `to`, `limit` | Історія супутникових спостережень |
| GET | `/api/satellite/map` | `object_id`, `from`, `to`, `limit` | GeoJSON FeatureCollection для карти |
| GET | `/api/alerts` | `object_id`, `sensor_id`, `severity`, `is_resolved`, `limit` | Попередження |
| GET | `/api/alerts/{id}` | | Одне попередження |
| GET | `/api/thresholds` | | Поточні пороги |
| GET | `/health` | | Перевірка, що сервіс живий |

Параметри історії: `from`, `to` (дата-час для вимірювань, дата для супутника), `limit` (1–1000, за замовчуванням 100).
Фільтр `severity`: `NORMAL`, `WARNING`, `CRITICAL`.

## Тіла запитів

### POST /api/sensors/telemetry (device)

Пристрій має бути зареєстрований із `device_id`.

```json
{
  "device_id": "kora_tracker_01",
  "timestamp_ms": 1452300,
  "climate": {"temperature": 22.5, "humidity": 55.0},
  "imu": {
    "accel": {"x": 0.05, "y": 9.81, "z": -0.12},
    "gyro": {"x": 0.01, "y": -0.0, "z": 0.03}
  },
  "gps": {"lat": 49.839683, "lng": 24.029717, "sats": 8, "time": "14:25:30", "valid": true}
}
```

Відповідь `201`:
```json
{"status": "stored", "measurement_id": 1, "severity": "NORMAL", "alert_id": null,
 "alert_created": false, "sensor_id": 1, "tilt_x": 0.29, "tilt_y": -0.70}
```

- Нахил рахується з акселерометра. Вертикальна вісь за замовчуванням `y` (змінюється через `DEVICE_VERTICAL_AXIS`).
- Час вимірювання = час отримання на сервері (UTC): `timestamp_ms` це uptime пристрою, а `gps.time` без дати.
- Вологість, гіроскоп і GPS зберігаються в полі `extra`. Координати GPS записуються лише при `valid: true`.
- Акселерометр з усіма нулями → `422`.

### POST /api/sensors/data (device)

```json
{"sensor_id": 1, "tilt_x": 1.25, "tilt_y": -0.42, "temperature": 24.5, "timestamp": "2026-11-14T12:30:00Z"}
```

Нахил у градусах (±90), `temperature` необов'язкова, `timestamp` не далі ніж на добу в майбутнє. Те саме `(sensor_id, timestamp)` двічі → `409`.

### POST /api/satellite/data (satellite)

```json
{
  "object_id": 1,
  "displacement": -12.5,
  "unit": "mm",
  "observation_date": "2026-11-10",
  "geometry": {"type": "Point", "coordinates": [23.9985, 49.8397]},
  "source": "NASA NISAR"
}
```

`unit`: `mm`, `cm` або `m`. `coordinates` це `[longitude, latitude]`. Відповідь `201`: `{"status":"stored","observation_id":1,"severity":"WARNING","alert_id":1,"alert_created":true}`.

### POST /api/objects (admin)

```json
{"name": "Корпус 1", "description": "Опис", "latitude": 49.8352, "longitude": 24.014}
```

### POST /api/sensors (admin)

```json
{"object_id": 1, "name": "Tracker 01", "sensor_type": "tilt", "device_id": "kora_tracker_01"}
```

`device_id` необов'язковий, унікальний. Повторний → `409`.

## Відповідь GET /api/objects/{id}/status

```json
{
  "object_id": 1,
  "status": "WARNING",
  "latest_sensor_data": {"sensor_id": 1, "tilt_x": 1.25, "tilt_y": -0.42,
                         "temperature": 24.5, "humidity": 55.0, "timestamp": "2026-11-14T12:30:00Z"},
  "latest_satellite_data": {"displacement": -12.5, "unit": "mm", "observation_date": "2026-11-10"},
  "active_alerts": 2,
  "last_updated": "2026-11-14T12:30:00Z"
}
```

`UNKNOWN`, якщо немає жодних даних. Інакше береться найвищий рівень серед активних попереджень, а без них `NORMAL`.

## Попередження (alert)

```json
{"id": 1, "object_id": 1, "sensor_id": 1, "severity": "WARNING",
 "message": "WARNING: tilt_x=2.13° exceeds 2.00° ...", "created_at": "2026-11-14T12:30:00Z", "is_resolved": false}
```

`sensor_id` дорівнює `null` для супутникових попереджень. Пороги за замовчуванням: нахил 2° / 5°, зміщення 10 / 25 мм (налаштовуються змінними середовища, актуальні значення в `/api/thresholds`). Попередження є індикаторами для перевірки, а не висновком про аварійність.

## Коди відповідей

| Код | Значення |
|---|---|
| 201 | Створено / збережено |
| 401 | Невірний чи відсутній `X-API-Key` |
| 404 | Об'єкт, датчик, пристрій чи попередження не знайдено |
| 409 | Дублікат: `device_id` або вимірювання з тим самим часом |
| 413 | Тіло запиту більше 64 КБ |
| 422 | Невалідні дані |
| 429 | Забагато запитів (запис: 60 на хвилину, решта: 120 на хвилину) |
| 503 | На сервері не задані API-ключі |
