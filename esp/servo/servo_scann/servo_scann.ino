#include <HardwareSerial.h>

HardwareSerial ServoSerial(2);

const int TX_PIN = 16;
const int RX_PIN = 17;
const uint32_t BAUD = 115200;

uint8_t foundIDs[127];
int foundCount = 0;

uint8_t checksum(const uint8_t *p, int begin, int end)
{
  uint8_t s = 0;
  for (int i = begin; i < end; i++) {
    s ^= p[i];
  }
  return s;
}

void clearRX()
{
  while (ServoSerial.available()) {
    ServoSerial.read();
  }
}

void sendPacket(uint8_t *p, int len)
{
  p[len - 1] = checksum(p, 2, len - 1);

  ServoSerial.write(p, len);
  ServoSerial.flush();
}

bool checkID(uint8_t id)
{
  clearRX();

  uint8_t p[] = {
    0xFA, 0xAF,
    id,
    0x09,
    0x00,
    0x00,
    0x01,
    0x00
  };

  sendPacket(p, sizeof(p));

  uint8_t rx[64];
  int n = 0;

  unsigned long start = micros();

  while (micros() - start < 10000) {
    while (ServoSerial.available() && n < 64) {
      rx[n++] = ServoSerial.read();
    }
  }

  for (int i = 0; i <= n - 3; i++) {
    if (
      rx[i] == 0xFD &&
      rx[i + 1] == 0xDF &&
      rx[i + 2] == id
    ) {
      return true;
    }
  }

  return false;
}

void scanServos()
{
  Serial.println("=== Servo Scan ===");

  for (int id = 1; id <= 127; id++) {

    if (checkID(id)) {
      foundIDs[foundCount++] = id;

      Serial.print("FOUND ID = ");
      Serial.println(id);
    }

    delay(10);
  }

  Serial.println();
  Serial.print("Found count = ");
  Serial.println(foundCount);
}

void torque(uint8_t id, bool on)
{
  uint8_t p[] = {
    0xFA, 0xAF,
    id,
    0x00,
    0x24,
    0x01,
    0x01,
    on ? 1 : 0,
    0x00
  };

  sendPacket(p, sizeof(p));
}

void moveServo(uint8_t id, float degree, float seconds)
{
  int16_t pos = round(degree * 10.0);
  uint16_t t = round(seconds * 100.0);

  uint8_t p[] = {
    0xFA, 0xAF,
    id,
    0x00,
    0x1E,
    0x04,
    0x01,

    (uint8_t)(pos & 0xFF),
    (uint8_t)((pos >> 8) & 0xFF),

    (uint8_t)(t & 0xFF),
    (uint8_t)((t >> 8) & 0xFF),

    0x00
  };

  sendPacket(p, sizeof(p));
}

void setup()
{
  Serial.begin(115200);

  ServoSerial.begin(
    BAUD,
    SERIAL_8N1,
    RX_PIN,
    TX_PIN
  );

  delay(1500);

  scanServos();

  Serial.println();
  Serial.println("=== Identification Test ===");

  for (int i = 0; i < foundCount; i++) {

    uint8_t id = foundIDs[i];

    Serial.println();
    Serial.println("--------------------");

    Serial.print("MOVING ID ");
    Serial.println(id);

    Serial.println("--------------------");

    torque(id, true);

    delay(300);

    // +20°
    moveServo(id, 20.0, 1.0);

    delay(1500);

    // 0°に戻す
    moveServo(id, 0.0, 1.0);

    delay(1500);

    torque(id, false);

    // 次のサーボを見るため少し間を空ける
    delay(2000);
  }

  Serial.println();
  Serial.println("=== FINISHED ===");
}

void loop()
{
}