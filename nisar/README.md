# Модуль супутникових даних

`kora_nisar_client.py` відправляє **вже обчислене** зміщення в `POST /api/satellite/data`. Він не обробляє сирі SAR-знімки.

```bash
export API_URL=http://localhost:8000 API_KEY_SATELLITE=...
python nisar/kora_nisar_client.py csv nisar/example_results.csv
python nisar/kora_nisar_client.py simulate --object-id 1 --lon 24.014 --lat 49.8352 --count 6
```

- `csv` — відправка готових результатів (колонки див. у `example_results.csv`).
- `simulate` — **демо-ряд**, у `source` пишеться `DEMO (simulated)`, щоб його не можна було видати за дані NISAR.
- `phase_to_los_mm()` — допоміжна функція переведення розгорнутої фази в зміщення вздовж лінії погляду (L-діапазон, λ≈23.8 см). Знак і опорну точку перевіряйте за документацією конкретного продукту.

Справжні дані: NISAR-продукти розповсюджує NASA через Earthdata / ASF DAAC (потрібен безкоштовний акаунт Earthdata). Отримати зміщення з InSAR-продукту (наприклад, розгорнутих інтерферограм) і відправити його сюди — завдання окремого GIS-модуля команди.
