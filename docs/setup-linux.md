# Puesta en marcha en Linux (CachyOS / Arch)

Redactada el 2026-11-08. **Estado de verificación (actualizado el 2026-11-12): el propietario ejecutó la cadena ESP32-CAM → detector con YOLO real → Mosquitto local → `mosquitto_sub` el 2026-11-11 y funcionó como se esperaba, con dos hallazgos menores (H-A y H-B, ver §6; sus correcciones están en curso y sin verificar con hardware).** Los demás pasos siguen sin registro; ver la tabla de §6. Al correrlos, registrar al final qué funcionó y qué no. Para Windows ver [setup-windows.md](setup-windows.md).

Todos los comandos se ejecutan desde la raíz del repositorio. El shell de login es fish, por eso no se usa `source .venv/bin/activate`: se llama directamente a `.venv/bin/python`.

## 0. Qué esperar de esta máquina

- Solo estaba instalado Python 3.14. El detector exige `>=3.11,<3.14`, así que se necesita 3.12.
- Se encontraron instalados `mosquitto`, `git`, `ffmpeg` y `docker`. Docker no hace falta.
- No estaban `uv`, `pio` ni `~/.platformio`.
- Los puertos `COM5`/`COM6` de `platformio.ini` son de Windows. En Linux se pasa el puerto con `--upload-port`/`--port`; no hace falta editar el archivo.

## 1. Herramientas y permiso del puerto serie

```bash
sudo pacman -S --needed uv git mosquitto
sudo usermod -aG uucp $USER      # cerrar sesión y volver a entrar para que aplique
uv python install 3.12
uv tool install platformio
```

`uucp` es el grupo que da acceso a `/dev/ttyUSB*` y `/dev/ttyACM*` en Arch. Comprobar con `id` después de volver a entrar.

## 2. Entorno Python del detector

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python numpy opencv-python "ultralytics>=8.3,<9" lap paho-mqtt
```

- No usar `pip install -e vision/detector`: falla por tener dos módulos de nivel superior (problema registrado en [reference.md](reference.md) §7).
- `lap` se instala a mano: el seguimiento lo necesita y un venv de `uv` no trae `pip` para que Ultralytics lo instale solo.
- `paho-mqtt` lo usa `cam_detection.py` cuando se pasa `--mqtt-host` (hito M1); la publicación contra Mosquitto local se verificó el 2026-11-11 (§4 y §6).
- En Linux, `torch` se instala con soporte CUDA por defecto (varios GB). Si el driver NVIDIA funciona (`nvidia-smi` responde), la RTX 2060 se usa automáticamente. Si no hay driver o se prefiere CPU:

```bash
uv pip install --python .venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

Comprobación:

```bash
.venv/bin/python -c "import torch, cv2, ultralytics; print(torch.__version__, torch.cuda.is_available())"
```

Descargar el modelo **antes de una demo**, con internet (se baja solo la primera vez que se carga `yolov8n.pt`).

## 3. Firmware de la cámara

```bash
cp firmware/camera-server/include/secrets.h.example firmware/camera-server/include/secrets.h
```

Editar `WIFI_SSID_LOCAL` y `WIFI_PASS_LOCAL` (el firmware usa `WifiEnv::LOCAL`). `Wokwi-GUEST` no sirve para hardware real. `secrets.h` está ignorado por Git: no se versiona.

Requisitos de red: el ESP32 solo usa 2,4 GHz y la PC debe estar en la misma red. Si el router aísla clientes entre sí, el stream no llegará; un hotspot propio es una alternativa.

```bash
pio device list                                   # ESP32-CAM-MB: /dev/ttyUSB0 ; ESP32-S3 por USB nativo: /dev/ttyACM0
pio run -d firmware/camera-server -e esp32cam
pio run -d firmware/camera-server -e esp32cam -t upload --upload-port /dev/ttyUSB0
pio device monitor -d firmware/camera-server -e esp32cam --port /dev/ttyUSB0 --baud 115200
```

Comando de monitor verificado en esta máquina (el propietario lo ejecuta con `uv run`, que usa el entorno virtual):

```bash
uv run pio device monitor --port /dev/ttyUSB0 --baud 115200 --rts 0 --dtr 0
```

