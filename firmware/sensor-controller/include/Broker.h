#ifndef BROKER_H
#define BROKER_H

#include <PubSubClient.h>
#include <WiFi.h>
#include <functional>
#include <secrets.h>

using StopCallback = std::function<void()>;

class Broker {
private:
  // WiFi
  const char *ssid = WIFI_SSID_LOCAL;     // WIFI_SSID_CODAPLI
  const char *password = WIFI_PASS_LOCAL; // WIFI_PASS_CODAPLI

  // MQTT Broker
  const char *broker_ip = LOCAL_BROKER; // EMQX_BROKER
  const int broker_port = 1883; // Convention port for MQTT data transfer
  const char *client_id = "esp32-codapli";
  const char *topic = "semaforo/esp32";

  WiFiClient espClient;
  PubSubClient mqttClient;
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
  static Broker *brokerInstance;
  void mqtt_callback(char *topic, byte *payload, unsigned int length);
};

#endif // !BROKER_H
