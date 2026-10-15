#include <HardwareSerial.h>

HardwareSerial ServoSerial(2);

const int SERVO_PIN = 16;

// チェックサム
uint8_t checksum(const uint8_t *packet, int lenWithoutChecksum) {
  uint8_t sum = 0;

  // FA AFは除外。IDから最後のデータまでXOR
  for (int i = 2; i < lenWithoutChecksum; i++) {
    sum ^= packet[i];
  }

  return sum;
}

void sendPacket(uint8_t *packet, int len) {
  packet[len - 1] = checksum(packet, len - 1);

  ServoSerial.write(packet, len);
  ServoSerial.flush();
}


// トルクON
void torqueOn(uint8_t id) {
  uint8_t packet[] = {
    0xFA, 0xAF,
    id,
    0x00,
    0x24,
    0x01,
    0x01,
    0x01,
    0x00       // checksum
  };

  sendPacket(packet, sizeof(packet));
}


// 角度指定
// angle10 : 角度×10
// 例 30.0° → 300
//
// time10ms : 10ms単位
// 例 1秒 → 100
void moveServo(uint8_t id, int16_t angle10, uint16_t time10ms) {

  uint8_t packet[] = {
    0xFA, 0xAF,
    id,
    0x00,
    0x1E,
    0x04,
    0x01,

    (uint8_t)(angle10 & 0xFF),
    (uint8_t)((angle10 >> 8) & 0xFF),

    (uint8_t)(time10ms & 0xFF),
    (uint8_t)((time10ms >> 8) & 0xFF),

    0x00       // checksum
  };

  sendPacket(packet, sizeof(packet));
}


void setup() {
  Serial.begin(115200);

  // まずは送信だけなのでTX=GPIO16
  // RXは使わない
  ServoSerial.begin(
    115200,
    SERIAL_8N1,
    -1,
    SERVO_PIN
  );

  delay(1000);

  Serial.println("Torque ON");

  // FF = 全サーボ
  torqueOn(0xFF);

  delay(500);

  Serial.println("Center");

  // 0.0°まで1秒
  moveServo(0xFF, 0, 100);
}

void loop() {

  delay(2000);

  Serial.println("+20 deg");
  moveServo(0xFF, 200, 100);

  delay(2000);

  Serial.println("-20 deg");
  moveServo(0xFF, -200, 100);
}