- `--rts 0 --dtr 0` dejan las líneas **RTS** y **DTR** del adaptador USB-serie en nivel bajo al abrir el puerto. En las placas ESP32 estas dos líneas están cableadas al circuito de autorreset: **DTR** se conecta a `IO0` (modo de arranque) y **RTS** a `EN` (reset del chip). Si el monitor las deja activas, puede mantener el chip en reset o arrancarlo en modo de descarga, y el log queda en silencio. Con ambas en 0 el monitor solo escucha y no reinicia ni bloquea la placa.
- Para ver el arranque completo, pulsar RST con el monitor ya abierto.
- El monitor imprime la IP al conectarse.
- Cerrar el monitor antes de volver a cargar: ocupa el puerto.
- Si el puerto no aparece o da permiso denegado: revisar el grupo `uucp`, el cable (debe ser de datos) y `dmesg | tail`.
- **No cargar `-e esp32s3` hasta validar pinout y alimentación (D12).** El perfil usa pines de una S3-EYE, y el sketch de Arduino solo se probó con el modelo AI Thinker. Para cargar el S3 se mantiene BOOT y se pulsa RST.

Qué mirar en el monitor serie si algo falla:

| Síntoma | Causa probable |
| --- | --- |
| `Camera init failed with error 0x...` | Pines/modelo de cámara incorrectos, PSRAM no detectada o cámara mal conectada |
| Puntos infinitos en `WiFi connecting` o stream con cortes | Credenciales, red de 5 GHz, `secrets.h` sin editar o **señal débil** (ver §7.5: era la causa real el 2026-11-08) |
| Reinicios continuos / `Brownout` | Alimentación USB insuficiente; probar otro cable o puerto |
| Compila pero no abre la página | Firewall de la PC o aislamiento de clientes del router |

Comprobar los servicios con la IP del monitor:

```bash
curl -I http://IP_CAMARA/
curl -o /tmp/captura.jpg http://IP_CAMARA/capture
```

El stream está en `http://IP_CAMARA:81/stream`.

## 4. Detector

```bash
.venv/bin/python vision/detector/detect_esp32cam.py --url http://IP_CAMARA:81/stream --show
.venv/bin/python vision/detector/cam_detection.py --url http://IP_CAMARA:81/stream --show --jsonl salida.jsonl
```

- `--show` se cierra con `q` o `Esc`. `--save` escribe `output.mp4`.
- Cerrar antes el navegador que esté mostrando el stream; no está validado con dos clientes.
- Si `--show` falla por Qt en Wayland: `QT_QPA_PLATFORM=xcb .venv/bin/python ...`.
- Probar sin cámara pasando un archivo de video como `--url` (previsto en RF-06; aún sin verificar).
- `cam_detection.py` imprime snapshots JSON por consola. Con `--mqtt-host` además publica (hito M1, escrito el 2026-11-08; **verificado contra Mosquitto local el 2026-11-11**, ver receta abajo):

```bash
mosquitto_sub -h 127.0.0.1 -t 'trafico/v1/+/detections' -v      # terminal 1
.venv/bin/python vision/detector/cam_detection.py --url http://IP_CAMARA:81/stream \
  --mqtt-host 127.0.0.1 --camera-id cam-01 --approach-id acceso-01 --show        # terminal 2
```

- Sin cámara: `--url archivo.mp4` (RF-06). Sin `--mqtt-host` no se publica nada.
- Cada ~1 s llega un JSON con `status: ok` y conteos (ceros si no hay vehículos). Si el stream cae o la inferencia falla llega `status: unavailable` sin `metrics`. Al cerrar el detector debería llegar un último `unavailable`, pero **con Ctrl+C no llegó** (H-B, §6; corrección en curso, sin verificar). El controlador no debe depender de ese mensaje: el modo seguro se basa en la vigencia T del dato.
- `paho-mqtt` debe estar instalado (paso §2).
- Hallazgo H-A: tras un tiempo sin conexión al stream, el detector cierra la ventana y termina (hace `break` tras `--reconnect` aperturas fallidas). Corrección en curso (reintento indefinido con espera creciente, RNF-01/RNF-02); sin verificar.

Receta verificada el 2026-11-11 (CachyOS, ESP32-CAM-MB con OV2640 real, Mosquitto local, YOLO real). Con `IP_CAMARA` reemplazada por la IP que imprime el monitor serie:

