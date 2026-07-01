# Semaforos-IOT-ESP32-MQTTClient

Proyecto IoT basado en ESP32 orientado al control inteligente de semáforos mediante sensores físicos y comunicación MQTT.

## Config simulacion (Diagram.json)
- Al iniciar la simulación en local, modificar (en tiempo de ejecución) el rango de detección simulado del Ultrasonico a valores entre 30 y 80cm para que efectue las acciones de cambios de luces y comunicación. Por fuera de estos valores los toma como que se tiene que poner en rojo.

## Objetivo

Implementar una arquitectura IoT que permita:

* Detectar presencia de vehículos y peatones.
* Controlar estados de semáforos.
* Publicar eventos mediante MQTT.
* Simular el sistema completo utilizando Wokwi.
* Facilitar la migración futura a hardware físico.

---

# Tecnologías utilizadas

## Hardware

* ESP32 DevKit V4

## Sensores

* HC-SR04 (Ultrasonido)
* PIR (Movimiento)

## Actuadores

* 3 LEDs RGB
* Display 7 segmentos (4 dígitos)

## Software

* Arduino Framework
* PlatformIO
* Wokwi Simulator
* MQTT
* PubSubClient

---

# Estructura del proyecto

```text
src/
├── main.cpp
└── Broker.cpp

include/
└── Broker.h

diagram.json

wokwi.toml

platformio.ini
```

## src/main.cpp

Punto de entrada principal del firmware.

Responsabilidades:

* Inicialización del sistema.
* Inicialización del broker MQTT.
* Ejecución continua del cliente MQTT.

## include/Broker.h

Define la clase Broker.

Responsabilidades:

* Configuración WiFi.
* Configuración MQTT.
* Declaración de callbacks.
* Gestión de conexión.

## src/Broker.cpp

Implementación de la lógica MQTT.

Responsabilidades:

* Conexión WiFi.
* Conexión MQTT.
* Publicación.
* Suscripción.
* Recepción de mensajes.

## diagram.json

Describe el circuito virtual utilizado por Wokwi.

Actualmente contiene:

* ESP32 DevKit
* Sensor HC-SR04
* Sensor PIR
* 3 LEDs RGB
* Display 7 segmentos

También define las conexiones eléctricas entre componentes.

## platformio.ini

Configuración de compilación.

Parámetros principales:

* Plataforma ESP32.
* Framework Arduino.
* Dependencias externas.
* Configuración del monitor serie.

## wokwi.toml

Configuración de integración con Wokwi.

Permite:

* Localizar firmware.bin.
* Localizar firmware.elf.
* Ejecutar simulaciones desde Cursor.

---

# Dependencias

PubSubClient

Instalada automáticamente mediante PlatformIO.

---

# Compilación

```bash
pio run
```

---

# Simulación

1. Compilar el proyecto.
2. Abrir Command Palette.
3. Ejecutar:

Wokwi: Start Simulator

---

# Comunicación MQTT

Broker:

broker.emqx.io

Puerto:

1883

Topic actual:

emqx/esp32

---

# Documentación de configuración

Configurar VS Code para Microsoft C++:
https://code.visualstudio.com/docs/cpp/config-msvc

---

# Futuras mejoras

* Implementar lectura del HC-SR04.
* Implementar detección mediante PIR.
* Control de LEDs RGB.
* Control de display 7 segmentos.
* Separar responsabilidades mediante clases:

  * WifiManager
  * MQTTManager
  * TrafficLightController
  * SensorManager
* Persistencia de configuración.
* OTA Updates.

```
```
