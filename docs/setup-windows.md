# Puesta en marcha en Windows (PowerShell)

Movida desde `reference.md` §8 el 2026-11-08 sin cambios de contenido técnico. Para Linux ver [setup-linux.md](setup-linux.md). Los COM5/COM6 son ejemplos locales.


Comandos desde la raíz en PowerShell. La instalación depende de reparar el empaquetado; la publicación automática y el selector de modo todavía no están implementados. No pasar opciones MQTT, `--device` o perfiles propuestos a los scripts/configuraciones actuales como si ya existieran.

### Entorno Python y PlatformIO

Con Python 3.12 disponible, crear el entorno solo si no existe:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install platformio
.\.venv\Scripts\python.exe -m pip install -e .\vision\detector
```

Se puede usar el ejecutable del entorno sin activarlo, evitando bloqueos de scripts PowerShell. Mosquitto se instala aparte. La comprobación `import cv2, numpy, ultralytics` valida importaciones, no inferencia ni MQTT.

### Credenciales, carga y monitor serie

```powershell
if (-not (Test-Path -LiteralPath '.\firmware\camera-server\include\secrets.h')) {
    Copy-Item -LiteralPath '.\firmware\camera-server\include\secrets.h.example' -Destination '.\firmware\camera-server\include\secrets.h'
}
.\.venv\Scripts\python.exe -m platformio device list
```

Completar `WIFI_SSID_LOCAL` y `WIFI_PASS_LOCAL`, porque `main.cpp` selecciona `WifiEnv::LOCAL`. `Wokwi-GUEST` corresponde al ejemplo de simulación y no sustituye la red física. No sobrescribir secretos locales existentes.

Sustituir `COMx`. El ejemplo corresponde solo a hardware compatible con `esp32cam`:

```powershell
$cameraEnv = 'esp32cam'
$cameraPort = 'COMx'
.\.venv\Scripts\python.exe -m platformio run -d firmware/camera-server -e $cameraEnv
.\.venv\Scripts\python.exe -m platformio run -d firmware/camera-server -e $cameraEnv -t upload --upload-port $cameraPort
.\.venv\Scripts\python.exe -m platformio device monitor --port $cameraPort --baud 115200
```

Usar el entorno actual `esp32s3` únicamente tras confirmar los pines de esa placa/cámara. Seguir su procedimiento físico de carga/reset y cerrar el monitor antes de otra carga si ocupa el puerto. Los COM5/COM6 de ejemplo no son requisitos y no se deben imponer a CI.

### Página, captura y stream

Tomar la IP del monitor: página `http://IP_CAMARA/`, captura `http://IP_CAMARA/capture` y stream `http://IP_CAMARA:81/stream`. La PC debe alcanzar esa IP por la red. Primero probar navegador y detector por separado; cerrar el consumidor de vídeo del navegador antes de probar Python. No dar por validada la concurrencia de varios clientes del stream.

### Detectores actuales

Ejecutar uno por vez, reemplazando `IP_CAMARA` y proporcionando un modelo local si no se admite descarga:

```powershell
.\.venv\Scripts\python.exe vision/detector/detect_esp32cam.py --url http://IP_CAMARA:81/stream --model yolov8n.pt --show
```

```powershell
.\.venv\Scripts\python.exe vision/detector/cam_detection.py --url http://IP_CAMARA:81/stream --model yolov8n.pt --show --emit-every 1
```

`--show` permite salir con `q` o `Esc`; `--save` genera `output.mp4` y `--max-w` limita el ancho. El segundo script puede escribir snapshots con `--jsonl`; no confundir ese archivo ni su salida de consola con publicación MQTT. Una ventana con anotaciones valida solo adquisición e inferencia.

### Broker y prueba manual de transporte

`python -m http.server 1883`, incluido todavía en la documentación del protocolo, crea HTTP y debe corregirse. Se necesita un broker MQTT real.

Para una red privada de laboratorio puede crearse `artifacts/mosquitto.local.conf` con:

```conf
listener 1883
allow_anonymous true
```

Este ensayo permite acceso sin credenciales; si se elige un broker autenticado, configurar ese acceso en ambos extremos. Mosquitto documenta que los valores predeterminados sin listener restringen conexiones al equipo local. El listener y la política deben ser explícitos para conectar ESP desde la red. [Autenticación](https://mosquitto.org/documentation/authentication-methods/) y [configuración oficial](https://mosquitto.org/man/mosquitto-conf-5.html).

Con archivo creado y utilidades en `PATH`, iniciar en una terminal:

```powershell
mosquitto -c .\artifacts\mosquitto.local.conf -v
```

Si un servicio ya ocupa 1883, usar su configuración o detener conscientemente esa instancia antes de iniciar otra. Permitir acceso en la red privada sin desactivar globalmente el firewall. Para probar desde otro equipo o ESP usar la IP LAN del servidor.

En otra terminal escuchar y, desde una tercera, publicar:

```powershell
mosquitto_sub -h 127.0.0.1 -p 1883 -t "trafico/v1/+/detections" -v
```

```powershell
mosquitto_pub -h 127.0.0.1 -p 1883 -t "trafico/v1/cam-01/detections" -m "prueba-manual-de-transporte"
```

Ese texto solo prueba transporte, no contrato JSON ni integración. El cierre del hito requiere recibir datos del procesador real sin publicar manualmente. Si se acuerda retorno al ESP, comprobar el resultado recibido en serie antes de conectarlo a actuadores.