```bash
mosquitto_sub -t 'trafico/v1/#' -v                                                       # terminal 1
.venv/bin/python vision/detector/cam_detection.py --url http://IP_CAMARA:81/stream \
  --mqtt-host localhost --camera-id cam-01 --approach-id acceso-01 --show                # terminal 2
```

(En el registro del propietario el comando del detector se anotó con `cam_detection.py --mqtt-host localhost --camera-id cam-01 --approach-id acceso-01 --show`; la URL del stream es `:81/stream` de la cámara.)

### Controlador y semáforo simulado (M2)

Tres procesos independientes unidos por MQTT (`trafico/v1/...`, ver [protocolo](../protocol/mqtt/README.md) §2). Solo necesitan `paho-mqtt` (ya instalado en el entorno del detector, §2); no hay que instalar nada más. Se ejecutan desde la raíz del repositorio, cada uno en su terminal, con Mosquitto escuchando en el 1883 (§5):

```bash
mosquitto_sub -h 127.0.0.1 -t 'trafico/v1/inter-01/#' -v                       # terminal 1: commands y state
.venv/bin/python control/traffic_light_sim.py --mqtt-host 127.0.0.1             # terminal 2: semáforo
.venv/bin/python control/traffic_controller.py --mqtt-host 127.0.0.1            # terminal 3: controlador
.venv/bin/python vision/detector/cam_detection.py --url http://IP_CAMARA:81/stream \
  --mqtt-host 127.0.0.1 --camera-id cam-01 --approach-id acceso-01              # terminal 4: acceso 1 real
```

- Orden de arranque recomendado: broker, semáforo, controlador y por último el detector (el semáforo debe existir antes para que el primer verde no llegue a un todo-rojo inicial sin cumplir).
- Valores por defecto: `--intersection-id inter-01`, `--approaches acceso-01,acceso-02`, verde 5-20 s, amarillo 2 s, todo-rojo 2 s, vigencia `--fresh 5`, ciclo fijo `--fixed-green 10`. Flags del controlador desde la corrección 2026-11-12: `--demand-present 0.5` (vehículos suavizados desde los que un acceso "tiene demanda"), `--switch-margin 0.5` (ventaja mínima sobre el verde actual para cambiar por demanda), `--fail-after 10` (s sin `ok` de un acceso para pasar a ciclo fijo) y `--recover-after 3` (s seguidos con `ok` en todos para volver a adaptativo); `--verbose` muestra el detalle por mensaje. Ver `--help` de cada script. Si cambias tiempos, usa los mismos en ambos procesos (el semáforo valida con ellos).
- El controlador arranca en `mode: fixed` / `fixed_cycle_no_data` y pasa a adaptativo cuando **todos** los accesos configurados llevan 3 s con datos vigentes; vuelve a fijo si alguno lleva 10 s sin `ok`. Si ningún acceso tiene demanda, mantiene el verde actual sin comandos (log `reposo: sin demanda, se mantiene ...`).
- Log del semáforo: `CAMBIO DE FASE` = la fase cambió; `ACTUALIZA MODO` = misma fase con modo o motivo nuevo; `INICIO` = arranque. Los campos `orden: modo=... motivo=...` son los de la última orden recibida (en una transición amarillo/todo-rojo/verde el motivo es el que originó el cambio). No son el modo actual del controlador.
- Segundo detector simulado con `mosquitto_pub` (repetir cada ~1 s con `seq` creciente y `processed_at` actual en UTC):

```bash
mosquitto_pub -t trafico/v1/cam-02/detections -m "{\"v\":1,\"camera_id\":\"cam-02\",\"approach_id\":\"acceso-02\",\"session_id\":\"sim-02\",\"seq\":1,\"processed_at\":\"$(date -u +%FT%TZ)\",\"status\":\"ok\",\"metrics\":{\"visible_count\":6}}"
```

- Probar: dar más conteo a un acceso y ver el cambio de fase tras el verde mínimo; dejar de publicar y ver `fixed_cycle_no_data` pasados 10 s sin `ok`; reanudar y ver `data_recovered` / `adaptive` tras 3 s; reiniciar controlador y semáforo por separado; publicar a mano un comando con dos verdes en `trafico/v1/inter-01/commands` y ver el `RECHAZADO` en el semáforo.
- Tests de lógica (sin broker): `python3 -m unittest discover -s control/tests` (o `.venv/bin/python -m pytest control/tests`).
- Sin Last Will del semáforo: si muere, el `state` retenido conserva la última fase.

