/*
 * KORA — ESP32 + MPU6050
 * Вимірює нахил конструкції і надсилає його на бекенд: POST /api/sensors/data
 *
 * Підключення MPU6050 -> ESP32:  VCC->3V3, GND->GND, SDA->GPIO21, SCL->GPIO22
 * Бібліотеки: лише ті, що входять до ESP32 Arduino core (WiFi, HTTPClient, Wire).
 * Плата в Arduino IDE: "ESP32 Dev Module".
 */
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <math.h>
#include <time.h>

#include "secrets.h"

static const uint8_t MPU_ADDR = 0x68;

void mpuWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

// Читає прискорення (g) та температуру кристала (°C). false — датчик не відповів.
bool mpuRead(float &ax, float &ay, float &az, float &tempC) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)MPU_ADDR, 8) != 8) return false;
  int16_t rax = (Wire.read() << 8) | Wire.read();
  int16_t ray = (Wire.read() << 8) | Wire.read();
  int16_t raz = (Wire.read() << 8) | Wire.read();
  int16_t rt = (Wire.read() << 8) | Wire.read();
  ax = rax / 16384.0f;  // діапазон ±2g
  ay = ray / 16384.0f;
  az = raz / 16384.0f;
  tempC = rt / 340.0f + 36.53f;
  return true;
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " ok" : " FAILED");
}

// Синхронізація часу (UTC) через NTP — бекенд приймає timestamp у UTC.
bool syncTime() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  struct tm t;
  for (int i = 0; i < 20; i++) {
    if (getLocalTime(&t, 500)) return true;
  }
  return false;
}

bool isoNow(char *buf, size_t len) {
  struct tm t;
  if (!getLocalTime(&t, 200)) return false;
  strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &t);
  return true;
}

// Повертає HTTP-код (або від'ємний при помилці з'єднання)
int postMeasurement(float tiltX, float tiltY, float temp, const char *ts) {
  char body[200];
  snprintf(body, sizeof(body),
           "{\"sensor_id\":%d,\"tilt_x\":%.3f,\"tilt_y\":%.3f,\"temperature\":%.1f,\"timestamp\":\"%s\"}",
           SENSOR_ID, tiltX, tiltY, temp, ts);

  String url = String(API_BASE_URL) + "/api/sensors/data";
  HTTPClient http;
  WiFiClientSecure secure;
  WiFiClient plain;

  if (url.startsWith("https://")) {
    secure.setInsecure();  // ХАКАТОН: без перевірки сертифіката. Для продакшену додайте root CA.
    http.begin(secure, url);
  } else {
    http.begin(plain, url);
  }
  http.setTimeout(60000);  // Render free "прокидається" ~30–60 с: коротший таймаут губить перший запит після простою
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY_DEVICE);
  int code = http.POST(body);
  Serial.printf("POST %s -> %d  %s\n", body, code, code > 0 ? http.getString().c_str() : http.errorToString(code).c_str());
  http.end();
  return code;
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  mpuWrite(0x6B, 0x00);  // вивести MPU6050 зі сну
  connectWiFi();
  Serial.println(syncTime() ? "NTP ok" : "NTP FAILED");
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last < SEND_INTERVAL_MS && last != 0) return;
  last = millis();

  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return;

  float ax, ay, az, temp;
  if (!mpuRead(ax, ay, az, temp)) {
    Serial.println("MPU6050 не відповідає — перевірте підключення");
    return;
  }
  // Нахил відносно вертикалі, градуси
  float tiltX = atan2f(ax, sqrtf(ay * ay + az * az)) * 180.0f / M_PI - OFFSET_X;
  float tiltY = atan2f(ay, sqrtf(ax * ax + az * az)) * 180.0f / M_PI - OFFSET_Y;

  char ts[25];
  if (!isoNow(ts, sizeof(ts))) {
    syncTime();
    return;
  }
  int code = postMeasurement(tiltX, tiltY, temp, ts);
  if (code == 409) Serial.println("Дублікат timestamp — ігноруємо");
  else if (code == 401) Serial.println("Невірний API-ключ");
  else if (code == 404) Serial.println("Датчик із таким SENSOR_ID не існує");
}
