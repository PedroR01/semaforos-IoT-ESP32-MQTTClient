#include "Broker.h"

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
void Broker::begin(){

    // Connecting to a WiFi network
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.println("Connecting to WiFi..");
    }
    Serial.println("Connected to the Wi-Fi network");

    //connecting to a mqtt broker
    client.setClient(espClient);
    client.setServer(mqtt_broker, mqtt_port);

    // Set the callback function for the MQTT client.
    // In ESP32 accepts lambdas; [this] captures the current instance of Broker.
    client.setCallback(mqttCallback);

    while (!client.connected()) {
        String client_id = "esp32-client-";
        client_id += String(WiFi.macAddress());
        Serial.printf("The client %s connects to the public MQTT broker\n", client_id.c_str());
        if (client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
            Serial.println("Public EMQX MQTT broker connected");
        } else {
            Serial.print("failed with state ");
            Serial.print(client.state());
            delay(2000);
        }
    }

    String publish_message = "Hi, I'm ESP32-client-" + String(WiFi.macAddress());
    // Publish and subscribe
    client.publish(topic, publish_message.c_str());
    client.subscribe(topic);
}

// Function to handle the callback structure for the MQTT client. It is called when a message is received.
void Broker::mqtt_callback(char *topic, byte *payload, unsigned int length) {
    Serial.print("Message arrived in topic: ");
    Serial.println(topic);

    String msg;
    for (unsigned int i = 0; i < length; i++) {
        msg += static_cast<char>(payload[i]);
    }

    Serial.print("Message: ");
    Serial.println(msg);
    Serial.println("-----------------------");

    if (msg == "Detener" && _onStopCallback) {
        _onStopCallback();
    }
}

void Broker::setOnStopCallback(StopCallback cb) {
    _onStopCallback = cb;
}

PubSubClient& Broker::getClient() {
    return client;
}