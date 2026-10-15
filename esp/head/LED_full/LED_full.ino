#include <Wire.h>

/*
  ============================================================
  Robi 口LED基板 / 目LED制御
  ============================================================

  I2Cデバイス:
    PCA9634
    7bit I2C address = 0x04

  ESP32-S3:
    SDA = GPIO42
    SCL = GPIO41

  LEDチャンネル割り当て:
    PWM0 = 左目 R
    PWM1 = 左目 G
    PWM2 = 左目 B

    PWM3 = 右目 R
    PWM4 = 右目 G
    PWM5 = 右目 B

    PWM6 = 口
    PWM7 = 未使用と思われる

  明るさ:
    0   = 消灯
    255 = 最大
    中間値でPWM調光

  PCA9634主要レジスタ:
    0x00 MODE1
    0x01 MODE2

    0x02 PWM0
    0x03 PWM1
    0x04 PWM2
    0x05 PWM3
    0x06 PWM4
    0x07 PWM5
    0x08 PWM6
    0x09 PWM7

    0x0C LEDOUT0  (PWM0～3の出力モード)
    0x0D LEDOUT1  (PWM4～7の出力モード)

  今回の設定:
    MODE1   = 0x00
    MODE2   = 0x05

    LEDOUT0 = 0xAA
      PWM0～3を個別PWM制御

    LEDOUT1 = 0x2A
      PWM4～6を個別PWM制御
      PWM7はOFF

  PWM一括書き込み:
    command = 0xA2

    0xA2の後に
      PWM0
      PWM1
      PWM2
      PWM3
      PWM4
      PWM5
      PWM6
      PWM7
    の8byteを連続送信する。

  ============================================================
*/

#define SDA_PIN 42
#define SCL_PIN 41

#define LED_ADDR 0x04


// ------------------------------------------------------------
// PCA9634 レジスタへ1byte書き込み
// ------------------------------------------------------------
void writeReg(uint8_t reg, uint8_t value)
{
  Wire.beginTransmission(LED_ADDR);

  Wire.write(reg);
  Wire.write(value);

  Wire.endTransmission();
}


// ------------------------------------------------------------
// PWM0～PWM7をまとめて設定
//
// ch0 = 左R
// ch1 = 左G
// ch2 = 左B
// ch3 = 右R
// ch4 = 右G
// ch5 = 右B
// ch6 = 口
// ch7 = 未使用
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

  /*
    0xA2:
      PWM0からPWM7まで
      Auto Incrementで連続書き込み
  */
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
// 普段はこちらを使う
//
// 左右の目をRGBで指定し、口の明るさも指定
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

    0       // PWM7 未使用
  );
}


// ------------------------------------------------------------
// LED基板初期化
//
// 電源投入後に1回実行
// ------------------------------------------------------------
void initRobiLED()
{
  /*
    MODE1
    通常動作
  */
  writeReg(0x00, 0x00);


  /*
    MODE2 = 0x05

    現状、この設定で
    赤・緑・青のPWM制御を実機確認
  */
  writeReg(0x01, 0x05);


  /*
    LEDOUT0

    PWM0～PWM3を
    個別PWMモードに設定

    2bit/ch:
      10 = PWM制御

    10 10 10 10 = 0xAA
  */
  writeReg(0x0C, 0xAA);


  /*
    LEDOUT1

    PWM4 = PWM
    PWM5 = PWM
    PWM6 = PWM
    PWM7 = OFF

    bit:
      PWM7 PWM6 PWM5 PWM4
       00   10   10   10

    = 0x2A
  */
  writeReg(0x0D, 0x2A);


  // 初期状態は全消灯
  setLED(
    0, 0, 0,
    0, 0, 0,
    0
  );
}


// ============================================================
// Arduino
// ============================================================

void setup()
{
  Serial.begin(115200);

  Wire.begin(SDA_PIN, SCL_PIN);

  // Robi側で安定している速度
  Wire.setClock(100000);

  delay(100);

  initRobiLED();


  // ----------------------------------------------------------
  // 使用例
  // ----------------------------------------------------------


  // 左目だけ赤
  setLED(
    255, 0,   0,
    0,   0,   0,
    0
  );

  delay(1000);


  // 左目緑 / 右目青
  setLED(
    0,   255, 0,
    0,   0,   255,
    0
  );

  delay(1000);


  // 両目白
  setLED(
    255, 255, 255,
    255, 255, 255,
    0
  );

  delay(1000);


  // 両目紫 + 口50%
  setLED(
    255, 0, 255,
    255, 0, 255,
    128
  );

  delay(1000);


  // 全消灯
  setLED(
    0, 0, 0,
    0, 0, 0,
    0
  );
}


void loop()
{
}