# KORA Backend

FastAPI-бекенд системи моніторингу стану будівель: приймає дані ESP32 + MPU6050, приймає **вже оброблені** результати супутникового аналізу NASA NISAR (сирі SAR-знімки бекенд не обробляє), зберігає їх у PostgreSQL, створює попередження та віддає все для React Dashboard.

> Попередження (`WARNING`/`CRITICAL`) — індикатори для перевірки, а не висновок про аварійність будівлі.

## Швидкий старт (локально)

Потрібен Python 3.12+.

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Згенеруйте ключі й впишіть їх у `.env` (`API_KEY_ADMIN`, `API_KEY_DEVICE`, `API_KEY_SATELLITE`):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Запуск:

```bash
uvicorn app.main:app --reload
```

Swagger: <http://localhost:8000/docs> (кнопка **Authorize** → ключ у `X-API-Key`).

Без `DATABASE_URL` використовується локальний SQLite (`kora.db`). Таблиці створюються автоматично при старті.

## База даних

`DATABASE_URL` у `.env` визначає БД:

- **Локально / демо:** `sqlite+aiosqlite:///./kora.db` (значення за замовчуванням, нічого налаштовувати не треба).
- **Безкоштовний Postgres:** [Neon](https://neon.tech), Supabase або локальний Postgres. Вставте connection string як `DATABASE_URL=postgresql://user:pass@host/db` (префікс автоматично перетворюється на `postgresql+asyncpg://`; параметр `sslmode` обробляється). Для Supabase free tier використовуйте Session pooler (IPv4).

На Render free **не використовуйте SQLite**: файлова система стирається при кожному перезапуску.

`.env` у `.gitignore` — паролі та ключі в репозиторій не потрапляють.

## Демо-дані

Для презентації можна заповнити працюючий бекенд тестовими об'єктами, вимірюваннями та супутниковими точками:

```bash
API_URL=http://localhost:8000 API_KEY_ADMIN=... API_KEY_DEVICE=... API_KEY_SATELLITE=... \
  python scripts/seed_demo.py
```

## Авторизація запису

Усі `POST`/`PATCH` вимагають заголовок `X-API-Key`. Читання (`GET`) відкрите для дашборду.

| Ключ | Дозволяє |
|---|---|
| `API_KEY_ADMIN` | створення об'єктів/датчиків, закриття алертів, а також усе нижче |
| `API_KEY_DEVICE` | `POST /api/sensors/data` (ESP32) |
| `API_KEY_SATELLITE` | `POST /api/satellite/data` (NISAR-модуль) |

Якщо ключ не заданий у середовищі — запис відхиляється (503).

## Endpoints

| Метод | Шлях | Опис |
|---|---|---|
| POST | `/api/objects` | створити об'єкт (admin) |
| GET | `/api/objects`, `/api/objects/{id}` | список / один об'єкт |
| GET | `/api/objects/{id}/status` | загальний стан: `UNKNOWN`/`NORMAL`/`WARNING`/`CRITICAL` |
| POST | `/api/sensors` | зареєструвати датчик (admin) |
| GET | `/api/sensors?object_id=`, `/api/sensors/{id}` | датчики |
| POST | `/api/sensors/data` | вимірювання від ESP32 (device) |
| GET | `/api/sensors/{id}/data?from=&to=&limit=` | історія вимірювань (нові першими) |
| POST | `/api/satellite/data` | результат аналізу NISAR (satellite) |
| GET | `/api/satellite/data?object_id=&from=&to=&limit=` | історія спостережень |
| GET | `/api/satellite/map?object_id=` | GeoJSON FeatureCollection для карти |
| GET | `/api/alerts?object_id=&severity=&is_resolved=&limit=` | попередження |
| PATCH | `/api/alerts/{id}/resolve` | позначити вирішеним (admin) |
| GET | `/health` | перевірка живості |

### Приклад: ESP32 / curl

```bash
curl -X POST http://localhost:8000/api/sensors/data \
  -H "X-API-Key: $API_KEY_DEVICE" -H "Content-Type: application/json" \
  -d '{"sensor_id":1,"tilt_x":1.25,"tilt_y":-0.42,"temperature":24.5,"timestamp":"2026-11-14T12:30:00Z"}'
```

Відповідь: `{"status":"stored","measurement_id":1,"severity":"NORMAL","alert_id":null,"alert_created":false}`.

### Приклад: супутникові дані

```bash
curl -X POST http://localhost:8000/api/satellite/data \
  -H "X-API-Key: $API_KEY_SATELLITE" -H "Content-Type: application/json" \
  -d '{"object_id":1,"displacement":-12.5,"unit":"mm","observation_date":"2026-11-10","geometry":{"type":"Point","coordinates":[23.9985,49.8397]},"source":"NASA NISAR"}'
```

`geometry` — GeoJSON Point, координати `[longitude, latitude]`.

## Логіка попереджень

- Нахил: береться більша з `|tilt_x|`, `|tilt_y|`. `> TILT_WARNING_THRESHOLD` → `WARNING`, `> TILT_CRITICAL_THRESHOLD` → `CRITICAL` (за замовчуванням 2° / 5°).
- Супутникове зміщення (переводиться в мм): `> 10 мм` → `WARNING`, `> 25 мм` → `CRITICAL`.
- Створюється один алерт найвищого рівня. Якщо вже є **активний** (нерозв'язаний) алерт того ж рівня для того ж датчика/об'єкта — новий не дублюється, у відповіді повертається `alert_created: false` і id наявного.
- Статус об'єкта: `UNKNOWN`, якщо немає жодних даних (ні датчиків, ні супутника); інакше найвищий рівень серед активних алертів; без алертів — `NORMAL`.
- Усі пороги налаштовуються через `.env`.

## Захист і обмеження

- Pydantic-валідація: діапазони нахилу (±90°), температури, координат; `timestamp` приводиться до UTC і не може бути більш ніж на добу в майбутньому (`MAX_FUTURE_SKEW_SECONDS`).
- Вимірювання для неіснуючого датчика → `404`. Повторне вимірювання з тим самим `(sensor_id, timestamp)` → `409`.
- Rate limit (slowapi): `60/minute` на ingest-endpoint-и, `120/minute` на решту (за IP, враховує `X-Forwarded-For`) → `429`.
- Розмір тіла запиту обмежено (`MAX_BODY_BYTES`, 64 KB) → `413`.
- CORS: `CORS_ORIGINS` (через кому або `*`).

## Тести

```bash
pip install -r requirements-dev.txt
pytest
```

## Деплой на Render (free)

- Root Directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Змінні середовища: `DATABASE_URL` (Postgres, наприклад Neon), `API_KEY_ADMIN`, `API_KEY_DEVICE`, `API_KEY_SATELLITE`, `CORS_ORIGINS` (адреса фронтенду на Vercel, без слеша в кінці, наприклад `https://kora.vercel.app`).
- Free-інстанс «засинає» після простою — перший запит може йти ~30–60 с.

## Структура

```
backend/app/
├── main.py        # FastAPI, CORS, rate limit
├── config.py      # налаштування з .env
├── database.py    # async SQLAlchemy
├── security.py    # X-API-Key
├── api/           # роутери: objects, sensors, satellite, alerts
├── models/        # таблиці: objects, sensors, measurements, satellite_observations, alerts
├── schemas/       # Pydantic-схеми
└── services/      # sensor_service, satellite_service, alert_service
```
