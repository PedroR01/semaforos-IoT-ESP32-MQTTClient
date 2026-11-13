## Retomar el proyecto sin el historial del chat

Punto de entrada para `project-mentor` y `coding-agent`. Corte de contexto: **2026-11-12, ~20:30** (actualizado tras el fail-safe), zona `America/Buenos_Aires`. Reemplaza al del 08/11. Lo que importa para continuar está aquí; el detalle largo está enlazado.

### Contexto mínimo

- **Producto:** detección y estado del tráfico con cámaras ESP32 y semaforización adaptativa. La documentación es para el propietario y para agentes.
- **Hito inmediato:** presentación **informal** del MVP el **viernes 13/11/2026**. Cadena a mostrar: ESP32-CAM → detector YOLO (PC) → MQTT → controlador → semáforo **simulado**. Prioridad: arquitectura y comunicación sólidas; todo lo inestable queda fuera.
- **Hardware de la demo:** ESP32-CAM-MB (OV2640, la que funciona), PC CachyOS con YOLO y Mosquitto. El ESP32-S3/OV5640 solo entra con pinout y alimentación validados (D12); NodeMCU disponible para pruebas MQTT. Sin LEDs.
- **Entorno:** Linux. Shell de login fish (no `source activate`; usar `.venv/bin/python` o `uv run`). Guía: [setup-linux.md](setup-linux.md). Dentro del sandbox de los agentes `.venv/bin/python` y a veces `paho` no funcionan: los agentes validan lógica pura con `python3 -m unittest discover -s <dir>` y el propietario ejecuta lo demás.

### Decisiones vigentes

D01–D07 en [reference.md](reference.md) §12. D08–D13 (08/11): percepción, decisión y actuación separadas y unidas solo por MQTT; el ESP solo captura y declara estado; semáforo simulado; política mínima acotada al MVP; S3 condicional; `docs/` reorganizada. Parámetros confirmados el 12/11 (reference §14): amarillo 2 s, todo-rojo 2 s, verde mínimo 5 s, máximo 20 s, T=5 s, ciclo base de respaldo 10 s de verde por acceso. Política en reposo: sin demanda se mantiene el verde actual (log "reposo"). Histéresis de modo: a ciclo fijo tras 10 s sin dato `ok`, vuelta a adaptativo tras 3 s continuos. El propietario eligió A+B+C+D para el fail-safe (§15).

### Qué existe y funciona (verificado por el propietario con hardware real el 11–12/11)

- **Firmware `camera-server`:** stream MJPEG `:81/stream` y `/capture`. Estable con buena señal WiFi (el fallo inicial era señal débil, no código).
- **Detector** (`vision/detector/cam_detection.py`, `traffic_mqtt.py`): publica cada ~1 s en `trafico/v1/<camera_id>/detections`, `unavailable` si no hay stream, reintento infinito con espera creciente, cierre limpio con Ctrl+C y Last Will. Corregido y verificado.
- **Fail-safe (§15):** latido, lease, watchdog local y Last Will en `control/`; 83 tests OK; sin verificar con hardware.
- **M2 en `control/`:** `traffic_logic.py` (lógica pura: política, vigencia, histéresis, validador de secuencia), `traffic_controller.py`, `traffic_light_sim.py`, `tests/` (54 tests). Verificado con Mosquitto local y con la cámara real: funciona en lo básico; **persiste ruido** al usar la cámara real (cortes de señal, detecciones fantasma, objetos de prueba), a retocar más adelante. Contrato en [protocol/mqtt/README.md](../protocol/mqtt/README.md).

### Qué no existe

Segundo acceso (M3), vista de demo (RF-12), `state` con Last Will del ESP (RF-07), modo local/selector, métricas de espera/cruce, comparación fijo vs adaptativo (RF-14).

### Problemas conocidos (no bloquean)

Ruido de la cámara real al dejar de ver vehículos; primera muestra tras un hueco no se suaviza (un conteo de 1 supera el umbral); si el semáforo arranca después del controlador hay un `RECHAZADO` inicial autocorregido (arrancar primero el semáforo); la vigencia compara `processed_at` con el reloj del controlador (válido en una sola PC).

### Por dónde continuar (en este orden; M3/M4 no se recortan por el fail-safe)

1. **Fail-safe A+B+C+D: implementado** (reference §15, 83 tests OK, integración local informada por el agente). Falta que el propietario ejecute las pruebas F1–F7 de [setup-linux.md](setup-linux.md) §4.
2. **M3 mínimo:** segundo acceso (S3 o, lo más realista, video grabado como fuente alternativa con otro `--camera-id`/`--approach-id`) y vista de demo mínima: video anotado con conteos y fase vigente (consola o ventana).
3. **M4:** ensayo completo cronometrado, **video grabado de respaldo**, conteo manual vs sistema sobre un clip de maqueta.
4. Antes de la presentación: modelo `yolov8n.pt` descargado (sin depender de internet), guion de contingencia, y decidir qué commitear (rama actual `dev`, M2 ya fusionado en PR #11; sin commit: fail-safe en `control/`, `protocol/mqtt/README.md`, docs y cambios en `.claude/` a confirmar).

Orden de recorte (MVP.md §10): RF-14, RF-12, segundo acceso en tiempo real (usar video), RF-07.

### Cómo se arranca el sistema (resumen; receta completa en [setup-linux.md](setup-linux.md) §4)

Orden: `mosquitto -v` → semáforo (`control/traffic_light_sim.py`) → controlador (`control/traffic_controller.py`) → detector (`vision/detector/cam_detection.py --url http://<IP>:81/stream --mqtt-host localhost --camera-id cam-01 --approach-id acceso-01 --show`). Observar con `mosquitto_sub -h localhost -t 'trafico/v1/#' -v`. Acceso-02 se simula con un bucle `mosquitto_pub` o con un segundo detector.

### Notas de trabajo

- No hacer commit, revertir ni limpiar cambios del usuario sin que sea parte de la tarea. `.agents/rules/coding-agent.md` figura borrado y existe un `coding-agent` en `.claude/`; parece una mudanza del propietario, confirmar antes de commitear.
- Los dotfiles (`.bashrc`, `.zshrc`, `.gitconfig`, `.mcp.json`, `.idea`, etc.) que lista `git status` son artefactos del entorno; no se versionan.
- No reactivar `firmware/sensor-controller/` por iniciativa propia. Las credenciales WiFi de los sketches de Arduino externos no se copian al repo.
- El propietario escribe en español y quiere explicaciones que le enseñen a razonar (rol mentor), con hechos separados de propuestas y de lo no verificado.
- Roles: el mentor analiza y revisa y deja briefs en `reference.md`; el `coding-agent` implementa un brief y reporta (archivos, decisiones, tests, qué no pudo verificar, riesgos).

### Lectura por necesidad

| Necesidad | Documento |
| --- | --- |
| Qué construir esta semana | [MVP.md](MVP.md) |
| Instalar, correr y registro de pruebas | [setup-linux.md](setup-linux.md) |
| Hardware, métricas, decisiones D01–D13, briefs M2 (§14) y fail-safe (§15) | [reference.md](reference.md) |
| Topics y payloads | [../protocol/mqtt/README.md](../protocol/mqtt/README.md) |

Los README antiguos pueden describir comportamiento desactualizado. Si el código y la documentación difieren, registrar la discrepancia.

Instrucción sugerida para retomar:

> Usa project-mentor. Lee `docs/agent_session_context.md`, contrasta con `git status` y delega al coding-agent la implementación del brief de `docs/reference.md` §15. Revisa su reporte, itera las correcciones y documenta resultados en reference §15 y setup-linux.
