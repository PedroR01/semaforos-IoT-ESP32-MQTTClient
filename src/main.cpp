#include <Arduino.h>
#include "Broker.h"

Broker broker;

void setup() {

    Serial.begin(115200);
    broker.begin();

}

void loop() {

    //Avoid using blocking delay() functions inside your loop, 
    // as it will cause the ESP32 client to disconnect from the broker.
    broker.getClient().loop();

}