# KORA — інструкція з деплою (для того, хто розгортає)

Потрібні: акаунт GitHub із доступом до організації `kora-student-project`, акаунти Render і Vercel (безкоштовні, картка не потрібна).

Репозиторії:
- бекенд: https://github.com/kora-student-project/NASA_Hakathon_Backend
- фронтенд: https://github.com/kora-student-project/NASA_Hakathon_Frontend

> Render: free-години (750/міс) рахуються на workspace. Не ставте бекенд у workspace, де вже працює інший always-on сервіс. Створіть окремий workspace для хакатону.

## 1. Бекенд + база на Render

1. Render → **New Workspace** (наприклад, `kora-hackathon`) → підключіть GitHub і надайте доступ до `NASA_Hakathon_Backend`.
2. **New → Blueprint** → репозиторій `NASA_Hakathon_Backend`, гілка `main`. Render прочитає `render.yaml` і створить сервіс `kora-backend` та базу `kora-db`.
3. На запит `CORS_ORIGINS` поки впишіть `*`. Натисніть **Apply**, зачекайте 3–5 хв до статусу **Live**.
4. Перевірте `https://<сервіс>.onrender.com/health` → `{"status":"ok"}`. Swagger: `/docs`.
5. У сервісі → **Environment** знайдіть `API_KEY_ADMIN`, `API_KEY_DEVICE`, `API_KEY_SATELLITE` (згенеровані Render). **Передайте їх власнику проєкту приватно (не в чат команди і не в git).**

## 2. Фронтенд на Vercel

Репозиторії приватні й належать організації. Hobby-план Vercel може не підтримувати автодеплой таких репозиторіїв, тому два шляхи:

**А. Через CLI (працює завжди):**
```bash
git clone https://github.com/kora-student-project/NASA_Hakathon_Frontend.git
cd NASA_Hakathon_Frontend
npx vercel            # залогіньтесь, прийміть значення за замовчуванням
npx vercel env add VITE_API_URL production    # значення: https://<сервіс>.onrender.com (без слеша в кінці)
npx vercel --prod
```

**Б. Через сайт:** Add New Project → імпорт `NASA_Hakathon_Frontend` (Framework: Vite, Root Directory порожній) → змінна `VITE_API_URL` = адреса бекенду з Render → Deploy.

Після деплою запишіть production-адресу з Vercel (розділ Domains), наприклад `https://kora.vercel.app`.

## 3. Замкнути CORS

Render → `kora-backend` → Environment → `CORS_ORIGINS` = адреса Vercel (без слеша в кінці, без `*`). Збережіть, сервіс перезапуститься.

## 4. Перевірка

- Відкрийте адресу Vercel: дашборд має завантажитись без червоного банера «Помилка з'єднання з API» (порожня карта нормальна, поки немає об'єктів).
- За потреби заповніть демо-даними (з локальної копії бекенду, значення береться з Render):
  ```bash
  API_URL=https://<сервіс>.onrender.com API_KEY_ADMIN=... API_KEY_DEVICE=... API_KEY_SATELLITE=... \
    python scripts/seed_demo.py
  ```
  Rate limit бекенду (60/хв) може зупинити seed на половині: тоді запустіть його ще раз через хвилину або вимкніть `RATE_LIMIT_ENABLED` тимчасово в Environment.

## 5. Пристрій

1. Зареєструйте пристрій (Swagger `/docs` → **Authorize** з admin-ключем → `POST /api/sensors` із `device_id`, напр. `kora_tracker_01`).
2. Пристрій шле JSON на `POST https://<сервіс>.onrender.com/api/sensors/data` із заголовком `X-API-Key: <API_KEY_DEVICE>`.

## Що передати назад (не секрети)

- Адреса бекенду (Render) і фронтенду (Vercel).
- Ключі `API_KEY_*` окремо, приватним каналом власнику проєкту.

## Обмеження безкоштовних планів

- Render-сервіс «засинає» через 15 хв без запитів, перший запит після цього ~1 хв. Перед показом відкрийте `/health`.
- Безкоштовна база Render живе 30 днів, потім 14 днів до видалення. Для довшого терміну потрібна інша БД (наприклад, Neon) і зміна `DATABASE_URL`.