## 5. Broker MQTT

Mosquitto, por defecto, solo acepta conexiones locales. Para laboratorio en red privada:

```bash
mkdir -p artifacts          # ignorado por Git
printf 'listener 1883 0.0.0.0\nallow_anonymous true\n' > artifacts/mosquitto.local.conf
mosquitto -c artifacts/mosquitto.local.conf -v
```

Si ya hay un servicio usando el 1883 (`ss -ltn | grep 1883`), detenerlo antes. Si hay firewall, abrir `1883/tcp` solo para la red privada.

En otra terminal, escuchar y publicar una prueba de transporte:

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'trafico/v1/+/detections' -v
mosquitto_pub -h 127.0.0.1 -p 1883 -t 'trafico/v1/cam-01/detections' -m prueba
```

Eso solo prueba el transporte. El hito M1 se cierra cuando llegan datos reales del detector sin publicar a mano. Un ESP necesita la **IP LAN de la PC** como broker (`localhost` en el ESP es el propio ESP).

### Probar un ESP contra el broker con el firmware legado

Es el único firmware que hoy habla MQTT (NodeMCU `esp32dev`). Es independiente del detector, que ya publica por MQTT (§4).

```bash
cp firmware/sensor-controller/include/secrets.h.example firmware/sensor-controller/include/secrets.h
# editar WIFI_* y LOCAL_BROKER = IP LAN de la PC
pio run -d firmware/sensor-controller -e esp32dev -t upload --upload-port /dev/ttyUSB0
mosquitto_sub -h 127.0.0.1 -t 'semaforo/esp32' -v
```

- Publica `Probando Mosquitto` cada segundo en `semaforo/esp32`.
- La orden `mosquitto_pub -t semaforo/esp32 -m Detener` activa su callback de parada.
- Su `monitor_port` está fijado en `/dev/ttyUSB1`; usar `--port` si cambia.
- Es referencia legada, con hardware de sensores pausado (D01).

## 6. Registro de verificación

Completar al ejecutar. Una línea por prueba, con fecha.

| Fecha | Paso | Resultado |
| --- | --- | --- |
| | `uv python install 3.12` y venv | |
| | `torch.cuda.is_available()` | |
| | `pio run -e esp32cam` | |
| | Carga y arranque de la ESP32-CAM | |
| | `/capture` y `:81/stream` desde la PC | |
| 2026-11-11 | Detector con `--show` sobre la cámara (YOLO real, ESP32-CAM-MB/OV2640) | Funcionó como se esperaba, salvo H-A (ver abajo) |
| | Mosquitto recibe desde otro equipo/ESP | Pendiente de verificar (la prueba del 2026-11-11 fue con broker local, `localhost`) |
| 2026-11-08 | Tests M1 (`python3 -m unittest discover -s vision/detector/tests`) | 6 de 6 OK con el Python del sistema (solo lógica de payload y conteos; sin cv2/YOLO/paho) |
| 2026-11-08 | M1 contra Mosquitto real | **No probado**: `.venv/bin/python` no es ejecutable desde el sandbox y `paho-mqtt` no está instalado. Pendiente del propietario |
| 2026-11-11 | Cadena completa: ESP32-CAM → `:81/stream` → `cam_detection.py --mqtt-host localhost --camera-id cam-01 --approach-id acceso-01 --show` → `mosquitto_sub -t 'trafico/v1/#' -v` (Mosquitto local) | Publicación MQTT recibida en `mosquitto_sub`; "todo funcionó de forma esperada" salvo H-A y H-B. Informado por el propietario. Cierra la prueba pendiente de la fila 2026-11-08 "M1 contra Mosquitto real" |
| 2026-11-11 | H-A: el detector termina tras un tiempo sin stream | **Corrección en curso, sin verificar con hardware.** Causa (análisis de `cam_detection.py`): tras `--reconnect` (3) aperturas fallidas hace `break`, se cierra la ventana OpenCV y el proceso termina. Contradice RNF-02/RNF-01 (debe reintentar indefinidamente). Corrección prevista: reintento indefinido con espera creciente. Menor según el propietario |
| 2026-11-11 | H-B: con Ctrl+C no se publica el `unavailable` final | **Corrección en curso, sin verificar con hardware.** Causa: `KeyboardInterrupt` no se captura y se salta el bloque de cierre; además `publish()` es asíncrono y el `disconnect()` inmediato podría perder el mensaje. Corrección prevista: `try/finally`, esperar confirmación de envío y Last Will del detector. El controlador no debe depender de ese mensaje (modo seguro por vigencia T del dato). Menor según el propietario |
| 2026-11-11 | Cuadro vacío, reconexión del ESP, caída del broker | No registrado |
| 2026-11-12 | M2: `python3 -m unittest discover -s control/tests` | 36 de 36 OK con Python 3.14 del sistema (lógica pura, sin paho) |
| 2026-11-12 | M2 contra Mosquitto local (puerto 18830, accesos simulados con `mosquitto_pub`, paho 2.2.0 del entorno del detector vía PYTHONPATH) | Cambio por demanda, `fixed_cycle_no_data` tras T, vuelta a `adaptive`, rechazo de dos verdes y reinicios por separado observados. Pendiente: cadena con detector/ESP real |
| 2026-11-08 | `command -v uv pio mosquitto` | `uv` y `mosquitto` presentes; **`pio` ausente**, sin `~/.platformio` (no se puede compilar ni cargar desde el sandbox) |
| 2026-11-08 | `id` | Grupos: `pedror01`, `nobody`. **Sin `uucp`** (visto desde el sandbox; confirmar en la terminal propia) |
| 2026-11-08 | `lsusb` / `/dev/ttyUSB*` | `lsusb` ve un CH340 (`1a86:7523`), pero **no existe `/dev/ttyUSB*`** dentro del sandbox: no se pudo abrir el puerto ni leer el log |
| 2026-11-08 | `secrets.h` | Existe, ignorado por Git, con los 8 `#define` esperados (`WIFI_SSID/PASS_{LOCAL,CODAPLI,MOBILE,WOKWI}`). Valores no leídos ni registrados |
| 2026-11-08 | Selección de pines | `-DCAMERA_MODEL_AI_THINKER` (platformio.ini) gana sobre `CAMERA_MODEL_ESP32_CAM_BOARD` (board_config.h) por el orden `#elif` en `camera_pins.h` (líneas 160 y 220): el cambio local es inofensivo hoy |

