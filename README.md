# Semáforos IoT ESP32

Monorepositorio para un sistema IoT compuesto por firmware de control, firmware de cámara y procesamiento de visión.

## Componentes actuales

- `firmware/sensor-controller/`: firmware PlatformIO para ESP32 DevKit, sensores, LEDs, display y MQTT.
- `firmware/camera-server/`: firmware PlatformIO para ESP32-CAM y ESP32-S3 que publica un stream MJPEG.
- `vision/detector/detect_esp32cam.py`: consumidor Python del stream con OpenCV y YOLO.

Los componentes siguen siendo proyectos independientes. No existe todavía una integración implementada entre la detección YOLO y el controlador MQTT del semáforo.

## Validación rápida

Desde cada proyecto PlatformIO:

```text
pio run -d firmware/sensor-controller -e esp32dev
pio run -d firmware/camera-server -e esp32cam
pio run -d firmware/camera-server -e esp32s3
```

Entornos de cámara disponibles: `esp32cam` y `esp32s3`.

El detector requiere un entorno Python con OpenCV, NumPy y Ultralytics. La declaración inicial está en `vision/detector/pyproject.toml`; el lockfile y la política de distribución del modelo se completarán antes de incorporarlo a CI.

## Entorno reproducible

El proyecto incluye un Dev Container en `.devcontainer/` para instalar PlatformIO Core, las dependencias Python del detector y las extensiones principales de VS Code. Con Docker Desktop iniciado y la extensión Dev Containers instalada, abrir la raíz y ejecutar `Dev Containers: Reopen in Container`.

La inicialización crea configuraciones locales a partir de los ejemplos sin credenciales reales y compila `esp32dev` y `esp32cam`. La carga del firmware y el monitor serie permanecen en el sistema anfitrión porque el acceso a puertos USB/COM desde Docker en Windows requiere una configuración adicional.

## Organización objetivo

La migración progresiva apunta a separar:

- `firmware/`: proyectos PlatformIO independientes.
- `vision/`: detector y pruebas Python.
- `protocol/mqtt/`: contrato versionado de comunicación.
- `docs/`: hardware, operación y decisiones arquitectónicas.
- `config/examples/`: ejemplos sin credenciales reales.

## Seguridad

No introducir credenciales reales, modelos descargados ni resultados de ejecución en commits. Los puertos serie son configuraciones locales y no forman parte de CI.
