# NASA_Hakathon — KORA

KORA — моніторинг стану будівель та інфраструктури: супутникові дані NASA NISAR + наземні IoT-датчики (ESP32 + MPU6050).

- [`backend/`](backend/README.md) — FastAPI + PostgreSQL (Render)
- [`frontend/`](frontend/README.md) — React + Vite дашборд (Vercel)
- [`firmware/`](firmware/README.md) — прошивка ESP32 + MPU6050
- [`nisar/`](nisar/README.md) — відправник результатів аналізу NISAR
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архітектура, [`docs/DEMO.md`](docs/DEMO.md) — демо без хостингу
- `docker-compose.yml` — локальний Postgres, `render.yaml` — Render blueprint
