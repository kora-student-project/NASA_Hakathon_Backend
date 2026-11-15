# KORA Backend

> Фронтенд (React дашборд) живе в окремому репозиторії: [NASA_Hakathon_Frontend](https://github.com/kora-student-project/NASA_Hakathon_Frontend).

FastAPI-бекенд системи моніторингу стану будівель: приймає дані ESP32 + MPU6050, приймає **вже оброблені** результати супутникового аналізу NASA NISAR (сирі SAR-знімки бекенд не обробляє), зберігає їх у PostgreSQL, створює попередження та віддає все для React Dashboard.

> Попередження (`WARNING`/`CRITICAL`) — індикатори для перевірки, а не висновок про аварійність будівлі.

## Швидкий старт (локально)

Потрібен Python 3.12+.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Згенеруйте ключі й впишіть їх у `.env` (`API_KEY_ADMIN`, `API_KEY_SATELLITE`):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Запуск:

```bash
uvicorn app.main:app --reload
```

Swagger: <http://localhost:8000/docs> (кнопка **Authorize** → ключ у `X-API-Key`).

Без `DATABASE_URL` використовується локальний SQLite (`kora.db`). Таблиці створюються автоматично при старті. Міграцій немає: при зміні схеми на існуючій БД потрібно її очистити (`docker compose down -v` для локального Postgres, видалити `kora.db` для SQLite).

## База даних

`DATABASE_URL` у `.env` визначає БД:

- **Локально / демо:** `sqlite+aiosqlite:///./kora.db` (значення за замовчуванням, нічого налаштовувати не треба).
- **Безкоштовний Postgres:** [Neon](https://neon.tech), Supabase або локальний Postgres. Вставте connection string як `DATABASE_URL=postgresql://user:pass@host/db` (префікс автоматично перетворюється на `postgresql+asyncpg://`; параметр `sslmode` обробляється). Для Supabase free tier використовуйте Session pooler (IPv4).

На Render free **не використовуйте SQLite**: файлова система стирається при кожному перезапуску.

`.env` у `.gitignore` — паролі та ключі в репозиторій не потрапляють.

## Демо-дані

Для презентації можна заповнити працюючий бекенд тестовими об'єктами, вимірюваннями та супутниковими точками:

```bash
API_URL=http://localhost:8000 API_KEY_ADMIN=... API_KEY_SATELLITE=... \
  python scripts/seed_demo.py
```

## Авторизація запису

Усі `POST`/`PATCH` вимагають заголовок `X-API-Key`. Читання (`GET`) відкрите для дашборду.

| Ключ | Дозволяє |
|---|---|
| `API_KEY_ADMIN` | створення об'єктів/датчиків, закриття алертів, а також усе нижче |
| ключ пристрою | видається **окремо для кожного пристрою** при реєстрації (`POST /api/sensors`), дозволяє писати лише від імені цього пристрою (див. «Безпека пристроїв») |
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
| POST | `/api/sensors/data` | **єдиний endpoint для пристрою (device)**: приймає повідомлення `kora_tracker_*` (клімат, IMU, GPS; нахил рахується з акселерометра) або готове вимірювання `{sensor_id, tilt_x, tilt_y, ...}` |
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
  -H "X-API-Key: $DEVICE_KEY" -H "Content-Type: application/json" \
  -d '{"sensor_id":1,"tilt_x":1.25,"tilt_y":-0.42,"temperature":24.5,"timestamp":"2026-11-14T12:30:00Z"}'
```

Відповідь: `{"status":"stored","measurement_id":1,"severity":"NORMAL","alert_id":null,"alert_created":false}`.

### Приклад: повідомлення пристрою (формат пристрою)

Пристрій має бути зареєстрований із `device_id`. У відповіді буде `api_key`: **він показується один раз**, передайте його пристрою:

```bash
curl -X POST http://localhost:8000/api/sensors -H "X-API-Key: $API_KEY_ADMIN" -H "Content-Type: application/json" \
  -d '{"object_id":1,"name":"Tracker 01","sensor_type":"tilt","device_id":"kora_tracker_01"}'
```

Далі пристрій шле свій JSON на `POST /api/sensors/data` (`X-API-Key: <device>`):

```json
{"device_id":"kora_tracker_01","timestamp_ms":1452300,
 "climate":{"temperature":22.5,"humidity":55.0},
 "imu":{"accel":{"x":0.05,"y":9.81,"z":-0.12},"gyro":{"x":0.01,"y":-0.0,"z":0.03}},
 "gps":{"lat":49.839683,"lng":24.029717,"sats":8,"time":"14:25:30","valid":true}}
```

- Нахил: `tilt_x`, `tilt_y` рахуються з акселерометра по двох горизонтальних осях. Вертикальна вісь задається `DEVICE_VERTICAL_AXIS` (за замовчуванням `y`, бо у спокої `y ≈ 9.81`). Якщо плата змонтована інакше, змініть значення.
- Час вимірювання = час отримання на сервері (UTC), бо `timestamp_ms` це uptime пристрою, а `gps.time` без дати. `timestamp_ms` зберігається в `extra`.
- Вологість, гіроскоп і GPS зберігаються в полі `extra` вимірювання. Координати GPS записуються лише при `valid: true`.
- Невідомий `device_id` → `404`. Датчик із таким `device_id` вже є → `409`.

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
- Унікальність у базі: одне активне попередження на `(об'єкт, датчик/супутник, рівень)` і одне супутникове спостереження на `(об'єкт, дата, джерело)`. Індекси створюються при старті (`init_db`) і для вже наявної бази; якщо в старих даних уже є дублікати, у логах буде `Could not create unique index`: видаліть дублікати й перезапустіть.
- Статус об'єкта: `UNKNOWN`, якщо немає жодних даних (ні датчиків, ні супутника); інакше найвищий рівень серед активних алертів; без алертів — `NORMAL`.
- Усі пороги налаштовуються через `.env`.

## Безпека пристроїв

Щоб ніхто сторонній не міг слати чи спамити дані від імені пристрою:

- **Персональний ключ на кожен пристрій.** При `POST /api/sensors` бекенд генерує ключ (`kora_...`, 256 біт), показує його один раз, а в базі зберігає лише SHA-256 хеш. Ключ пристрою A не підходить для пристрою B. Загального ключа пристроїв немає: витік одного ключа не відкриває запис для інших.
- **Невідомий пристрій і хибний ключ дають однакове `401`**, тож перебором не дізнатись, які `device_id` існують.
- **Відкликання.** `PATCH /api/sensors/{id}` з `{"is_active": false}` вимикає пристрій (`403`). `POST /api/sensors/{id}/rotate-key` видає новий ключ, старий перестає працювати одразу. Обидві дії тільки з admin-ключем.
- **Ліміт на пристрій:** `DEVICE_MAX_PER_MINUTE` (30 вимірювань/хв) → `429`. Додатково загальний ліміт за IP (60/хв на запис).
- **Перевірка даних:** діапазони (акселерометр ±160 м/с², вологість 0–100, GPS), нульовий акселерометр і неіснуючі поля відхиляються (`422`), `timestamp` не з майбутнього.
- **HTTPS.** На Render трафік шифрується; ключ не передається у URL, лише в заголовку `X-API-Key`.
- Читання (`GET`) відкрите для дашборду. Для закритих об'єктів потрібен логін користувачів (не реалізовано).

## Захист і обмеження

- Pydantic-валідація: діапазони нахилу (±90°), температури, координат; `timestamp` приводиться до UTC і не може бути більш ніж на добу в майбутньому (`MAX_FUTURE_SKEW_SECONDS`).
- Вимірювання для неіснуючого датчика → `404`. Повторне вимірювання з тим самим `(sensor_id, timestamp)` → `409`.
- Rate limit (slowapi, ключ — IP клієнта з **останнього** значення `X-Forwarded-For`, яке дописує проксі; перше значення клієнт може підробити): `60/minute` на ingest-endpoint-и, `120/minute` на решту (за IP, враховує `X-Forwarded-For`) → `429`.
- Розмір тіла запиту обмежено (`MAX_BODY_BYTES`, 64 KB) → `413`.
- CORS: `CORS_ORIGINS` (через кому або `*`).

## Тести

```bash
pip install -r requirements-dev.txt
pytest
```

## Деплой на Render (free)

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `DATABASE_URL` підставляється автоматично з безкоштовного Postgres Render (`kora-db`, живе 30 днів). Інші змінні: `API_KEY_ADMIN`, `API_KEY_SATELLITE`, `CORS_ORIGINS` (адреса фронтенду на Vercel, без слеша в кінці, наприклад `https://kora.vercel.app`).
- Free-інстанс «засинає» після простою — перший запит може йти ~30–60 с.

## Структура репозиторію

```
app/
├── main.py        # FastAPI, CORS, rate limit
├── config.py      # налаштування з .env
├── database.py    # async SQLAlchemy
├── security.py    # X-API-Key
├── api/           # роутери: objects, sensors, satellite, alerts
├── models/        # таблиці: objects, sensors, measurements, satellite_observations, alerts
├── schemas/       # Pydantic-схеми
└── services/      # sensor_service, satellite_service, alert_service
```

Також у репозиторії: `firmware/` (скетч ESP32), `nisar/` (автоматичне отримання даних NASA NISAR і відправка в API), `scripts/seed_demo.py`, `docs/` (архітектура, демо), `docker-compose.yml` (локальний Postgres), `render.yaml` (Render blueprint).
