# Semáforos IoT ESP32

Monorepositorio para un sistema IoT compuesto por firmware de control, firmware de cámara y procesamiento de visión.

## Componentes

- `firmware/sensor-controller/`: firmware PlatformIO para ESP32 DevKit, sensores, LEDs, display y MQTT.
- `firmware/camera-server/`: firmware PlatformIO para ESP32-CAM y ESP32-S3 que publica un stream MJPEG.
- `vision/detector/detect_esp32cam.py`: consumidor Python del stream con OpenCV y YOLO.

Los componentes son proyectos independientes. La detección YOLO todavía no publica MQTT ni controla el semáforo.

## Requisitos

- Git.
- Python entre 3.11 y 3.13 para el detector.
- VS Code con la extensión PlatformIO IDE, o PlatformIO Core instalado en el PATH.
- Para la simulación: extensión Wokwi para VS Code y una cuenta de Wokwi si la extensión la solicita.
- Para cargar firmware: el ESP32 correspondiente, un cable USB de datos y el controlador USB-serie que necesite la placa.

Este proyecto no requiere Docker. PlatformIO instala automáticamente el framework, toolchain y librerías declaradas por cada firmware; el detector instala sus dependencias en un entorno virtual de Python.

### PlatformIO

La opción más sencilla es instalar la extensión **PlatformIO IDE** en VS Code. Como alternativa, instalar PlatformIO Core desde una terminal:

```powershell
python -m pip install --upgrade platformio
pio --version
```

Las dependencias de cada firmware se descargan al ejecutar su primera compilación.

### Credenciales locales

Antes de compilar hardware real, crear los archivos de secretos a partir de sus ejemplos y reemplazar los valores de WiFi. Estos archivos están ignorados por Git:

```powershell
Copy-Item firmware/sensor-controller/include/secrets.h.example firmware/sensor-controller/include/secrets.h
Copy-Item firmware/camera-server/include/secrets.h.example firmware/camera-server/include/secrets.h
```

Para Wokwi se pueden conservar `Wokwi-GUEST` y la contraseña vacía. Para una placa física, completar el perfil seleccionado por el código (`LOCAL` en ambos firmwares) con la red disponible.

## Firmware del controlador de sensores

El proyecto usa un ESP32 DevKit y el entorno PlatformIO `esp32dev`.

### Compilar

Desde la raíz del repositorio:

```powershell
pio run -d firmware/sensor-controller -e esp32dev
```

### Cargar en el ESP32 y abrir el monitor serie

Conectar la placa y sustituir `COMx` por el puerto que corresponda:

```powershell
pio run -d firmware/sensor-controller -e esp32dev -t upload --upload-port COMx
pio device monitor --port COMx --baud 115200
```

El archivo `platformio.ini` contiene `/dev/ttyUSB1` como valor de desarrollo para el monitor; en Windows conviene indicar el puerto con `--port` como en el ejemplo.

### Ejecutar en Wokwi

1. Compilar el firmware con el comando anterior.
2. Abrir `firmware/sensor-controller` en VS Code.
3. Ejecutar **Wokwi: Start Simulator** desde la Command Palette.
4. Durante la simulación, ajustar el rango del sensor ultrasónico entre 30 y 80 cm para provocar el cambio de luces y la comunicación MQTT.

Las dependencias `PubSubClient`, `TM1637` y `NewPing` se instalan automáticamente desde `platformio.ini`.

## Firmware de cámara

El servidor soporta dos entornos PlatformIO:

- `esp32cam`: AI Thinker ESP32-CAM, normalmente en `COM5` en la configuración de ejemplo.
- `esp32s3`: ESP32-S3-EYE, normalmente en `COM6` en la configuración de ejemplo.

No asumir esos puertos: editar `firmware/camera-server/platformio.ini` o pasarlos en la línea de comandos.

### Compilar

```powershell
pio run -d firmware/camera-server -e esp32cam
pio run -d firmware/camera-server -e esp32s3
```

### Cargar y obtener la URL del stream

Para una AI Thinker ESP32-CAM:

```powershell
pio run -d firmware/camera-server -e esp32cam -t upload --upload-port COMx
pio device monitor --port COMx --baud 115200
```

Para una ESP32-S3-EYE, cambiar `esp32cam` por `esp32s3` y `COMx` por el puerto de la placa.

El monitor serie mostrará la IP local después de conectar la cámara al WiFi. El servidor web queda disponible en `http://IP_DE_LA_CAMARA/` y el stream MJPEG en:

```text
http://IP_DE_LA_CAMARA:81/stream
```

La computadora que ejecute el detector debe estar en la misma red que la cámara.

## Detector Python

El detector consume el stream MJPEG y ejecuta inferencia local con Ultralytics YOLO. Requiere Python `>=3.11,<3.14`.

Desde la raíz del repositorio, crear y activar un entorno virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e vision/detector
```

Si PowerShell bloquea la activación de scripts, puede ejecutarse el intérprete del entorno directamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -e vision/detector
```

Ejecutar el detector apuntando al stream de la cámara:

```powershell
python vision/detector/detect_esp32cam.py --url http://IP_DE_LA_CAMARA:81/stream --model yolov8n.pt --show
```

`yolov8n.pt` se descarga por Ultralytics si no existe localmente. También se puede indicar una ruta propia con `--model`. Para guardar las anotaciones, agregar `--save`, que genera `output.mp4`; para limitar el ancho, usar por ejemplo `--max-w 640`. El programa termina con `q` o `Esc` cuando se usa `--show`.

Ejemplo sin ventana gráfica:

```powershell
python vision/detector/detect_esp32cam.py --url http://IP_DE_LA_CAMARA:81/stream --model yolov8n.pt --save --max-w 640
```

Los modelos descargados y los videos generados no deben incorporarse al repositorio.

## Validación rápida de firmware

Desde la raíz:

```powershell
pio run -d firmware/sensor-controller -e esp32dev
pio run -d firmware/camera-server -e esp32cam
pio run -d firmware/camera-server -e esp32s3
```

Para comprobar que el entorno Python está instalado correctamente:

```powershell
.\.venv\Scripts\python.exe -c "import cv2, numpy, ultralytics; print('Dependencias del detector OK')"
```

## Organización objetivo

La migración progresiva apunta a separar:

- `firmware/`: proyectos PlatformIO independientes.
- `vision/`: detector y pruebas Python.
- `protocol/mqtt/`: contrato versionado de comunicación.
- `docs/`: hardware, operación y decisiones arquitectónicas.
- `config/examples/`: ejemplos sin credenciales reales.

## Seguridad

No introducir credenciales reales, modelos descargados ni resultados de ejecución en commits. Los puertos serie son configuraciones locales y no forman parte de CI. La configuración MQTT actual usa `broker.emqx.io:1883` y el tópico legado `semaforo/esp32`; su contrato y limitaciones están documentados en `protocol/mqtt/README.md`.
