## Retomar el proyecto sin el historial del chat

Punto de entrada para `project-mentor`. Corte de contexto: **2026-11-08, ~20:00**, zona `America/Buenos_Aires`. El propietario reinicia la computadora para aplicar actualizaciones del sistema y retoma después. Este apartado reemplaza al del 21/10/2026.

### Contexto mínimo

- **Producto:** detección y estado del tráfico con cámaras ESP32, con semaforización adaptativa. Documentación solo para el propietario y para agentes: sirve de registro y guía al retomar.
- **Hito inmediato:** presentación **informal** del MVP el **viernes 13/11/2026**. Audiencia cercana, sin requisito formal.
- **Qué se muestra:** recorrido estable cámara → detección → MQTT → decisión → semáforo **simulado**, con énfasis en arquitectura y comunicación sólida. Métricas que le importan: mejora del flujo y precisión de detección; la prioridad real es la arquitectura. Todo lo inestable queda fuera.
- **Hardware de la demo:** ESP32-CAM-MB con OV2640 (cámara que realmente funciona hoy), ESP32-S3-N16R8 con OV5640 (pinout y alimentación sin validar), PC con YOLO. Sin LEDs ni semáforos físicos. NodeMCU disponible para pruebas MQTT.
- **Máquina:** CachyOS (Linux), primera vez que se ejecuta el proyecto aquí. Los documentos históricos asumen Windows/PowerShell.

### Decisiones vigentes

D01–D07 como en [reference.md](reference.md) §12. Confirmadas el 08/11/2026:

- **D08** percepción, decisión y actuación separadas y unidas solo por MQTT.
- **D09** en el MVP el ESP solo captura, transmite y declara estado; sin inferencia ni métricas.
- **D10** semáforo simulado por software.
- **D11** política mínima de prioridad acotada al MVP (excepción a I6); la política definitiva sigue pendiente.
- **D12** el S3/OV5640 entra solo con pinout y alimentación validados; si no, el segundo acceso usa video o webcam.
- **D13** `docs/` reorganizada (D02 reemplazada): índice, MVP, referencia larga, guías por sistema operativo; contrato MQTT solo en `protocol/mqtt/README.md`; estudios y guion narrativo en el vault de Obsidian.

Respuesta de diseño dada al propietario: el servidor calcula espera y prioridad, pero en un proceso separado que solo habla por MQTT; el ESP además de transmitir video publica identidad/estado y Last Will, sin calcular nada.

### Qué existe y qué no

- **Existe:** firmware `camera-server` (HTTP, captura, MJPEG en `:81/stream`), `detect_esp32cam.py`, `cam_detection.py` (tracking, snapshots JSON/JSONL).
- **No existe:** publicación MQTT de cámara/detector, controlador, política, semáforo simulado, modo seguro, selector externo/local, métricas de espera/cruce.
- **Sin verificar en Linux:** compilación y carga del firmware, stream, detector. Nada se ejecutó en esta sesión: el sandbox no veía USB, red ni GPU, y `pio`/`uv` no estaban instalados.
- **Problemas conocidos:** empaquetado Python (dos módulos), `lap` no declarado, semántica de conteos en `cam_detection.py`, reconexión con captura abierta sin frames.

### Diagnóstico del fallo de `camera-server` con PlatformIO (análisis estático)

Comparado con la versión de Arduino IDE (`/mnt/hdd/UTN - CODAPLI/CameraWebServer/`): el código es equivalente (solo guardas LEDC y origen de credenciales). Causas probables, sin confirmar: puertos `COM5`/`COM6` en Linux; `secrets.h` ausente (está ignorado por Git); `platform = espressif32` sin versión fija; hardware/alimentación. El sketch de Arduino solo probó el modelo AI Thinker, nunca el S3. `/mnt/hdd/UTN - CODAPLI/MqttComs/` es el equivalente Arduino de `sensor-controller` (publica `Probando Mosquitto` cada segundo en `semaforo/esp32`). Ambos directorios de Arduino contienen credenciales WiFi reales en texto plano: no copiarlas al repo.

### Estado del árbol de trabajo (sin commit)

Nada se commiteó en esta sesión. Cambios hechos:

