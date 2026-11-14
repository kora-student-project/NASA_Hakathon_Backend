# Прошивка ESP32

`kora_esp32/` — скетч Arduino (ESP32 Dev Module), читає MPU6050 по I2C, рахує нахил X/Y, час бере через NTP, шле `POST /api/sensors/data`.

1. `cp kora_esp32/secrets.h.example kora_esp32/secrets.h` і заповніть.
2. Підключення: VCC→3V3, GND→GND, SDA→GPIO21, SCL→GPIO22.
3. Arduino IDE → Board: ESP32 Dev Module → Upload. Serial Monitor: 115200.

Бібліотеки не потрібні (лише ESP32 core). Скетч **ще не компілювався і не запускався на залізі** — перед демо перевірте на платі.

HTTPS: для `https://` використовується `setInsecure()` (без перевірки сертифіката). Для продакшену додайте root CA.
Нахил рахується за прискоренням; калібруйте `OFFSET_X/OFFSET_Y` при рівному положенні плати.