## 7. Depuración: el firmware `camera-server` no imprime la IP

Registrado el 2026-11-08. Análisis **estático**: no se compiló ni se cargó nada (ver §6). Distingue hechos, inferencias y propuestas; las propuestas **no están acordadas** hasta que el propietario las confirme.

### 7.1 Hechos (verificados leyendo `firmware/camera-server/src/main.cpp`)

- La IP se imprime **una sola vez**, en la última línea de `setup()` (`Camera Ready! Use 'http://...`), después de tres pasos que pueden impedir llegar ahí:
  1. `esp_camera_init()` falla → `Serial.printf("Camera init failed with error 0x%x", err); return;`. El `return` sale de `setup()` **sin conectar WiFi**. El mensaje no lleva `\n`.
  2. `while (WiFi.status() != WL_CONNECTED)` es un bucle **sin tiempo límite ni diagnóstico**: solo imprime puntos.
  3. `startCameraServer()` precede a la impresión de la IP: si cuelga o reinicia, la IP no sale aunque WiFi esté conectado.
- `loop()` no hace nada: si se abre el monitor después del arranque, el mensaje ya pasó y no se repite.
- `platformio.ini` fija `upload_port`/`monitor_port` en `COM5`/`COM6` (Windows). Sin `--port` en Linux, `pio device monitor` y `upload` apuntan a un puerto inexistente.
- `platform = espressif32` sin versión: el core Arduino puede cambiar entre máquinas y fechas.
- El código es equivalente al de Arduino IDE que funcionó (§ contexto de sesión); la diferencia está en entorno, no en lógica.

### 7.2 Hipótesis (inferencias, ordenadas por costo de descartar)

