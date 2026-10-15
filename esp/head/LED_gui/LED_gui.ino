// PC: led_gui.py / 115200 baud
// Wiring and register values follow ../LED_full/LED_full.ino.
#include <Wire.h>
#include <stdlib.h>
#include <string.h>

const uint8_t LED_ADDR = 0x04;
char lineBuffer[96];
size_t used = 0;
bool overflow = false;

bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(LED_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool setLED(const uint8_t values[7]) {
  Wire.beginTransmission(LED_ADDR);
  Wire.write(0xA2);
  for (int i = 0; i < 7; ++i) Wire.write(values[i]);
  Wire.write((uint8_t)0);
  return Wire.endTransmission() == 0;
}

void processCommand(char *line) {
  if (strcmp(line, "PING") == 0) {
    Serial.println("ROBI_LED_V1");
    return;
  }
  uint8_t values[7] = {0};
  if (strcmp(line, "OFF") != 0) {
    if (strncmp(line, "LED,", 4) != 0) {
      Serial.println("ERR COMMAND");
      return;
    }
    char *cursor = line + 4;
    for (int i = 0; i < 7; ++i) {
      if (*cursor < '0' || *cursor > '9') {
        Serial.println("ERR VALUES"); return;
      }
      char *end;
      long value = strtol(cursor, &end, 10);
      if (value < 0 || value > 255 ||
          (i < 6 ? *end != ',' : *end != '\0')) {
        Serial.println("ERR VALUES"); return;
      }
      values[i] = (uint8_t)value;
      cursor = i < 6 ? end + 1 : end;
    }
  }
  Serial.println(setLED(values) ? "OK LED" : "ERR I2C");
}

void setup() {
  Serial.begin(115200);
  Wire.begin(42, 41);
  Wire.setClock(100000);
  delay(100);
  bool ok = writeReg(0x00, 0x00);
  ok = writeReg(0x01, 0x05) && ok;
  ok = writeReg(0x0C, 0xAA) && ok;
  ok = writeReg(0x0D, 0x2A) && ok;
  uint8_t off[7] = {0};
  ok = setLED(off) && ok;
  Serial.println(ok ? "ROBI_LED_V1" : "ERR I2C INIT");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflow) Serial.println("ERR LINE TOO LONG");
      else if (used) {
        lineBuffer[used] = '\0';
        processCommand(lineBuffer);
      }
      used = 0;
      overflow = false;
    } else if (!overflow) {
      if (used < sizeof(lineBuffer) - 1) lineBuffer[used++] = c;
      else overflow = true;
    }
  }
}
