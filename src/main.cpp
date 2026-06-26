#include <Arduino.h>
#include "Broker.h"
#include "Sensor.h"

Broker broker;
Sensor sensor(16, 17, 18, 5, 14, 0, 4);

void setup() {
    Serial.begin(115200);
    sensor.begin();
    broker.setOnStopCallback([&sensor]() { sensor.handleStop(); });
    broker.begin();
}

void loop() {
    broker.getClient().loop();
    sensor.update();
}