| # | Hipótesis | Qué se vería en el log | Prueba |
| --- | --- | --- | --- |
| H1 | Se abrió el monitor tras el arranque y el mensaje único se perdió | Nada, o solo logs del servidor (`log_i`) al navegar | Pulsar **RST** con el monitor abierto |
| H2 | Falla `esp_camera_init` y se aborta antes de WiFi | `Camera init failed with error 0x...` al final y silencio | Leer el código de error (0x105 no detectada, 0x20001/0x101 memoria/PSRAM, 0x103 pines/SCCB); revisar cinta de la cámara y modelo de pines |
| H3 | WiFi no conecta | `WiFi connecting....` con puntos infinitos | SSID/clave en `secrets.h` (`WIFI_*_LOCAL`), red solo 2,4 GHz, sin caracteres raros |
| H4 | Brownout o reinicio en bucle | `Brownout detector was triggered` o el banner `ets ...` repetido | Otro cable/puerto USB, sin hub; ver si el banner se repite |
| H5 | Sin permiso o puerto equivocado → el "log" es de otro origen | `Permission denied` o `No such file` | `id` (¿`uucp`?), `ls -l /dev/ttyUSB*`, `dmesg \| tail`, pasar `--port` |
| H6 | `startCameraServer` falla/cuelga | Se ve `WiFi connected` pero no `Camera Ready`; posibles `log_e` | Buscar `Starting web server on port` en el log |
| H7 | Velocidad o consola distinta | Caracteres basura | Monitor a 115200 |

### 7.3 Lista de depuración (propuesta, en este orden)

Marcar cada ítem con fecha y resultado en la tabla del §7.5.

1. **Entorno** (terminal propia): `id` (debe incluir `uucp`; si no, `sudo usermod -aG uucp $USER` y volver a iniciar sesión), `ls -l /dev/ttyUSB*`, `dmesg | tail`. Instalar `uv tool install platformio` si falta `pio`.
2. **Puerto libre**: cerrar todo monitor/IDE que lo use (`fuser /dev/ttyUSB0`).
3. **Capturar el arranque completo**: `pio device monitor -d firmware/camera-server -e esp32cam --port /dev/ttyUSB0 --baud 115200` y pulsar **RST** en la placa. Guardar el log desde el banner `ets ...` hasta el último mensaje. Con ese log se decide entre H1–H7; no seguir al paso 4 sin él.
4. **Compilar limpio** con el puerto explícito: `pio run -d firmware/camera-server -e esp32cam -t upload --upload-port /dev/ttyUSB0`. Anotar versión de plataforma/core que imprime `pio`.
5. Si el log muestra `Camera init failed`: anotar el código, reasentar la cinta de la OV2640, probar con alimentación de 5 V suficiente (cable de datos corto).
6. Si queda en puntos: probar con un hotspot propio de 2,4 GHz y credenciales sencillas.
7. Si aparece `WiFi connected` pero no la IP: revisar el log de `startCameraServer` (H6).
8. Con IP obtenida, comprobar `curl -I http://IP/`, `/capture` y `:81/stream`, y recién entonces pasar al detector.

### 7.4 Propuestas de cambio (pendientes de aprobación; ninguna aplicada)

Cambios mínimos al firmware, sin nuevas capas, que hacen el fallo visible en vez de silencioso:

- **P-A** Reimprimir periódicamente estado e IP desde `loop()` (cada ~5 s: `WiFi.status()`, `WiFi.localIP()`, RSSI). Resuelve H1 de raíz y sirve como latido para la demo.
- **P-B** Imprimir la IP **inmediatamente** tras `WL_CONNECTED`, antes de `startCameraServer()`.
- **P-C** En el fallo de cámara: terminar el mensaje con `\n` y, en lugar de `return`, reintentar o reiniciar (`ESP.restart()` tras unos segundos) manteniendo WiFi opcional para diagnóstico.
- **P-D** Límite de espera de WiFi (p. ej. 20 s) con impresión de `WiFi.status()` y reintento.
- **P-E** Fijar la versión de `platform` y, para Linux, definir el puerto por `--port` (o un entorno `[env:esp32cam_linux]`) en vez de editar `COM5`.
- Fuera de alcance de este bug: S3 (D12), MQTT, reconexión del stream.

### 7.5 Resultados de la depuración

Completar al ejecutar.

