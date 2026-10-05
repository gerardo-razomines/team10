
#include <Wire.h>

volatile byte desired[2] = {0, 0};
volatile bool newData = false;

void receiveEvent(int howMany) {
  Wire.read();
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
  if (newData) {
    newData = false;
    Serial.print("Goal Position: ");
    Serial.print(desired[0]);
    Serial.print(" ");
    Serial.println(desired[1]);
  }
}
