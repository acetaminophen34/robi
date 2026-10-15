#include <HardwareSerial.h>

HardwareSerial ServoSerial(2);

const int SERVO_ID = 15;

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
// Torque ON / OFF / Brake
//
// 0 = OFF
// 1 = ON
// 2 = Brake
// ==================================================
void torque(uint8_t mode)
{
  uint8_t p[] = {
    0xFA, 0xAF,
    SERVO_ID,
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
// 0～100 %
// ==================================================
void maxTorque(uint8_t percent)
{
  if (percent > 100) {
    percent = 100;
  }

  uint8_t p[] = {
    0xFA, 0xAF,
    SERVO_ID,
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
void moveServo(float degree, float seconds)
{
  // 念のため制限
  if (degree > 150.0) {
    degree = 150.0;
  }

  if (degree < -150.0) {
    degree = -150.0;
  }

  int16_t position = round(degree * 10.0);

  // 10 ms単位
  uint16_t moveTime = round(seconds * 100.0);

  if (moveTime > 0x3FFF) {
    moveTime = 0x3FFF;
  }

  uint8_t p[] = {
    0xFA, 0xAF,
    SERVO_ID,
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
}


// ==================================================
// RXバッファ掃除
// ==================================================
void clearRX()
{
  while (ServoSerial.available()) {
    ServoSerial.read();
  }
}


// ==================================================
// サーボ状態要求
// ==================================================
void requestStatus()
{
  uint8_t p[] = {
    0xFA, 0xAF,
    SERVO_ID,
    0x09,
    0x00,
    0x00,
    0x01,
    0x00
  };

  sendPacket(p, sizeof(p));
}


// ==================================================
// 状態取得
// ==================================================
void readStatus()
{
  clearRX();

  requestStatus();

  uint8_t rx[64];

  int n = 0;

  unsigned long start = micros();

  // 最大10ms待つ
  while (micros() - start < 10000) {

    while (ServoSerial.available() && n < 64) {

      rx[n] = ServoSerial.read();

      n++;
    }
  }

  // FD DF ID を探す
  for (int i = 0; i <= n - 19; i++) {

    if (
      rx[i] == 0xFD &&
      rx[i + 1] == 0xDF &&
      rx[i + 2] == SERVO_ID
    ) {

      int d = i + 7;

      int16_t position =
        (int16_t)(
          rx[d] |
          (rx[d + 1] << 8)
        );

      uint16_t currentTime =
        rx[d + 2] |
        (rx[d + 3] << 8);

      int16_t speed =
        (int16_t)(
          rx[d + 4] |
          (rx[d + 5] << 8)
        );

      int16_t load =
        (int16_t)(
          rx[d + 6] |
          (rx[d + 7] << 8)
        );

      int16_t temp =
        (int16_t)(
          rx[d + 8] |
          (rx[d + 9] << 8)
        );

      uint16_t voltage =
        rx[d + 10] |
        (rx[d + 11] << 8);


      Serial.print("Position = ");
      Serial.print(position / 10.0);
      Serial.print(" deg");

      Serial.print(" | Time = ");
      Serial.print(currentTime * 0.01);
      Serial.print(" s");

      Serial.print(" | Speed(raw) = ");
      Serial.print(speed);

      Serial.print(" | Load(raw) = ");
      Serial.print(load);

      Serial.print(" | Temp(raw) = ");
      Serial.print(temp);

      Serial.print(" | Voltage(raw) = ");
      Serial.println(voltage);

      return;
    }
  }

  Serial.println("Status response not found");
}


// ==================================================
// 移動しながら状態表示
// ==================================================
void testMove(
  const char *name,
  float degree,
  float seconds
)
{
  Serial.println();
  Serial.println("----------------------------");

  Serial.print("TEST : ");
  Serial.println(name);

  Serial.print("Target = ");
  Serial.print(degree);
  Serial.print(" deg / ");

  Serial.print(seconds);
  Serial.println(" sec");

  Serial.println("----------------------------");

  moveServo(degree, seconds);

  // 約200msごとに状態取得
  int samples = max(
    5,
    (int)(seconds * 5.0)
  );

  for (int i = 0; i < samples; i++) {

    delay(200);

    readStatus();
  }

  delay(500);
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
  Serial.println(" Robi Servo Automatic Test");
  Serial.println("============================");

  Serial.print("Servo ID = ");
  Serial.println(SERVO_ID);

  Serial.println("Torque = 100%");

  maxTorque(100);

  torque(1);

  delay(1000);


  // ==================================================
  // CENTER
  // ==================================================

  testMove(
    "CENTER",
    0,
    2.0
  );


  // ==================================================
  // ±30°
  // ==================================================

  testMove(
    "+30 deg / slow",
    30,
    2.0
  );

  testMove(
    "-30 deg / slow",
    -30,
    2.0
  );


  // ==================================================
  // ±60°
  // ==================================================

  testMove(
    "+60 deg / slow",
    60,
    3.0
  );

  testMove(
    "-60 deg / slow",
    -60,
    3.0
  );


  testMove(
    "+60 deg / fast",
    60,
    1.0
  );

  testMove(
    "-60 deg / fast",
    -60,
    1.0
  );


  // ==================================================
  // ±90°
  // ==================================================

  testMove(
    "+90 deg / slow",
    90,
    3.0
  );

  testMove(
    "-90 deg / slow",
    -90,
    3.0
  );


  testMove(
    "+90 deg / medium",
    90,
    1.5
  );

  testMove(
    "-90 deg / medium",
    -90,
    1.5
  );


  // ==================================================
  // 大きい振幅を高速
  // ==================================================

  testMove(
    "+90 deg / fast",
    90,
    0.7
  );

  testMove(
    "-90 deg / fast",
    -90,
    0.7
  );


  // ==================================================
  // 位置を細かく変える
  // ==================================================

  testMove(
    "-60 deg",
    -60,
    1.0
  );

  testMove(
    "-30 deg",
    -30,
    0.7
  );

  testMove(
    "0 deg",
    0,
    0.7
  );

  testMove(
    "+30 deg",
    30,
    0.7
  );

  testMove(
    "+60 deg",
    60,
    0.7
  );

  testMove(
    "+90 deg",
    90,
    0.7
  );


  // ==================================================
  // CENTERに戻す
  // ==================================================

  testMove(
    "RETURN CENTER",
    0,
    2.0
  );


  // ==================================================
  // トルク50%
  // ==================================================

  Serial.println();
  Serial.println("============================");
  Serial.println(" Torque 50%");
  Serial.println("============================");

  maxTorque(50);

  testMove(
    "+60 deg / Torque 50%",
    60,
    2.0
  );

  testMove(
    "-60 deg / Torque 50%",
    -60,
    2.0
  );

  testMove(
    "CENTER",
    0,
    1.5
  );


  // ==================================================
  // トルク20%
  // ==================================================

  Serial.println();
  Serial.println("============================");
  Serial.println(" Torque 20%");
  Serial.println("============================");

  maxTorque(20);

  testMove(
    "+45 deg / Torque 20%",
    45,
    2.0
  );

  testMove(
    "-45 deg / Torque 20%",
    -45,
    2.0
  );

  testMove(
    "CENTER",
    0,
    1.5
  );


  // ==================================================
  // Brake
  // ==================================================

  Serial.println();
  Serial.println("============================");
  Serial.println(" BRAKE MODE");
  Serial.println("============================");

  torque(2);

  delay(3000);


  // ==================================================
  // Torque OFF
  // ==================================================

  Serial.println();
  Serial.println("============================");
  Serial.println(" TORQUE OFF");
  Serial.println("============================");

  torque(0);

  delay(1000);


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