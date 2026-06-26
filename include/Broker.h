#ifndef BROKER_H
#define BROKER_H

#include <WiFi.h>
#include <PubSubClient.h>
#include <functional>

using StopCallback = std::function<void()>;

class Broker {
private:

// WiFi
// const char *ssid = "xxxxx"; // Enter your Wi-Fi name
// const char *password = "xxxxx";  // Enter Wi-Fi password
const char *ssid = "Wokwi-GUEST";
const char *password = "";

// MQTT Broker
const char *mqtt_broker = "broker.emqx.io";
const char *topic = "semaforo/esp32";
const char *mqtt_username = "codapli";
const char *mqtt_password = "codapli";
const int mqtt_port = 1883;

WiFiClient espClient;
PubSubClient client;
StopCallback _onStopCallback;

public:
  Broker();
  void begin();
  PubSubClient& getClient();
  void setOnStopCallback(StopCallback cb);
  static Broker* brokerInstance;
  void mqtt_callback(char *topic, byte *payload, unsigned int length);
};

#endif  // !BROKER_H