| Fecha | Ítem | Resultado |
| --- | --- | --- |
| 2026-11-08 | Análisis estático de `main.cpp`, `platformio.ini`, `camera_pins.h`, `secrets.h` | Hechos de §7.1; sin causa confirmada |
| 2026-11-08 | Log real del arranque | El propietario abre `pio device monitor` en `/dev/ttyUSB0` (115200) y pulsa RST: **no aparece ningún byte**, ni siquiera el banner `ets ...` de la ROM. H1 descartada |
| 2026-11-08 | Interpretación | Que falte hasta el banner de la ROM apunta **por debajo del firmware**: enlace serie, línea RTS/DTR reteniendo EN, alimentación o puerto equivocado. Es inferencia, aún sin probar |
| 2026-11-08 | Hallazgo en `platformio.ini` | No define `-DCORE_DEBUG_LEVEL`: en PlatformIO el nivel por defecto es 0, así que `log_i`/`log_e` de `app_httpd.cpp` **no imprimen nada** aunque el código llegue ahí |
| 2026-11-08 | **Causa raíz confirmada** | Señal WiFi débil en la ubicación original. Al mover el ESP a otro lugar con mejor señal, el stream transmite sin interrupciones y el monitor (con `--rts 0 --dtr 0`) muestra la IP. Informado por el propietario; sin cambios de código |

### 7.6 Guía de pruebas escalonadas (propuesta; las ejecuta el propietario)

Regla: cambiar **una cosa por vez**, compilar, cargar, anotar el resultado en §7.5. Comandos con `uv run pio ... --port /dev/ttyUSB0`.

**Etapa 0, enlace sin tocar código.** (a) `monitor --rts 0 --dtr 0`: en placas con circuito de autorreset, el monitor puede dejar EN retenido y el chip en reset. (b) `uv run pio pkg exec -p tool-esptoolpy -- esptool.py --port /dev/ttyUSB0 chip_id` (o `uv run pio run -t upload -v`, que muestra el chip detectado): confirma que el puerto, el cable y el chip responden. (c) Mirar si el LED rojo de la placa enciende. Si (b) falla, el problema es hardware/puerto y no el firmware.

**Etapa 1, latido.** Primera línea de `setup()`: `delay(1500); Serial.println("[BOOT] setup start");`. En `loop()`: `Serial.printf("[HB] %lu ms\n", millis()); delay(2000);`. Si el latido no aparece, ver Etapa 0. Si aparece, el enlace está bien y el problema está más adelante.

**Etapa 2, logs del core.** En `platformio.ini`, `build_flags`: añadir `-DCORE_DEBUG_LEVEL=3`. Sin esto no se ven `log_i`/`log_e` de `app_httpd.cpp` ni los del driver de cámara.

**Etapa 3, memoria.** Antes de `esp_camera_init`: `Serial.printf("[MEM] PSRAM=%s size=%u heap=%u\n", psramFound() ? "si" : "no", ESP.getPsramSize(), ESP.getFreeHeap());`. Si no hay PSRAM, el firmware cae a SVGA en DRAM (es válido, pero conviene saberlo).

**Etapa 4, aislar la cámara.** Rodear el bloque desde `camera_config_t config;` hasta el `setupLedFlash()` con `#if 0 ... #endif`. Si la IP aparece, WiFi y red están bien y el fallo es la cámara (pines, cinta, alimentación). Si no, es WiFi.

**Etapa 5, WiFi con diagnóstico.** Reemplazar el `while` por uno con límite que imprima `WiFi.status()` (6 = clave incorrecta, 1 = SSID no encontrado, 3 = conectado) y la IP **antes** de `startCameraServer()`.

**Etapa 6, servidor sin cámara.** Con la cámara aún desactivada, `startCameraServer()` levanta HTTP. Probar `curl -I http://IP/`. Comprueba red/firewall sin depender del sensor.

**Etapa 7, cámara, de menor a mayor exigencia.** Reactivar la cámara: primero `/capture` (un JPEG) y solo después `:81/stream`.

Qué se puede comentar sin romper nada: `setupLedFlash()` y el LED del stream, los handlers `/bmp`, `/xclk`, `/reg`, `/greg`, `/pll`, `/resolution`, y la página `/` (`index_handler`). Qué no tocar: los pines, `esp_camera_init`, `WiFi.begin`, `startCameraServer` y `stream_handler`.
