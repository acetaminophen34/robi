#include <HardwareSerial.h>

HardwareSerial ServoSerial(2);

const int TX_PIN = 16;
const int RX_PIN = 17;

const uint32_t BAUD = 115200;


// ==================================================
// Checksum
// ==================================================
uint8_t calcChecksum(const uint8_t *p, int begin, int end)
{
  uint8_t s = 0;

  for (int i = begin; i < end; i++) {
    s ^= p[i];
  }

  return s;
}


// ==================================================
// Packet送信
// ==================================================
void sendPacket(uint8_t *p, int len)
{
  p[len - 1] = calcChecksum(p, 2, len - 1);

  ServoSerial.write(p, len);
  ServoSerial.flush();
}


// ==================================================
// Torque ON / OFF
// ==================================================
void torque(uint8_t id, uint8_t mode)
{
  uint8_t p[] = {
    0xFA, 0xAF,
    id,
    0x00,
    0x24,
    0x01,
    0x01,
    mode,
    0x00
  };

  sendPacket(p, sizeof(p));
}


// ==================================================
// 最大トルク
// ==================================================
void maxTorque(uint8_t id, uint8_t percent)
{
  if (percent > 100) {
    percent = 100;
  }

  uint8_t p[] = {
    0xFA, 0xAF,
    id,
    0x00,
    0x23,
    0x01,
    0x01,
    percent,
    0x00
  };

  sendPacket(p, sizeof(p));
}


// ==================================================
// サーボ移動
//
// degree  : 目標角度 [deg]
// seconds : 移動時間 [s]
// ==================================================
void moveServo(
  uint8_t id,
  float degree,
  float seconds
)
{
  // 今回は安全のため±30°以内
  if (degree > 30.0) {
    degree = 30.0;
  }

  if (degree < -30.0) {
    degree = -30.0;
  }

  int16_t position =
    round(degree * 10.0);

  // 10ms単位
  uint16_t moveTime =
    round(seconds * 100.0);

  if (moveTime > 0x3FFF) {
    moveTime = 0x3FFF;
  }

  uint8_t p[] = {
    0xFA, 0xAF,
    id,
    0x00,
    0x1E,
    0x04,
    0x01,

    // Position
    (uint8_t)(position & 0xFF),
    (uint8_t)((position >> 8) & 0xFF),

    // Time
    (uint8_t)(moveTime & 0xFF),
    (uint8_t)((moveTime >> 8) & 0xFF),

    0x00
  };

  sendPacket(p, sizeof(p));

  Serial.print("ID ");
  Serial.print(id);

  Serial.print(" -> ");
  Serial.print(degree);
  Serial.print(" deg / ");

  Serial.print(seconds);
  Serial.println(" sec");
}


// ==================================================
// 1軸テスト
// ==================================================
void testNeckServo(
  uint8_t id,
  const char *name
)
{
  Serial.println();
  Serial.println("============================");

  Serial.print("TEST ID ");
  Serial.print(id);
  Serial.print(" : ");
  Serial.println(name);

  Serial.println("============================");

  // トルク設定
  maxTorque(id, 50);
  torque(id, 1);

  delay(500);


  // 中央
  moveServo(id, 0, 1.5);
  delay(2000);


  // +20°
  moveServo(id, 20, 1.5);
  delay(2000);


  // 中央
  moveServo(id, 0, 1.5);
  delay(2000);


  // -20°
  moveServo(id, -20, 1.5);
  delay(2000);


  // 中央
  moveServo(id, 0, 1.5);
  delay(2000);


  // 一旦OFF
  torque(id, 0);

  delay(1000);
}


// ==================================================
// SETUP
// ==================================================
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

  Serial.println();
  Serial.println("============================");
  Serial.println(" Robi Neck Servo Test");
  Serial.println("============================");

  Serial.println("ID13 = Yaw");
  Serial.println("ID14 = Roll");
  Serial.println("ID15 = Pitch");

  delay(2000);


  // ==================================================
  // ID13 首旋回
  // ==================================================
  testNeckServo(
    13,
    "NECK YAW"
  );


  // ==================================================
  // ID14 首横回転
  // ==================================================
  testNeckServo(
    14,
    "NECK ROLL"
  );


  // ==================================================
  // ID15 首縦回転
  // ==================================================
  testNeckServo(
    15,
    "NECK PITCH"
  );


  Serial.println();
  Serial.println("============================");
  Serial.println(" TEST FINISHED");
  Serial.println("============================");
}


// ==================================================
// LOOP
// ==================================================
void loop()
{
}