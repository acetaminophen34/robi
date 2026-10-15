#include <Wire.h>
#include <math.h>

/*
  Robi LED / PCA9634
  I2C address : 0x04

  PWM0 : 左目 R
  PWM1 : 左目 G
  PWM2 : 左目 B
  PWM3 : 右目 R
  PWM4 : 右目 G
  PWM5 : 右目 B
  PWM6 : 口
  PWM7 : 未使用
*/

#define SDA_PIN 42
#define SCL_PIN 41
#define LED_ADDR 0x04


// ------------------------------------------------------------
// PCA9634 レジスタ書き込み
// ------------------------------------------------------------
void writeReg(uint8_t reg, uint8_t value)
{
  Wire.beginTransmission(LED_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}


// ------------------------------------------------------------
// PWM0～PWM7 一括書き込み
// ------------------------------------------------------------
void setPWM(
  uint8_t ch0,
  uint8_t ch1,
  uint8_t ch2,
  uint8_t ch3,
  uint8_t ch4,
  uint8_t ch5,
  uint8_t ch6,
  uint8_t ch7
)
{
  Wire.beginTransmission(LED_ADDR);

  // PWM0からPWM7へAuto Increment
  Wire.write(0xA2);

  Wire.write(ch0);
  Wire.write(ch1);
  Wire.write(ch2);
  Wire.write(ch3);
  Wire.write(ch4);
  Wire.write(ch5);
  Wire.write(ch6);
  Wire.write(ch7);

  Wire.endTransmission();
}


// ------------------------------------------------------------
// 普段使う関数
// 左右RGB + 口明るさ
// ------------------------------------------------------------
void setLED(
  uint8_t leftR,
  uint8_t leftG,
  uint8_t leftB,

  uint8_t rightR,
  uint8_t rightG,
  uint8_t rightB,

  uint8_t mouth
)
{
  setPWM(
    leftR,
    leftG,
    leftB,

    rightR,
    rightG,
    rightB,

    mouth,
    0
  );
}


// ------------------------------------------------------------
// LED初期化
// ------------------------------------------------------------
void initRobiLED()
{
  // MODE1
  writeReg(0x00, 0x00);

  // MODE2
  writeReg(0x01, 0x05);

  // PWM0～3を個別PWM
  writeReg(0x0C, 0xAA);

  // PWM4～6を個別PWM、PWM7 OFF
  writeReg(0x0D, 0x2A);

  setLED(
    0, 0, 0,
    0, 0, 0,
    0
  );
}


// ------------------------------------------------------------
// HSV → RGB
//
// h : 0～360
// s : 0～1
// v : 0～1
// ------------------------------------------------------------
void hsvToRgb(
  float h,
  float s,
  float v,
  uint8_t &r,
  uint8_t &g,
  uint8_t &b
)
{
  float c = v * s;

  float x =
    c * (1.0f - fabsf(fmodf(h / 60.0f, 2.0f) - 1.0f));

  float m = v - c;

  float rf = 0;
  float gf = 0;
  float bf = 0;

  if (h < 60.0f) {
    rf = c;
    gf = x;
  }
  else if (h < 120.0f) {
    rf = x;
    gf = c;
  }
  else if (h < 180.0f) {
    gf = c;
    bf = x;
  }
  else if (h < 240.0f) {
    gf = x;
    bf = c;
  }
  else if (h < 300.0f) {
    rf = x;
    bf = c;
  }
  else {
    rf = c;
    bf = x;
  }

  r = (uint8_t)((rf + m) * 255.0f);
  g = (uint8_t)((gf + m) * 255.0f);
  b = (uint8_t)((bf + m) * 255.0f);
}


// ============================================================
// SETUP
// ============================================================

void setup()
{
  Serial.begin(115200);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);

  delay(100);

  initRobiLED();
}


// ============================================================
// GAMING RGB LOOP
// ============================================================

void loop()
{
  static float hue = 0.0f;
  static float phase = 0.0f;

  uint8_t lr, lg, lb;
  uint8_t rr, rg, rb;

  // 左目
  hsvToRgb(
    hue,
    1.0f,
    1.0f,
    lr, lg, lb
  );

  // 右目は少し位相差を変化させる
  float offset = 120.0f + 50.0f * sinf(phase);

  float rightHue = hue + offset;

  if (rightHue >= 360.0f)
    rightHue -= 360.0f;

  hsvToRgb(
    rightHue,
    1.0f,
    1.0f,
    rr, rg, rb
  );

  // 口
  float pulse =
    (sinf(phase * 2.0f) + 1.0f) * 0.5f;

  uint8_t mouth =
    30 + (uint8_t)(pulse * 200.0f);

  setLED(
    lr, lg, lb,
    rr, rg, rb,
    mouth
  );

  // 1回の変化量を大きめに
  hue += 6.0f;

  if (hue >= 360.0f)
    hue -= 360.0f;

  phase += 0.18f;

  // 通信回数を減らす
  delay(45);
}