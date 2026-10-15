#include <HardwareSerial.h>
#include <Wire.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// ============================================================
// Robi custom PCB / ESP32-S3
// ============================================================

// ---------- USB serial ----------
// Serial = USB CDC
// Host protocol identifier expected by robi_gui.py. PCB revision is separate
// from the USB command protocol version.
static const char HOST_PROTOCOL[] = "ROBI_COMBINED_V2";

// ---------- Robi servo bus ----------
static const int SERVO_TX_PIN      = 43;
static const int SERVO_RX_PIN      = 44;
static const int SERVO_CONTROL_PIN = 1;

static const uint32_t SERVO_BAUD = 115200;

// ---------- LED UART ----------
static const int LED_TX_PIN = 17;
static const int LED_RX_PIN = 18;

// ---------- Sensor UART ----------
static const int SENSOR_TX_PIN = 5;
static const int SENSOR_RX_PIN = 4;

// ---------- microSD SPI ----------
static const int SD_CS_PIN   = 39;
static const int SD_MOSI_PIN = 40;
static const int SD_SCK_PIN  = 41;
static const int SD_MISO_PIN = 42;


// ============================================================
// UART
// ============================================================

HardwareSerial ServoSerial(2);


// ============================================================
// Servo configuration
// ============================================================

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

  {16, -100, 100 },
  {17,  -60,  80 },
  {18,    0,  90 },

  {19, -150, 150 },
  {20, -150, 150 },
  {21, -150, 150 }
};

const int NUM_SERVOS =
  sizeof(limits) / sizeof(limits[0]);


// ============================================================
// Serial command buffer
// ============================================================

char lineBuffer[128];

size_t used = 0;

bool overflow = false;


// ============================================================
// Checksum
// ============================================================

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


// ============================================================
// Servo bus direction
//
// LOW  = ESP32 -> servo
// HIGH = servo -> ESP32
// ============================================================

void servoTxMode()
{
  digitalWrite(
    SERVO_CONTROL_PIN,
    LOW
  );

  delayMicroseconds(10);
}


void servoRxMode()
{
  // UART peripheralのflush後にも少し余裕を取る
  delayMicroseconds(100);

  digitalWrite(
    SERVO_CONTROL_PIN,
    HIGH
  );

  delayMicroseconds(10);
}


// ============================================================
// Clear RX
// ============================================================

void clearServoRX()
{
  while (ServoSerial.available()) {
    ServoSerial.read();
  }
}


// ============================================================
// Packet send
// ============================================================

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

  clearServoRX();

  servoTxMode();

  ServoSerial.write(
    p,
    len
  );

  ServoSerial.flush();

  servoRxMode();
}


// ============================================================
// Find servo index
// ============================================================

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


// ============================================================
// Torque
//
// mode
// 0 = OFF
// 1 = ON
// 2 = brake
// ============================================================

