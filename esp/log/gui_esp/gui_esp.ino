#include <HardwareSerial.h>

HardwareSerial ServoSerial(2);

const int TX_PIN = 16;
const int RX_PIN = 17;
const uint32_t BAUD = 115200;


// ==================================================
// 軸ごとの設定
// minDeg / maxDeg はあとで個別に変更可能
// ==================================================
struct ServoLimit {
  uint8_t id;
  float minDeg;
  float maxDeg;
};

ServoLimit limits[] = {
  { 2, -150, 150 },
  { 3, -150, 150 },
  { 4, -150, 150 },
  { 5, -150, 150 },
  { 6, -150, 150 },

  { 7, -150, 150 },
  { 8, -150, 150 },
  { 9, -150, 150 },
  {10, -150, 150 },
  {11, -150, 150 },

  {12, -150, 150 },

  {13, -150, 150 },
  {14, -150, 150 },
  {15, -150, 150 },

  {16, -150, 150 },
  {17, -150, 150 },
  {18, -150, 150 },

  {19, -150, 150 },
  {20, -150, 150 },
  {21, -150, 150 }
};

const int NUM_SERVOS =
  sizeof(limits) / sizeof(limits[0]);


// ==================================================
// Checksum
// ==================================================
uint8_t calcChecksum(
  const uint8_t *p,
  int begin,
  int end
)
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
void sendPacket(
  uint8_t *p,
  int len
)
{
  p[len - 1] =
    calcChecksum(
      p,
      2,
      len - 1
    );

  ServoSerial.write(
    p,
    len
  );

  ServoSerial.flush();

  delay(20);
}


// ==================================================
// ID検索
// ==================================================
int findServoIndex(
  uint8_t id
)
{
  for (int i = 0; i < NUM_SERVOS; i++) {

    if (limits[i].id == id) {
      return i;
    }
  }

  return -1;
}


// ==================================================
// Torque
// ==================================================
void torque(
  uint8_t id,
  uint8_t mode
)
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

  sendPacket(
    p,
    sizeof(p)
  );
}


// ==================================================
// 最大トルク
// ==================================================
void maxTorque(
  uint8_t id,
  uint8_t percent
)
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

  sendPacket(
    p,
    sizeof(p)
  );
}


// ==================================================
// サーボ移動
// ==================================================
void moveServo(
  uint8_t id,
  float degree,
  float seconds
)
{
  int index =
    findServoIndex(id);

  if (index < 0) {

    Serial.println(
      "ERR,INVALID_ID"
    );

    return;
  }

  // 軸ごとの制限
  degree = constrain(
    degree,
    limits[index].minDeg,
    limits[index].maxDeg
  );

  if (seconds < 0.05) {
    seconds = 0.05;
  }

  int16_t position =
    round(
      degree * 10.0
    );

  uint16_t moveTime =
    round(
      seconds * 100.0
    );

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

    (uint8_t)(position & 0xFF),
    (uint8_t)((position >> 8) & 0xFF),

    (uint8_t)(moveTime & 0xFF),
    (uint8_t)((moveTime >> 8) & 0xFF),

    0x00
  };

  sendPacket(
    p,
    sizeof(p)
  );

  Serial.print(
    "OK,MOVE,"
  );

  Serial.print(id);

  Serial.print(",");

  Serial.println(degree);
}


// ==================================================
// 1軸初期化
// ==================================================
void prepareServo(
  uint8_t id,
  uint8_t torquePercent
)
{
  maxTorque(
    id,
    torquePercent
  );

  delay(100);

  torque(
    id,
    1
  );

  delay(300);
}


// ==================================================
// 全軸トルクOFF
// ==================================================
void allTorqueOff()
{
  for (int i = 0; i < NUM_SERVOS; i++) {

    torque(
      limits[i].id,
      0
    );

    delay(30);
  }

  Serial.println(
    "OK,STOP"
  );
}


// ==================================================
// コマンド解析
//
// MOVE,15,10,1
// TORQUE,15,1
// MAXTORQUE,15,50
// PREPARE,15,50
// STOP
// ==================================================
void processCommand(
  String line
)
{
  line.trim();

  if (line.length() == 0) {
    return;
  }

  Serial.print("RX:");
  Serial.println(line);


  // --------------------------------
  // STOP
  // --------------------------------
  if (line == "STOP") {

    allTorqueOff();

    return;
  }


  // --------------------------------
  // MOVE
  // --------------------------------
  if (line.startsWith("MOVE,")) {

    int c1 = line.indexOf(',');
    int c2 = line.indexOf(',', c1 + 1);
    int c3 = line.indexOf(',', c2 + 1);

    if (
      c1 < 0 ||
      c2 < 0 ||
      c3 < 0
    ) {
      Serial.println(
        "ERR,FORMAT"
      );

      return;
    }

    uint8_t id =
      line.substring(
        c1 + 1,
        c2
      ).toInt();

    float degree =
      line.substring(
        c2 + 1,
        c3
      ).toFloat();

    float seconds =
      line.substring(
        c3 + 1
      ).toFloat();

    moveServo(
      id,
      degree,
      seconds
    );

    return;
  }


  // --------------------------------
  // TORQUE
  // --------------------------------
  if (line.startsWith("TORQUE,")) {

    int c1 = line.indexOf(',');
    int c2 = line.indexOf(',', c1 + 1);

    uint8_t id =
      line.substring(
        c1 + 1,
        c2
      ).toInt();

    uint8_t mode =
      line.substring(
        c2 + 1
      ).toInt();

    torque(
      id,
      mode
    );

    Serial.println(
      "OK,TORQUE"
    );

    return;
  }


  // --------------------------------
  // MAXTORQUE
  // --------------------------------
  if (line.startsWith("MAXTORQUE,")) {

    int c1 = line.indexOf(',');
    int c2 = line.indexOf(',', c1 + 1);

    uint8_t id =
      line.substring(
        c1 + 1,
        c2
      ).toInt();

    uint8_t percent =
      line.substring(
        c2 + 1
      ).toInt();

    maxTorque(
      id,
      percent
    );

    Serial.println(
      "OK,MAXTORQUE"
    );

    return;
  }


  // --------------------------------
  // PREPARE
  // --------------------------------
  if (line.startsWith("PREPARE,")) {

    int c1 = line.indexOf(',');
    int c2 = line.indexOf(',', c1 + 1);

    uint8_t id =
      line.substring(
        c1 + 1,
        c2
      ).toInt();

    uint8_t percent =
      line.substring(
        c2 + 1
      ).toInt();

    prepareServo(
      id,
      percent
    );

    Serial.println(
      "OK,PREPARE"
    );

    return;
  }


  Serial.println(
    "ERR,UNKNOWN"
  );
}


// ==================================================
// Setup
// ==================================================
void setup()
{
  Serial.begin(
    115200
  );

  ServoSerial.begin(
    BAUD,
    SERIAL_8N1,
    RX_PIN,
    TX_PIN
  );

  delay(1500);

  Serial.println(
    "READY"
  );
}


// ==================================================
// Loop
// ==================================================
void loop()
{
  static String line = "";

  while (Serial.available()) {

    char c =
      Serial.read();

    if (c == '\n') {

      processCommand(
        line
      );

      line = "";

    } else if (c != '\r') {

      line += c;
    }
  }
}