#include <HardwareSerial.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
HardwareSerial bus(2);
char line[512]; size_t used=0; bool overflow=false;
unsigned long busyUntil=0; bool busy=false;
const char *PROTOCOL="ROBI_MOTION_V3";
bool reading=false; uint8_t readId=2, readAttempt=0, readRX[128];
size_t readCount=0; unsigned long readStart=0;
float lowLimit(int id) { return id==16 ? -100 : id==17 ? -60 : id==18 ? 0 : -150; }
float highLimit(int id) { return id==16 ? 100 : id==17 ? 80 : id==18 ? 90 : 150; }
void packet(uint8_t *p, int n) {
  uint8_t sum=0; for(int i=2;i<n-1;i++) sum^=p[i]; p[n-1]=sum;
  digitalWrite(1,LOW); delayMicroseconds(10);
  bus.write(p,n); bus.flush(); delayMicroseconds(100); digitalWrite(1,HIGH);
}
void torqueAll(int mode) {
  for(int id=2;id<=21;id++) {
    uint8_t p[]={0xFA,0xAF,(uint8_t)id,0,0x24,1,1,(uint8_t)mode,0}; packet(p,9);
  }
}
bool number(char *s, float &v) {
  if(!s || !*s) return false;
  char *end; v=strtof(s,&end); return *end==0 && isfinite(v);
}
void requestPosition() {
  while(bus.available()) bus.read();
  uint8_t q[]={0xFA,0xAF,readId,0x0F,0x2A,2,0,0};
  if(readAttempt) {q[3]=0x09; q[4]=0; q[5]=0; q[6]=1;}
  readCount=0; packet(q,8); readStart=millis();
}
bool decodePosition(int16_t &position) {
  for(size_t i=0;i+10<=readCount;i++) {
    if(readRX[i]!=0xFD || readRX[i+1]!=0xDF || readRX[i+2]!=readId ||
       readRX[i+3]!=0 || readRX[i+4]!=0x2A || readRX[i+5]<2 || readRX[i+6]!=1) continue;
    size_t n=8+readRX[i+5]; if(i+n>readCount) continue;
    uint8_t sum=0; for(size_t j=i+2;j<i+n-1;j++) sum^=readRX[j];
    if(sum!=readRX[i+n-1]) continue;
    position=(int16_t)((uint16_t)readRX[i+7]|((uint16_t)readRX[i+8]<<8)); return true;
  }
  return false;
}
void pollPosition() {
  if(!reading) return;
  while(bus.available()) {int value=bus.read(); if(readCount<sizeof(readRX)) readRX[readCount++]=value;}
  int16_t pos;
  if(decodePosition(pos)) {
    Serial.print("POSE,"); Serial.print(readId); Serial.print(','); Serial.println(pos/10.0f,1);
    if(++readId>21) {reading=false; Serial.println("DONE,READ_ALL");}
    else {readAttempt=0; requestPosition();}
  } else if(millis()-readStart>=100) {
    if(!readAttempt) {readAttempt=1; requestPosition();}
    else {reading=false; Serial.print("ERR,READ,"); Serial.println(readId);}
  }
}
void command(char *s) {
  if(!strcmp(s,"PING")) { Serial.println(PROTOCOL); return; }
  if(!strcmp(s,"STOP") || !strcmp(s,"TORQUE,0")) {
    busy=false; reading=false; torqueAll(0); Serial.println("OK,STOP"); return;
  }
  if(!strcmp(s,"READ_ALL")) {
    if(busy || reading) {Serial.println("ERR,BUSY"); return;}
    reading=true; readId=2; readAttempt=0; requestPosition(); return;
  }
  if(!strcmp(s,"TORQUE,1")) {
    if(reading) {Serial.println("ERR,BUSY"); return;}
    torqueAll(1); Serial.println("OK,TORQUE"); return;
  }
  bool rawMode=!strncmp(s,"FRAME_RAW,",10);
  if(!rawMode && strncmp(s,"FRAME,",6)) { Serial.println("ERR,COMMAND"); return; }
  if(busy || reading) { Serial.println("ERR,BUSY"); return; }
  // Validate the complete frame before moving any axis.
  char *ctx; strtok_r(s,",",&ctx); float ms, angles[20];
  if(!number(strtok_r(NULL,",",&ctx),ms) || ms<50 || ms>163830) { Serial.println("ERR,TIME"); return; }
  for(int i=0;i<20;i++) {
    if(!number(strtok_r(NULL,",",&ctx),angles[i]) || angles[i]<-3276.8f || angles[i]>3276.7f ||
       (!rawMode && (angles[i]<lowLimit(i+2) || angles[i]>highLimit(i+2)))) {
      Serial.println("ERR,ANGLE"); return;
    }
  }
  if(strtok_r(NULL,",",&ctx)) { Serial.println("ERR,FIELDS"); return; }
  uint16_t ticks=(uint16_t)roundf(ms/10);
  for(int i=0;i<20;i++) {
    int16_t pos=(int16_t)roundf(angles[i]*10);
    uint8_t p[]={0xFA,0xAF,(uint8_t)(i+2),0,0x1E,4,1,(uint8_t)pos,(uint8_t)(pos>>8),(uint8_t)ticks,(uint8_t)(ticks>>8),0};
    packet(p,12);
  }
  busy=true; busyUntil=millis()+(unsigned long)ms; Serial.println("OK,FRAME");
}
void setup() {
  Serial.begin(115200); pinMode(1,OUTPUT); digitalWrite(1,HIGH);
  bus.begin(115200,SERIAL_8N1,44,43); Serial.println(PROTOCOL);
}
void loop() {
  while(Serial.available()) {
    char c=Serial.read(); if(c=='\r') continue;
    if(c=='\n') {
      if(overflow) Serial.println("ERR,LINE_TOO_LONG");
      else if(used) {line[used]=0; command(line);}
      used=0; overflow=false;
    } else if(used<sizeof(line)-1) line[used++]=c; else overflow=true;
  }
  if(busy && (long)(millis()-busyUntil)>=0) {busy=false; Serial.println("DONE,FRAME");}
  pollPosition();
}
