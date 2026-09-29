# Detector de visión

`detect_esp32cam.py` consume un stream MJPEG del firmware de cámara y ejecuta inferencia YOLO localmente. Actualmente solo muestra anotaciones y puede guardar vídeo; no publica MQTT ni controla el semáforo.

## Entorno

Crear un entorno virtual e instalar el proyecto con:

```text
python -m venv .venv
python -m pip install -e .
```

El modelo se proporciona mediante `--model`. No se incluye una política de descarga o redistribución hasta revisar procedencia, checksum y licencia.

Ejemplo de ejecución:

```text
python vision/detector/detect_esp32cam.py --url http://CAMERA_IP:81/stream --model PATH_TO_MODEL --show
```