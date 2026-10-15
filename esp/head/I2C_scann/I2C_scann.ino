#include <Wire.h>

#define I2C_SCL 41
#define I2C_SDA 42

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("=== I2C Scanner ===");

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000);  // まずは100kHz

  Serial.printf("SDA = GPIO%d\n", I2C_SDA);
  Serial.printf("SCL = GPIO%d\n", I2C_SCL);
}

void loop() {
  int found = 0;

  Serial.println("Scanning...");

  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();

    if (error == 0) {
      Serial.printf("FOUND: 0x%02X (%d)\n", address, address);
      found++;
    } else if (error == 4) {
      Serial.printf("Unknown error at 0x%02X\n", address);
    }
  }

  if (found == 0) {
    Serial.println("No I2C devices found.");
  } else {
    Serial.printf("Total: %d device(s)\n", found);
  }

  Serial.println("----------------");
  delay(3000);
}