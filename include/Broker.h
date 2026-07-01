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


static constexpr unsigned long BOT_TIMEOUT_MS = 400;
static constexpr unsigned long STATUS_INTERVAL_MS = 3000;
static constexpr unsigned long WIFI_CONNECT_TIMEOUT_MS = 10000;
static constexpr unsigned long WIFI_RECONNECT_INTERVAL_MS = 10000;
static constexpr unsigned long MQTT_RECONNECT_INTERVAL_MS = 5000;
static constexpr unsigned long DIAG_INTERVAL_MS = 30000;

unsigned long _lastDiagMs = 0;
unsigned long _wifiReconnectMs = 0;
unsigned long _mqttReconnectMs = 0;
bool _lastConnectionState = false;
bool _connectionStateTracked = false;

bool _connectMqtt();
void _reconnectWiFi();
void _subscribeTopics();

public:
  Broker();
  bool begin();
  void loop();
  void diagnose();
  void printConnectionStatus();
  void setOnStopCallback(StopCallback cb);
  static Broker* brokerInstance;
  void mqtt_callback(char *topic, byte *payload, unsigned int length);
};

#endif  // !BROKER_H
