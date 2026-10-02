/*
  test_i2c_receive.ino
  EENG350 Mini Project - debug tool (Arduino side)

  Purpose:
    Receives the goal [left, right] from the Pi over I2C and prints it
    to the Serial Monitor. No motors needed. Used to check the Pi -> Arduino link.

  Hardware:
    Pi SDA -> Arduino SDA (A4 on Uno), Pi SCL -> Arduino SCL (A5 on Uno), GND -> GND
    I2C address: 8 (must match ARD_ADDR in the Pi code)
*/

#include <Wire.h>

volatile byte desired[2] = {0, 0};
volatile bool newData = false;

void receiveEvent(int howMany) {
  Wire.read();                          // skip the offset byte
  for (int i = 0; i < 2 && Wire.available(); i++) desired[i] = Wire.read();
  newData = true;
}

void setup() {
  Serial.begin(115200);
  Wire.begin(8);
  Wire.onReceive(receiveEvent);
  Serial.println("Waiting for goal from Pi...");
}

void loop() {
  if (newData) {                        // print outside the interrupt
    newData = false;
    Serial.print("Goal Position: ");
    Serial.print(desired[0]);
    Serial.print(" ");
    Serial.println(desired[1]);
  }
}
