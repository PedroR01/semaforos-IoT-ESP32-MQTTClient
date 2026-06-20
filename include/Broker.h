#ifndef BROKER_H
#define BROKER_H

#include <WiFi.h>
#include <PubSubClient.h>

class Broker {
private:

// WiFi
// const char *ssid = "xxxxx"; // Enter your Wi-Fi name
// const char *password = "xxxxx";  // Enter Wi-Fi password
const char *ssid = "Wokwi-GUEST";
const char *password = "";

// MQTT Broker
const char *mqtt_broker = "broker.emqx.io";
const char *topic = "emqx/esp32";
const char *mqtt_username = "emqx";
const char *mqtt_password = "public";
const int mqtt_port = 1883;

WiFiClient espClient;
PubSubClient client;


public:
  Broker();
  void callback(char *topic, byte *payload, unsigned int length);
  void begin();
  PubSubClient& getClient();
};

#endif  // !BROKER_H