- Nuevos: `docs/MVP.md`, `docs/reference.md` (era `docs/README.md`), `docs/setup-linux.md`, `docs/setup-windows.md` (§8 movida de la referencia).
- Reescritos: `docs/README.md` (ahora índice), este archivo, `protocol/mqtt/README.md` (contrato único, corrige `http.server`).
- Actualizados: `.agents/skills/project-mentor/SKILL.md` y `.agents/rules/coding-agent.md` (rutas a `reference.md`, Linux), `CONTRIBUTING.md` (sin Dev Container), `README.md` (puntero a Linux e índice).
- Vault de Obsidian: `MVP Semáforo Inteligente.md` recibió un puntero a `docs/MVP.md`.
- **Cambio ajeno a esta sesión:** `firmware/camera-server/include/board_config.h` aparece modificado (`#define CAMERA_MODEL_ESP32_CAM_BOARD` descomentado). El árbol estaba limpio al inicio, así que lo cambió el propietario. Hoy es inofensivo porque `AI_THINKER` aparece antes en la cadena `#elif` de `camera_pins.h`, pero conviene revertirlo o confirmarlo.
- Los archivos `.bashrc`, `.zshrc`, `.gitconfig`, `.mcp.json`, etc. que `git status` lista como no versionados son artefactos del sandbox de la sesión, no archivos del repo.

### Actualización 2026-11-08 (tarde)

- **M0 cámara:** el "no imprime la IP" era señal WiFi débil; con mejor ubicación el stream es estable y el monitor muestra la IP (`uv run pio device monitor --port /dev/ttyUSB0 --baud 115200 --rts 0 --dtr 0`, ver [setup-linux.md](setup-linux.md) §3 y §7). `board_config.h` ya no figura modificado; `platformio.ini` y `main.cpp` sí (cambios de depuración del propietario, no revisados).
- **M1 escrito, sin probar contra broker:** `vision/detector/traffic_mqtt.py`, flags `--mqtt-host/--camera-id/--approach-id` en `cam_detection.py`, `visible_count` cuenta cajas sin ID, `unavailable` si cae el stream o falla la inferencia, `paho-mqtt` en `pyproject.toml`. 6 tests de lógica OK. Pendiente: instalar `paho-mqtt` y verificar con `mosquitto_sub` y YOLO real (primer paso al retomar).
- Siguiente: M2 (controlador y semáforo simulado), proceso separado que solo habla por MQTT.

### Por dónde continuar (anterior a esta actualización)

1. Verificar que el entorno sobrevivió al reinicio: `git status --short`, `id` (grupo `uucp` si se agregó), `command -v uv pio mosquitto`.
2. Ejecutar **M0** de [MVP.md](MVP.md) §10 siguiendo [setup-linux.md](setup-linux.md): instalar `uv`, Python 3.12, `platformio`; crear `secrets.h`; compilar `esp32cam`; cargar; abrir `/capture` y `:81/stream`; detector con `--show`. Registrar cada resultado en la tabla de verificación de `setup-linux.md` §6.
3. Pedir al propietario la salida de `pio device list` y del primer `pio run`, y el estado del `board_config.h` modificado.
4. Después, **M1**: detector → MQTT (agregar `paho-mqtt`, corregir semántica de `visible_count`, publicar en `trafico/v1/<camera_id>/detections`). Luego M2 (controlador y semáforo simulado), M3, M4.
5. No hacer commit, revertir ni limpiar cambios del usuario sin que sea parte de la tarea. No reactivar `sensor-controller` por iniciativa propia.

Calendario del hito: M0 dom 8 – lun 9, M1 mar 10, M2 mié 11, M3 jue 12, M4 jue 12 – vie 13. Orden de recorte en MVP.md §10.

### Decisiones abiertas

- Parámetros de la política (ciclo base, verde mínimo y máximo, vigencia T del dato).
- Qué hacer con el S3: validar pinout y alimentación o usar fuente alternativa (D12).
- Si se commitea esta reorganización y en qué rama (la actual es `fix/cam-web-server-stream`).
- Documentos aparte que el propietario pidió documentar fuera del MVP: interfaces, hardware/software, criterios de aceptación y plan de pruebas, riesgos, guion de demo y contingencia.

### Lectura por necesidad

| Necesidad | Documento |
| --- | --- |
| Qué construir esta semana | [MVP.md](MVP.md) |
| Instalar y correr | [setup-linux.md](setup-linux.md) |
| Hardware, métricas, modo local, P01–P08, I0–I6 | [reference.md](reference.md) |
| Topics y payloads | [../protocol/mqtt/README.md](../protocol/mqtt/README.md) |

Los README antiguos pueden describir comportamiento desactualizado. Las instrucciones explícitas del propietario definen el alcance; el código y las pruebas determinan qué está implementado. Si difieren, registrar la discrepancia.

Instrucción sugerida para retomar:

> Usa project-mentor. Lee `docs/agent_session_context.md`, contrasta con `git status` y continúa por el paso 1 de "Por dónde continuar". Distingue acuerdos de propuestas y registra los resultados de verificación en `docs/setup-linux.md`.