void torque(
  uint8_t id,
  uint8_t mode
)
{
  uint8_t p[] = {

    0xFA,
    0xAF,

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

  delay(20);
}


// ============================================================
// Maximum torque
// ============================================================

void maxTorque(
  uint8_t id,
  uint8_t percent
)
{
  if (percent > 100) {
    percent = 100;
  }

  uint8_t p[] = {

    0xFA,
    0xAF,

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

  delay(20);
}


// ============================================================
// Move servo
// ============================================================

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


  degree =
    constrain(
      degree,
      limits[index].minDeg,
      limits[index].maxDeg
    );


  if (seconds < 0.05f) {
    seconds = 0.05f;
  }


  int16_t position =
    (int16_t)round(
      degree * 10.0f
    );


  uint16_t moveTime =
    (uint16_t)round(
      seconds * 100.0f
    );


  if (moveTime > 0x3FFF) {
    moveTime = 0x3FFF;
  }


  uint8_t p[] = {

    0xFA,
    0xAF,

    id,

    0x00,

    0x1E,

    0x04,

    0x01,

    (uint8_t)(
      position & 0xFF
    ),

    (uint8_t)(
      (position >> 8) & 0xFF
    ),

    (uint8_t)(
      moveTime & 0xFF
    ),

    (uint8_t)(
      (moveTime >> 8) & 0xFF
    ),

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


// ============================================================
// Prepare one servo
// ============================================================

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


// ============================================================
// All torque OFF
// ============================================================

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


// ============================================================
// Decode Futaba return packet
// ============================================================

bool decodePosition(
  const uint8_t *rx,
  int n,
  uint8_t id,
  int16_t &position
)
{
  for (
    int i = 0;
    i + 10 <= n;
    ++i
  ) {

    if (
      rx[i]     != 0xFD ||
      rx[i + 1] != 0xDF ||
      rx[i + 2] != id   ||
      rx[i + 3] != 0x00 ||
      rx[i + 4] != 0x2A ||
      rx[i + 5] < 2     ||
      rx[i + 6] != 1
    ) {
      continue;
    }


    int packetSize =
      8 + rx[i + 5];


    if (
      i + packetSize > n
    ) {
      continue;
    }


    uint8_t expected =
      calcChecksum(
        rx + i,
        2,
        packetSize - 1
      );


    if (
      expected !=
      rx[i + packetSize - 1]
    ) {
      continue;
    }


    position =
      (int16_t)(
        (uint16_t)rx[i + 7]
        |
        (
          (uint16_t)rx[i + 8]
          << 8
        )
      );


    return true;
  }


  return false;
}


// ============================================================
// Raw servo request
// ============================================================

int servoRequest(
  uint8_t *request,
  int requestLength,
  uint8_t *rx,
  int rxSize,
  uint32_t timeoutMs
)
{
  clearServoRX();


  request[requestLength - 1] =
    calcChecksum(
      request,
      2,
      requestLength - 1
    );


  servoTxMode();


  ServoSerial.write(
    request,
    requestLength
  );

  ServoSerial.flush();


  servoRxMode();


  int count = 0;

  unsigned long start =
    millis();


  while (
    millis() - start <
    timeoutMs
  ) {

    while (
      ServoSerial.available() &&
      count < rxSize
    ) {

      rx[count++] =
        ServoSerial.read();
    }


    delay(1);
  }


  return count;
}


// ============================================================
// Read position
// ============================================================

void readPosition(
  uint8_t id
)
{
  int16_t position = 0;

  bool found = false;


  for (
    int attempt = 0;
    attempt < 2 && !found;
    ++attempt
  ) {

    uint8_t request[8];


    if (attempt == 0) {

      // Read current position RAM 0x2A
      uint8_t q[] = {

        0xFA,
        0xAF,

        id,

        0x0F,

        0x2A,

        0x02,

        0x00,

        0x00
      };

      memcpy(
        request,
        q,
        sizeof(request)
      );

    } else {

      // Status return
      uint8_t q[] = {

        0xFA,
        0xAF,

        id,

        0x09,

        0x00,

        0x00,

        0x01,

        0x00
      };

      memcpy(
        request,
        q,
        sizeof(request)
      );
    }


    uint8_t rx[128];


    int count =
      servoRequest(
        request,
        sizeof(request),
        rx,
        sizeof(rx),
        100
      );


    found =
      decodePosition(
        rx,
        count,
        id,
        position
      );


    if (!found) {

      Serial.print(
        "STATUS_RX,"
      );

      Serial.print(id);

      Serial.print(",");

      Serial.print(attempt);

      Serial.print(",");

      Serial.print(count);

      Serial.print(",");


      for (
        int i = 0;
        i < count;
        i++
      ) {

        if (rx[i] < 0x10) {
          Serial.print("0");
        }

        Serial.print(
          rx[i],
          HEX
        );

        Serial.print(" ");
      }


      Serial.println();
    }
  }


  Serial.print(
    "STATUS,"
  );

  Serial.print(id);

  Serial.print(",");


  if (found) {

    Serial.println(
      position / 10.0f
    );

  } else {

    Serial.println(
      "NA"
    );
  }


  Serial.println(
    "OK,STATUS"
  );
}


// ============================================================
// Servo scan
// ============================================================

bool probeServo(
  uint8_t id
)
{
  uint8_t request[] = {

    0xFA,
    0xAF,

    id,

    0x09,

    0x00,

    0x00,

    0x01,

    0x00
  };


  uint8_t rx[128];


  int count =
    servoRequest(
      request,
      sizeof(request),
      rx,
      sizeof(rx),
      30
    );


  for (
    int i = 0;
    i + 2 < count;
    i++
  ) {

    if (
      rx[i]     == 0xFD &&
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
  int foundCount = 0;


  Serial.println(
    "SCAN,BEGIN"
  );


  for (
    int id = 1;
    id <= 127;
    id++
  ) {

    if (
      probeServo(
        (uint8_t)id
      )
    ) {

      Serial.print(
        "SCAN,FOUND,"
      );

      Serial.println(id);

      foundCount++;
    }


    delay(5);
  }


  Serial.print(
    "SCAN,END,"
  );

  Serial.println(
    foundCount
  );
}


// ============================================================
// LED: legacy I2C head board (same protocol as LED_gui.ino).
// GPIO42/41 are shared with the unused SD pin definitions above.
// ============================================================

static const int LED_SDA_PIN = 42;
static const int LED_SCL_PIN = 41;
static const uint8_t LED_ADDR = 0x04;

bool writeLEDRegister(uint8_t reg, uint8_t value)
{
  Wire.beginTransmission(LED_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool setLED(const uint8_t values[7])
{
  Wire.beginTransmission(LED_ADDR);
  Wire.write(0xA2);
  for (int i = 0; i < 7; ++i) Wire.write(values[i]);
  Wire.write((uint8_t)0);
  return Wire.endTransmission() == 0;
}

void reportLED(const uint8_t values[7])
{
  Serial.println(setLED(values) ? "OK,LED" : "ERR,I2C");
}

void initializeLED()
{
  Wire.begin(LED_SDA_PIN, LED_SCL_PIN);
  Wire.setClock(100000);
  bool ok = writeLEDRegister(0x00, 0x00);
  ok = writeLEDRegister(0x01, 0x05) && ok;
  ok = writeLEDRegister(0x0C, 0xAA) && ok;
  ok = writeLEDRegister(0x0D, 0x2A) && ok;
  const uint8_t off[7] = {0};
  ok = setLED(off) && ok;
  if (!ok) Serial.println("ERR,I2C_INIT");
}


// ============================================================
// CSV command parser
// ============================================================

void processCommand(
  char *line
)
{
  // ----------------------------------------------------------
  // No-argument commands
  // ----------------------------------------------------------

  if (
    strcmp(
      line,
      "PING"
    ) == 0
  ) {

    Serial.println(
      HOST_PROTOCOL
    );

    return;
  }


  if (
    strcmp(
      line,
      "STOP"
    ) == 0
  ) {

    allTorqueOff();

    return;
  }


  if (
    strcmp(
      line,
      "SCAN"
    ) == 0
  ) {

    scanServos();

    return;
  }


  if (
    strcmp(
      line,
      "OFF"
    ) == 0
  ) {

    const uint8_t off[7] = {0};
    reportLED(off);

    return;
  }


  // ----------------------------------------------------------
  // CSV
  // ----------------------------------------------------------

  char *comma =
    strchr(
      line,
      ','
    );


  if (!comma) {

    Serial.println(
      "ERR,COMMAND"
    );

    return;
  }


  *comma = '\0';


  double values[7];

  int count = 0;

  char *cursor =
    comma + 1;


  while (true) {

    if (
      count == 7 ||
      *cursor == '\0'
    ) {

      Serial.println(
        "ERR,FORMAT"
      );

      return;
    }


    char *end;


    double value =
      strtod(
        cursor,
        &end
      );


    if (
      end == cursor ||
      !isfinite(value) ||
      (
        *end != ',' &&
        *end != '\0'
      )
    ) {

      Serial.println(
        "ERR,VALUE"
      );

      return;
    }


    values[count++] =
      value;


    if (
      *end == '\0'
    ) {
      break;
    }


    cursor =
      end + 1;
  }


  // ----------------------------------------------------------
  // LED command
  // ----------------------------------------------------------

  if (
    strcmp(
      line,
      "LED"
    ) == 0
  ) {

    if (count != 7) {
      Serial.println("ERR,FORMAT");
      return;
    }
    uint8_t ledValues[7];
    for (int i = 0; i < 7; ++i) {
      if (values[i] < 0 || values[i] > 255 || floor(values[i]) != values[i]) {
        Serial.println("ERR,LED_RANGE");
        return;
      }
      ledValues[i] = (uint8_t)values[i];
    }
    reportLED(ledValues);

    return;
  }


  // ----------------------------------------------------------
  // Servo ID
  // ----------------------------------------------------------

  if (
    values[0] < 2 ||
    values[0] > 21 ||
    floor(values[0]) !=
      values[0]
  ) {

    Serial.println(
      "ERR,INVALID_ID"
    );

    return;
  }


  uint8_t id =
    (uint8_t)values[0];


  // ----------------------------------------------------------
  // STATUS
  // ----------------------------------------------------------

  if (
    strcmp(
      line,
      "STATUS"
    ) == 0 &&
    count == 1
  ) {

    readPosition(id);

    return;
  }


  // ----------------------------------------------------------
  // MOVE
  // ----------------------------------------------------------

  if (
    strcmp(
      line,
      "MOVE"
    ) == 0 &&
    count == 3
  ) {

    if (
      values[1] < -150 ||
      values[1] > 150  ||
      values[2] < 0.05 ||
      values[2] > 163.83
    ) {

      Serial.println(
        "ERR,MOVE_RANGE"
      );

      return;
    }


    moveServo(
      id,
      values[1],
      values[2]
    );

    return;
  }


  // Remaining commands need exactly 2 arguments

  if (
    count != 2 ||
    floor(values[1]) !=
      values[1]
  ) {

    Serial.println(
      "ERR,FORMAT"
    );

    return;
  }


  // ----------------------------------------------------------
  // TORQUE
  // ----------------------------------------------------------

  if (
    strcmp(
      line,
      "TORQUE"
    ) == 0 &&
    values[1] >= 0 &&
    values[1] <= 2
  ) {

    torque(
      id,
      (uint8_t)values[1]
    );


    Serial.println(
      "OK,TORQUE"
    );

    return;
  }


  // ----------------------------------------------------------
  // MAXTORQUE / PREPARE
  // ----------------------------------------------------------

  if (
    values[1] >= 0 &&
    values[1] <= 100
  ) {

    if (
      strcmp(
        line,
        "MAXTORQUE"
      ) == 0
    ) {

      maxTorque(
        id,
        (uint8_t)values[1]
      );


      Serial.println(
        "OK,MAXTORQUE"
      );

      return;
    }


    if (
      strcmp(
        line,
        "PREPARE"
      ) == 0
    ) {

      prepareServo(
        id,
        (uint8_t)values[1]
      );


      Serial.println(
        "OK,PREPARE"
      );

      return;
    }
  }


  Serial.println(
    "ERR,COMMAND"
  );
}


// ============================================================
// Setup
// ============================================================

void setup()
{
  // ----------------------------------------------------------
  // USB CDC
  // ----------------------------------------------------------

  Serial.begin(
    115200
  );


  // ----------------------------------------------------------
  // Servo direction control
  // ----------------------------------------------------------

  pinMode(
    SERVO_CONTROL_PIN,
    OUTPUT
  );


  // TX buffer disabled while idle
  digitalWrite(
    SERVO_CONTROL_PIN,
    HIGH
  );


  // ----------------------------------------------------------
  // Servo UART
  // ----------------------------------------------------------

  ServoSerial.begin(
    SERVO_BAUD,
    SERIAL_8N1,
    SERVO_RX_PIN,
    SERVO_TX_PIN
  );


  delay(500);


  // Ensure receive mode after startup
  servoRxMode();
  initializeLED();


  Serial.println(
    HOST_PROTOCOL
  );


  Serial.println(
    "READY"
  );
}


// ============================================================
// Main loop
// ============================================================

void loop()
{
  while (
    Serial.available()
  ) {

    char c =
      Serial.read();


    if (
      c == '\r'
    ) {
      continue;
    }


    if (
      c == '\n'
    ) {

      if (overflow) {

        Serial.println(
          "ERR,LINE_TOO_LONG"
        );

      } else if (used) {

        lineBuffer[used] =
          '\0';


        processCommand(
          lineBuffer
        );
      }


      used = 0;

      overflow =
        false;


    } else if (
      !overflow
    ) {

      if (
        used <
        sizeof(lineBuffer) - 1
      ) {

        lineBuffer[used++] =
          c;

      } else {

        overflow =
          true;
      }
    }
  }
}
