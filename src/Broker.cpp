#include "Broker.h"
#include <cstring>

Broker* Broker::brokerInstance=nullptr;

void mqttCallback(char* topic, byte* payload, unsigned int length)
{
    Broker::brokerInstance->mqtt_callback(topic, payload, length);
}

// Constructor
Broker::Broker(){
  brokerInstance = this;
}

// Actions on Init
bool Broker::begin(){

    // Connecting to a WiFi network
    WiFi.begin(ssid, password);
    const unsigned long startMs = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - startMs >= WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println(F("[Broker] WiFi timeout in begin() - will retry in loop()"));
            return false;
        }
        delay(200);
        Serial.print('.');
    }
    Serial.println(F("\n[Broker] WiFi connected"));

    client.setClient(espClient);
    client.setServer(mqtt_broker, mqtt_port);
    client.setCallback(mqttCallback);

    return _connectMqtt();
}

bool Broker::_connectMqtt() {
    char clientId[32];
    snprintf(clientId, sizeof(clientId), "esp32-%s", WiFi.macAddress().c_str());
    Serial.printf("[Broker] Connecting as %s...\n", clientId);
    if (client.connect(clientId, mqtt_username, mqtt_password)) {
        Serial.println(F("[Broker] MQTT connected"));
        _subscribeTopics();
        _lastConnectionState = true;
        _mqttReconnectMs = 0;
        return true;
    }
    Serial.printf("[Broker] MQTT connect failed, state=%d\n", client.state());
    return false;
}

void Broker::_reconnectWiFi() {
    const unsigned long now = millis();
    if (now - _wifiReconnectMs < WIFI_RECONNECT_INTERVAL_MS) return;
    _wifiReconnectMs = now;
    Serial.println(F("[Broker] Attempting WiFi reconnect..."));
    WiFi.disconnect();
    WiFi.begin(ssid, password);
}

void Broker::_subscribeTopics() {
    if (client.subscribe(topic)) {
        Serial.printf("[Broker] Subscribed: %s\n", topic);
    } else {
        Serial.printf("[Broker] Subscribe failed: %s\n", topic);
    }
}

void Broker::diagnose() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println(F("[DIAG] WiFi: DISCONNECTED"));
        _reconnectWiFi();
        return;
    }
    if (!client.connected()) {
        Serial.printf("[DIAG] MQTT: DISCONNECTED (state=%d)\n", client.state());
        const unsigned long now = millis();
        if (now - _mqttReconnectMs >= MQTT_RECONNECT_INTERVAL_MS) {
            _mqttReconnectMs = now;
            _connectMqtt();
        }
        return;
    }
    Serial.println(F("[DIAG] All connections OK"));
}

void Broker::mqtt_callback(char *topic, byte *payload, unsigned int length) {
    Serial.printf("[MQTT] Topic: %s | Msg: ", topic);
    for (unsigned int i = 0; i < length; i++) {
        Serial.print(static_cast<char>(payload[i]));
    }
    Serial.println();

    if (length == 7 && memcmp(payload, "Detener", 7) == 0 && _onStopCallback) {
        _onStopCallback();
    }
}

void Broker::setOnStopCallback(StopCallback cb) {
    _onStopCallback = cb;
}

void Broker::loop() {
    client.loop();
    const bool nowConnected = client.connected();
    if (nowConnected != _lastConnectionState) {
        _lastConnectionState = nowConnected;
        printConnectionStatus();
        if (!nowConnected) {
            diagnose();
        }
    }
    const unsigned long now = millis();
    if (now - _lastDiagMs >= DIAG_INTERVAL_MS) {
        _lastDiagMs = now;
        diagnose();
    }
}

void Broker::printConnectionStatus() {
    const bool connected = client.connected();
    Serial.println();
    Serial.println(F("========================================"));
    if (connected) {
        Serial.println(F(">>> MQTT BROKER CONNECTED <<<"));
    } else {
        Serial.println(F(">>> MQTT BROKER DISCONNECTED <<<"));
    }
    Serial.println(F("========================================"));
    Serial.println();
}
