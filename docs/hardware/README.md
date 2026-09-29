# Hardware soportado

## Controlador de sensores

El proyecto actual usa un ESP32 DevKit y, según `diagram.json`, un HC-SR04, tres LEDs discretos y un display TM1637. `src/main.cpp` construye `Sensor(16, 17, 18, 5, 14, 0, 4)`.

Los límites de detección y tiempos de la máquina de estados están definidos en `include/Sensor.h`. El display está preparado en el código, pero sus operaciones están comentadas.

## Cámara

El proyecto `CameraWebServerPlatformio` mantiene dos entornos separados:

- `esp32cam`: AI Thinker ESP32-CAM con `CAMERA_MODEL_AI_THINKER`.
- `esp32s3`: ESP32-S3-EYE con PSRAM y `CAMERA_MODEL_ESP32S3_EYE`.

Ambos comparten el servidor de cámara, pero no deben compartir ciegamente pines, memoria, particiones ni configuración de carga.

## Discrepancias pendientes

El README histórico menciona PIR y LEDs RGB, pero esos elementos no aparecen en el diagrama ni en la implementación actual. Antes de ampliar abstracciones se debe confirmar cuál es el hardware autoritativo.