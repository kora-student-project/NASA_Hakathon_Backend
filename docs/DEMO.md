# KORA — демо без хостингу (усе на ноутбуці)

Потрібно: Python 3.12+, Node 20+, (за бажанням) Docker і плата ESP32 + MPU6050.

## 1. Підготовка

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # впишіть три ключі (команда генерації — у .env.example)
```

Postgres у Docker (необов'язково, інакше буде SQLite):

```bash
docker compose up -d     # з кореня репозиторію
# у backend/.env: DATABASE_URL=postgresql://kora:kora_dev_password@localhost:5432/kora
```

## 2. Запуск

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000     # термінал 1
cd frontend && cp .env.example .env && npm install && npm run dev   # термінал 2
```

`--host 0.0.0.0` потрібен, щоб ESP32 бачив бекенд у локальній мережі.
Дашборд: <http://localhost:5173>, Swagger: <http://localhost:8000/docs>.

## 3. Демо-дані

```bash
cd backend && set -a && . ./.env && set +a
RATE_LIMIT_ENABLED=false uvicorn app.main:app --port 8000 &    # seed робить ~150 запитів, ліміт 60/хв його зупинить
API_URL=http://localhost:8000 python scripts/seed_demo.py
```

Супутникові точки позначені `DEMO (simulated)`: це не справжні дані NISAR.

## 4. Живий ESP32

1. Дізнайтесь IP ноутбука (`ipconfig getifaddr en0`).
2. `firmware/kora_esp32/secrets.h.example` → `secrets.h`; впишіть Wi-Fi, `http://<IP>:8000`, `API_KEY_DEVICE`, `SENSOR_ID`.
3. Створіть датчик (`POST /api/sensors` у Swagger з admin-ключем) і візьміть його `id`.
4. Прошийте, відкрийте Serial Monitor (115200). Нахиліть плату — на графіку з'явиться рух, при > 2° з'явиться WARNING.

## 5. Сценарій показу (2–3 хв)

1. **Проблема:** будівлі осідають повільно; супутник бачить мм-зміщення, а датчик — нахил у реальному часі.
2. **Карта:** об'єкти кольором статусу, фіолетові точки — супутникові спостереження.
3. **Об'єкт «Міст через Полтву» (CRITICAL):** показники, графік із лініями порогів, список alerts.
4. **Живо:** нахиляємо ESP32 → нове вимірювання, WARNING → CRITICAL, статус на карті змінюється за ≤ 15 с.
5. **«Вирішено»:** вводимо admin-ключ, закриваємо alert, статус знижується.
6. **Чесно про межі:** alerts це індикатори для перевірки; обробка SAR виконується окремим модулем; пороги потребують калібрування.
