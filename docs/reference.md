# Sistema de detección y estado del tráfico con ESP

Última actualización: 21/10/2026; reorganizado el 08/11/2026. Referencia técnica larga de requisitos, arquitectura, hardware, métricas, problemas pendientes y validación. Los documentos de `docs/` se organizan según el [índice](README.md): el alcance del hito del 13/11 está en [MVP.md](MVP.md), la puesta en marcha en las guías por sistema operativo y el contrato MQTT en [protocol/mqtt](../protocol/mqtt/README.md).

**Estado:** la arquitectura y el contrato que se proponen a continuación todavía requieren implementación. El código actual transmite vídeo desde el ESP y ejecuta detección en Python; no integra MQTT en cámara/visión ni calcula todavía cola o flujo de tráfico.

## 1. Objetivo y prioridades acordadas

Desarrollar un sistema escalable que detecte presencia de vehículos, determine cuántos esperan y cuente pasos sin duplicados para describir el flujo por acceso/carril. Las pruebas incluyen vehículos de maqueta y tráfico real, que deben validarse por separado.

La ubicación del procesamiento será **configurable al compilar y cargar el firmware**, según el hardware y el modelo disponible:

- `external`: el ESP captura imágenes; una PC o centro de cómputo ejecuta detección, seguimiento y métricas, y publica el estado del tráfico por MQTT.
- `local`: un ESP compatible integra captura, inferencia, seguimiento/métricas y publicación MQTT. Los modelos y métricas soportados deben validarse para esa placa.

Los nombres son una propuesta de configuración; el selector todavía no existe en el código. El requisito de poder elegir el lugar de procesamiento sí está acordado. La prioridad actual es desarrollar funcionalidades y esa arquitectura; optimizar CPU/GPU, elegir compras o aumentar FPS no son condiciones previas para comenzar.

El desarrollo del simulador `firmware/sensor-controller` está pausado. Conservamos sus configuraciones de hardware y experiencia MQTT como referencia. No es necesario corregir su máquina de estados, compilarlo o eliminarlo de CI para avanzar con cámara/visión.

El primer hito es **captura → detección → MQTT**. El siguiente incluye cantidades esperando y flujo con seguimiento y reglas de conteo. Mostrar cajas o transportar un snapshot de clases no completa por sí solo ese segundo hito. La política que asigna prioridad y la actuación física del semáforo necesitan una especificación propia.

## 2. Inventario y configuraciones de hardware

### Dispositivos físicos informados

| Cantidad | Equipo                              | Papel y validaciones pendientes                                                                            |
| -------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| 1        | ESP-32S, OV2640 y base ESP32-CAM-MB | Captura/transmisión; confirmar pinout y PSRAM detectada antes de equipararlo al perfil `esp32cam`          |
| 1        | ESP32-S3-N16R8 y OV5640             | Captura y candidato para procesamiento local; falta identificar placa portadora, pinout y memoria efectiva |
| 1        | ESP32 NodeMCU                       | Referencia y pruebas MQTT; no se informó una cámara conectada                                              |

Inventario informado por el propietario; no equivale a validación física del agente. En la variante ESP32-S3-WROOM-1-N16R8, Espressif documenta 16 MB de flash y 8 MB de PSRAM. Flash almacena firmware/modelos y RAM aloja datos y tensores: no son intercambiables ni indican por sí solas velocidad de inferencia. N16R8 no define los GPIO de la cámara. [Hoja de datos oficial](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf).

Por placa se debe registrar modelo, cámara, pines, flash/PSRAM, alimentación, adaptador USB/serie, procedimiento de carga/reset y entorno de compilación. No trasladar automáticamente los pines del circuito ultrasónico a una cámara.

### Computadoras disponibles

| Equipo               | Configuración informada                                                     | Uso posible                                                                |
| -------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| PC                   | Intel i5-9600K, 16 GB RAM, NVIDIA RTX 2060 con 6 GB GDDR6 y bus de 192 bits | Procesamiento externo, desarrollo y pruebas                                |
| Notebook HP Pavilion | Ryzen 7 5700U, 8 GB RAM y Radeon integrada con 496 MB gráficos reportados   | Desarrollo y pruebas portátiles; capacidad y aceleración se validan aparte |

En el entorno virtual revisado se observó `torch 2.14.0+cpu`, `torch.version.cuda = None` y CUDA no disponible para PyTorch. Eso describe la instalación, no ausencia de GPU física. Aprovechar CUDA en la PC queda como mejora posterior; CPU sigue siendo una ruta válida para desarrollar y comprobar funcionalidades sin prometer rendimiento.

### Perfiles de cámara declarados en el repositorio

| Entorno actual | Configuración declarada                                                                                                 |
| -------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `esp32cam`     | `board = esp32cam`, `CAMERA_MODEL_AI_THINKER`; COM5 como ejemplo local                                                  |
| `esp32s3`      | `board = esp32-s3-devkitc-1`, `CAMERA_MODEL_ESP32S3_EYE`, memoria `qio_opi`, `BOARD_HAS_PSRAM`; COM6 como ejemplo local |

El perfil S3 no demuestra que la placa N16R8 del usuario sea una S3-EYE. Contrastar los pines reales antes de cargar. `partitions.csv` termina en 4 MiB y no se declara explícitamente flash de 16 MB en `platformio.ini`: revisar esa distribución al incorporar modelos. Una tabla de 4 MiB puede bastar para vídeo y no prueba un fallo de compilación.

El servidor configura inicialmente JPEG a QVGA. La OV5640 no está necesariamente transmitiendo a su resolución máxima. El driver admite OV2640 y OV5640 y documenta el costo de RGB/YUV, PSRAM, WiFi y múltiples buffers: la captura y la inferencia simultáneas necesitan una prueba conjunta. [Driver oficial de cámara](https://github.com/espressif/esp32-camera#readme).

### Circuito histórico de sensores

`diagram.json` contiene ESP32 DevKit, HC-SR04, tres LEDs discretos y TM1637. `src/main.cpp` construye `Sensor(16, 17, 18, 5, 14, 0, 4)`. Las operaciones del display están comentadas; la bitácora registra su ausencia en pruebas físicas. El README histórico menciona PIR y LEDs RGB que no corresponden al diagrama actual. Este circuito es referencia del desarrollo pausado, no el cableado de las cámaras.

## 3. Estado actual comprobado en el repositorio

| Componente                                                  | Qué existe                                                                             | Qué falta para el objetivo                                                                       |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [camera-server](../firmware/camera-server/)                 | Credenciales por perfil, inicialización de cámara, web, captura y MJPEG                | Selector externo/local, backend de inferencia local y cliente MQTT                               |
| [detect_esp32cam.py](../vision/detector/detect_esp32cam.py) | Una URL, YOLO, filtro de cinco clases, anotaciones y vídeo opcional                    | Datos estructurados comunes, seguimiento/métricas funcionales y MQTT                             |
| [cam_detection.py](../vision/detector/cam_detection.py)     | IDs de tracking, conteos y snapshots JSON/JSONL                                        | Corregir semántica de conteos, zonas, espera, cruces y MQTT; estaba sin versionar en la revisión |
| [pyproject.toml](../vision/detector/pyproject.toml)         | Python `>=3.11,<3.14`, NumPy, OpenCV y Ultralytics                                     | Empaquetado explícito de ambos módulos y dependencias de MQTT/seguimiento verificadas            |
| [MQTT legado](../protocol/mqtt/README.md)                   | Diagnóstico y `Detener` en `sensor-controller`                                         | Contrato para tráfico, identidades y recuperación compartido por ambos modos                     |
| CI                                                          | Compila los tres entornos de firmware y verifica sintaxis/ayuda del detector principal | Pruebas funcionales de contratos, métricas y modos; instalación/ayuda de ambos scripts           |

Los proyectos PlatformIO son independientes. No existe un backend MVC, base de datos ni persistencia central implementada. Docker no es requisito; `.devcontainer/` no existe aunque `CONTRIBUTING.md` todavía lo describe. Las dependencias no están completamente fijadas, por lo que la reproducibilidad debe registrarse al validar versiones.

## 4. Arquitectura objetivo con dos modos de procesamiento

### Responsabilidades compartidas

Separar captura, proveedor de detecciones, seguimiento, métricas, configuración e intercambio MQTT. La separación responde a la necesidad concreta de dos ubicaciones de procesamiento; no requiere crear servicios genéricos o capas adicionales para cada operación.

```mermaid
flowchart LR
    C[ESP: captura de cámara] --> M{Modo compilado}
    M -->|external| E[PC o centro: detección y seguimiento]
    M -->|local y compatible| L[ESP: modelo y seguimiento]
    E --> T[Estado de tráfico: zonas, espera y cruces]
    L --> T
    T --> Q[MQTT: mismo contrato y métricas]
    Q --> R[Consumidores o gestor de prioridad]
```

Es un diagrama de responsabilidades lógicas: en `local`, seguimiento y métricas también residen en el ESP; en `external`, residen en el centro. Compartir contrato y casos de prueba no significa ejecutar Python/PyTorch dentro del microcontrolador ni copiar sin adaptación todo el algoritmo entre runtimes.

| Aspecto                              | `external`                                                                | `local`                                                                     |
| ------------------------------------ | ------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Captura                              | ESP                                                                       | ESP                                                                         |
| Transporte de imagen para inferencia | HTTP/MJPEG hacia el centro                                                | No requiere enviar imágenes para procesarlas; vista de diagnóstico opcional |
| Detección, seguimiento y métricas    | PC o centro de cómputo                                                    | ESP, con implementación y modelo compatibles                                |
| Publicación del estado de tráfico    | Proceso externo identificado por cámara                                   | ESP identificado por cámara                                                 |
| Estado del dispositivo               | ESP por MQTT, al implementarlo                                            | ESP por MQTT                                                                |
| Si falla el procesador               | Declarar resultados no disponibles y conservar captura cuando sea posible | Declarar error local; no publicar conteos inventados                        |

El broker continúa siendo un servicio MQTT de la red; integrar funciones en el ESP no implica ejecutar Mosquitto en él. USB programa y permite consultar el monitor serie; el vídeo actual se transmite por WiFi.

### Selección al compilar y cargar

Propuesta de parámetro lógico: `processing_mode = external | local`, separado del perfil físico de placa/cámara. Su representación definitiva en PlatformIO, macros o configuración generada se define al implementar; no es una opción disponible hoy.

Podrían existir perfiles como `esp32cam-external`, `esp32s3-external` y `esp32s3-local`, reutilizando configuración física. Son nombres propuestos, **no entornos ejecutables actuales**. Seleccionar un perfil determinará qué backend se incluye en el firmware antes de la carga.

La configuración debe cubrir identidad del dispositivo/cámara, perfil físico, modo, modelo/backend y capacidades, red, broker y parámetros de métricas. Un nodo local debe declarar qué métricas soporta realmente: detectar presencia no equivale a implementar espera y flujo.

- Una combinación no soportada debe rechazarse en la validación previa a la carga cuando pueda detectarse allí, con diagnóstico del chip/modelo/memoria o función faltante.
- No cambiar silenciosamente de `local` a `external` ni publicar ceros para funciones no implementadas.
- Los nodos de ambos modos deben poder coexistir y publicar resultados identificables con las mismas definiciones funcionales.
- Un cambio de modo o reinicio debe delimitar sesiones y evitar dos publicadores activos contando el mismo origen sin coordinación.
- La recepción del estado de fase y el retorno de resultados al ESP se especifican por separado. No son sinónimos de cambiar el lugar de inferencia.

### Procesamiento externo escalable

Los scripts actuales aceptan una sola URL y crean un objeto YOLO por ejecución. Se puede evolucionar hacia un servicio con captura independiente por fuente, modelo compartido, colas acotadas y estado/trackers separados por cámara. No alternar cámaras en el `model.track(..., persist=True)` actual sin separar contextos. Una cámara caída no debe bloquear a las demás.

Ultralytics admite varias fuentes y lotes, incluidas listas `.streams`; los scripts actuales no adquieren ese soporte simplemente recibiendo ese archivo. Un modelo compartido evita duplicación, pero el trabajo sigue creciendo con las imágenes procesadas. La demanda aproximada es `N × f` imágenes por segundo para `N` cámaras y `f` inferencias por cámara. Es un presupuesto, no un benchmark. [Inferencia con varias fuentes](https://docs.ultralytics.com/modes/predict/).

Separar frecuencia de captura, inferencia y publicación MQTT. Reducir frecuencia o resolución exige comprobar que no se pierdan cruces o vehículos pequeños. `classes=[...]` filtra categorías y `max_det` limita resultados; no convierten una red general en un modelo pequeño específico de vehículos. Estos son criterios posteriores de capacidad, no el foco del incremento actual.

### Procesamiento local y compatibilidad

El S3 es candidato para una prueba de modelo pequeño especializado, no una garantía de que el pipeline completo ya quepa o alcance precisión. ESP-DL distingue el ESP32 clásico sin instrucciones PIE del S3 con PIE V1. [Operadores y plataformas](https://github.com/espressif/esp-dl/blob/master/operator_support_state.md).

ESP-Detection ofrece modelos ESPDet-Pico y entrenamiento para objetivos específicos. Publica más de 7 FPS a 224 × 224 para un ejemplo en S3; ese resultado no demuestra cinco clases de vehículos, seguimiento, cámara y MQTT simultáneos. Su flujo documentado usa ESP-IDF para despliegue, por lo que no se debe asumir integración directa sin cambios al firmware Arduino actual. [ESP-Detection](https://github.com/espressif/esp-detection#readme).

ESP-DL usa modelos `.espdl` y herramientas de cuantización. Se requieren datos representativos, entrenamiento/ajuste o modelo adecuado, exportación, operadores compatibles y validación de memoria/precisión. Entrenar fuera del ESP no significa necesitar ese centro para cada inferencia posterior. El archivo `.pt` y los scripts Python actuales no se ejecutan directamente en el ESP. [ESP-DL](https://github.com/espressif/esp-dl#readme).

Como contraste de límites, los benchmarks de YOLO26n en ESP-DL muestran configuraciones S3 con 16 MB de PSRAM y latencias del orden de segundos a 512/640 píxeles. No equivalen al R8 ni al YOLOv8n actual. Probar un modelo pequeño especializado y el pipeline completo; no prometer rendimiento por la etiqueta «compatible con YOLO». [Benchmarks YOLO26](https://github.com/espressif/esp-dl/blob/master/models/yolo26/README.md).

Un solo S3 no se considera por defecto procesador de las cámaras de otros ESP. Las reglas simples de diferencias de imagen/ocupación pueden investigarse en escenas controladas, pero sombras, vibración e iluminación alteran resultados; un vehículo detenido también debe detectarse. La activación por movimiento necesita revisión periódica para no olvidar vehículos inmóviles.

## 5. Definición de las métricas de tráfico

| Métrica propuesta | Qué significa                                  | Implementación necesaria                                       |
| ----------------- | ---------------------------------------------- | -------------------------------------------------------------- |
| `visible_count`   | Vehículos observados ahora en un acceso/carril | Región de interés, objetos válidos y eliminación de duplicados |
| `waiting_count`   | Vehículos observados que esperan               | Zona de espera y condición temporal de detención/avance lento  |
| `crossings_count` | Pasos válidos durante un intervalo             | Línea/zona, trayectoria, dirección y deduplicación de eventos  |
| `flow_rate`       | Intensidad de circulación                      | Cruces divididos por una ventana explícita, con unidades       |

No sumar snapshots de cola: un vehículo detenido durante cien imágenes representa una unidad esperando en cada instante. Si cruzan 12 vehículos en 30 segundos, el volumen observado es 12 y la tasa equivalente es 24 vehículos/minuto; no implica 24 cruces ya observados.

### Zonas, espera y cobertura

Cada cámara necesita asociarse a accesos/carriles, regiones de espera y líneas de cruce con dirección. Una cámara puede cubrir varias zonas o varias cámaras pueden observar regiones distintas; depende de la instalación. Propuesta a validar: usar un punto de referencia como la parte inferior central de la caja y tolerancias frente al ruido de detección. [Conteo por regiones](https://docs.ultralytics.com/guides/region-counting/) y [conteo por línea/zona](https://docs.ultralytics.com/guides/object-counting/).

Para espera falta acordar zona, duración mínima, umbral de movimiento, tratamiento de avance lento/detenciones transitorias y persistencia estimada ante oclusiones breves. Los píxeles dependen de perspectiva, resolución y frecuencia; no equivalen a velocidad física sin calibración. Distinguir observación reciente de estado estimado.

Si la cola continúa fuera del encuadre o hay vehículos ocultos, el conteo visible no demuestra la longitud completa de la cola. Documentar cobertura y calidad de observación. Ausencia de detecciones y ausencia física no son equivalentes garantizados.

### Unicidad y sesiones

Propuesta pendiente de confirmar: un conteo por paso válido en un acceso/carril y una sesión. Para cantidad presente, mantener una representación por trayectoria activa, sin acumular cada detección. Un `track_id` es una identidad temporal estimada y puede cambiar tras oclusiones o reconexiones; no garantiza identidad física permanente. [Seguimiento de Ultralytics](https://docs.ultralytics.com/modes/track/).

Definir dirección y tolerancia al cruce, si un vehículo que regresa produce otro evento, tratamiento de reinicios/sesiones y continuidad de agregados. Si las vistas se solapan, sumarlas puede duplicar vehículos sin asociación entre cámaras. También se debe acordar tolerancia a omisiones y duplicados: deduplicación de mensajes no demuestra conteo físico perfecto.

Los resultados necesitan identificar dispositivo/cámara, acceso/carril, sesión, secuencia y tiempo/ventana. Cada evento de cruce requiere identidad propia para no sumarlo dos veces por una entrega MQTT repetida. Mantener seguimiento y estado por cámara y zona.

### Prioridad y fase efectiva

La salida inicial es telemetría de espera, cruces, tiempos y salud. La política de prioridad todavía no define equidad, espera máxima ni cambios de fase. Una ponderación futura distinta para colectivos o bicicletas es una regla de gestión, no una modificación del conteo físico.

Para etiquetar el flujo como «durante el verde» hace falta conocer la fase efectiva desde una fuente autoritativa, aún no definida. Mientras falte, medir por tiempo y publicar fase desconocida, sin deducirla solo del movimiento.

### Diferencia respecto de los scripts

El detector simple carece de seguimiento, zonas y métricas de espera/cruce. En `cam_detection.py`, `current` cuenta tracks del frame y no representa espera. `unique_total` registra primeras apariciones y puede recontar un ID eliminado por TTL. `unique_window` se basa en primeras apariciones, no en todas las presencias ni en salidas. Estas métricas no deben publicarse como unicidad física o flujo sin corregirlas/definirlas.

Ambos scripts fijan `max_det=30` e `imgsz=320`; revisar truncamiento en escenas densas y calidad con vehículos lejanos, considerando además la captura inicial QVGA. El seguimiento solo añade a `current` cajas con ID: decidir cómo tratar detecciones aún sin ID. Mantener el script simple como diagnóstico es compatible con desarrollar un pipeline funcional común.

## 6. Comunicación MQTT y contrato común

No existe publicación MQTT en cámara/visión. El legado de sensores usa un único tópico `semaforo/esp32`, diagnóstico y la orden `Detener`, sin autenticación/TLS ni contrato estable. No reutilizar esa orden como resultado de visión.

Propuesta de tópicos por origen, todavía no implementada:

| Tópico de ejemplo              | Publicador                                 | Función                                     |
| ------------------------------ | ------------------------------------------ | ------------------------------------------- |
| `trafico/v1/cam-01/detections` | Procesador externo o ESP local, según modo | Snapshot de observaciones y métricas        |
| `trafico/v1/cam-01/state`      | ESP                                        | Salud, modo, capacidades y estado de cámara |

Separar eventos de cruce, órdenes y estado efectivo cuando se definan sus contratos. No mezclar diagnóstico con comandos ni crear un canal de actuación sin requerimiento. El consumidor debe identificar origen y no depender de que el procesamiento sea Python o C++.

Ejemplo ilustrativo de snapshot; **no es una API aprobada ni la salida actual**:

```json
{
  "v": 1,
  "device_id": "cam-01",
  "camera_id": "cam-01",
  "approach_id": "acceso-01",
  "processing_mode": "external",
  "producer_id": "vision-cam-01",
  "session_id": "sesion-ejemplo-01",
  "seq": 1,
  "processed_at": "2026-10-21T12:00:00Z",
  "status": "ok",
  "metrics": {
    "visible_count": 4,
    "waiting_count": 3,
    "crossings_count": 12,
    "window_s": 30,
    "flow_rate_vehicles_per_minute": 24
  }
}
```

Puede agregarse desglose por clase y carril con las definiciones acordadas. `processed_at` es procesamiento, no captura. Si el reloj del nodo local no está sincronizado, definir explícitamente la base temporal; no inventar una hora UTC. `session_id` distingue ejecuciones y `seq` ordena snapshots dentro de ellas.

Propuesta inicial: un snapshot por segundo, QoS 0 y detecciones sin retención; frecuencia, vigencia y política final quedan por confirmar. No reproducir una acumulación de datos antiguos como tráfico actual al recuperar conexión. Un frame válido vacío produce ceros; stream caído, inferencia fallida o métrica no soportada producen estado no disponible, no cero. El receptor valida identidad, versión, duplicados y vigencia.

### Configuración y ciclo de conexión

El ESP necesita host/IP LAN alcanzable del broker; `localhost` en él no identifica la PC. Python puede usar `127.0.0.1` si broker y proceso están en la misma computadora y el listener lo admite. IP de cámara y dirección del broker son distintas.

Cada placa y cada proceso MQTT requieren identificadores de cliente distintos y asociación estable entre identidad de cámara y URL. La IP puede cambiar sin cambiar el origen lógico. Configurar puerto, tópicos y credenciales según el broker, evitando secretos reales en Git.

El antiguo `Broker` sirve como referencia pero contiene ID/tópico fijos, ignora `MQTT_TOPIC`, publica mensajes de prueba y pausa un segundo por ciclo. Además, tras timeout inicial de WiFi puede intentar reconectar sin haber inicializado MQTT. No trasladar esos comportamientos al nuevo firmware.

Inicializar el cliente aunque WiFi aún no esté disponible y reconectar sin esperas largas que paralicen captura/inferencia. El `loop()` actual de cámara duerme 10 segundos: no es un ritmo apropiado para atender el futuro cliente MQTT. La caída del broker no debe impedir capturar ni declarar correctamente la ausencia de resultados.

Agregar la dependencia del cliente Python en `pyproject.toml` y la del firmware donde corresponda. Actualizar ejemplos y generación de configuración en [CI de firmware](../.github/workflows/platformio.yml) al añadir parámetros.

## 7. Problemas fundamentales pendientes

| Área                      | Acción necesaria                                                                 | Evidencia de cierre                                                               |
| ------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Hardware                  | Contrastar placa/pines/memorias con perfiles y particiones                       | Arranque, captura y carga física registrados por placa                            |
| Selector de procesamiento | Implementar elección de modo al compilar, backend y validación de compatibilidad | Perfiles válidos funcionan; combinaciones no soportadas fallan de forma explícita |
| WiFi/HTTP                 | Configurar perfil `LOCAL`, diagnosticar fallos y comprobar servicios reales      | Página, captura y stream alcanzables desde la red                                 |
| Instalación Python        | Declarar los dos módulos o crear un paquete explícito                            | Instalación desde entorno limpio y ayuda/inferencia de ambos scripts              |
| MQTT                      | Implementar publicación/estado y configuración en los extremos correspondientes  | Suscriptor independiente recibe datos reales identificados                        |
| Métricas                  | Seguimiento, zonas, espera, cruce y deduplicación                                | Comparación con referencia manual en maqueta y tráfico real                       |
| Backend local             | Modelo/runtime y pipeline completo compatibles por chip                          | Memoria, resultados, recuperación y capacidades comprobados en el ESP             |
| Robustez                  | Tratar pérdidas de frames, WiFi, broker, excepciones y cierre                    | Fallos producen estados explícitos y recuperación comprobada                      |

### Instalación y modelos

En el árbol con ambos scripts, una instalación editable produjo `Multiple top-level modules discovered in a flat-layout: ['cam_detection', 'detect_esp32cam']`. No basta con ejecutar scripts en un entorno ya preparado: resolver el empaquetado y verificar instalación limpia.

Revisar dependencias efectivas de seguimiento: la versión local de Ultralytics usa `lap` para asociar tracks, sin declaración directa en este proyecto. No depender de descargas/instalaciones accidentales en ejecución. Un modelo propio tampoco garantiza el mapa de clases COCO usado para bicicletas, autos, motos, colectivos y camiones.

`yolov8n.pt` puede descargarse al cargarlo si no existe. Para operar sin conexión, disponer previamente del modelo. No versionar modelos descargados, vídeos, entornos ni credenciales.

### Recuperación y observabilidad

La cámara espera WiFi indefinidamente al iniciar y retorna de `setup()` si falla `esp_camera_init`. Diferenciar esos estados de los fallos MQTT. El texto `Camera Ready` no comprueba que todos los servicios HTTP se hayan iniciado: realizar una consulta real.

Los dos detectores reinician el contador de reconexiones cuando la captura abre, aunque nunca entregue frames; se reprodujo que ese caso supera el límite indicado. La apertura inicial fallida tampoco tiene política equivalente de reintento ni código de salida explícito de error. Definir timeouts donde el backend los admita y cerrar captura, vídeo, JSONL y MQTT también ante excepciones o `Ctrl+C`.

`CAP_PROP_BUFFERSIZE = 1` no demuestra que siempre se procese el frame más reciente. Probar imagen nula, captura abierta sin frames, reinicio de cámara y pérdida de red. Distinguir retardo de captura, procesamiento y publicación; no prometer tiempo real con una latencia no medida.

## 8. Puesta en marcha

La puesta en marcha depende del sistema operativo y vive en guías aparte:

- Linux (CachyOS/Arch): [setup-linux.md](setup-linux.md)
- Windows (PowerShell): [setup-windows.md](setup-windows.md)

Las limitaciones de ese recorrido (empaquetado Python, ausencia de MQTT en cámara/visión, selector de modo no implementado) siguen descritas en las secciones 3 y 7.

## 9. Pruebas de aceptación y límites de la revisión

| Prueba                               | Evidencia esperada                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------------- |
| Instalación limpia                   | Ambos scripts disponibles e inferencia sin dependencias accidentales                    |
| Configuración por modo               | Modo y capacidades identificables; combinación inválida rechazada explícitamente        |
| Placa física                         | Entorno, COM, memoria y pines registrados; cámara inicia sin error                      |
| Recorrido externo                    | Imagen desde ESP, detección y estado MQTT con origen correcto                           |
| Recorrido local compatible           | ESP captura, procesa, calcula métricas declaradas y publica, sin PC para inferencia     |
| Compatibilidad de contrato           | Ambos modos usan las mismas definiciones; no exigir cajas idénticas a modelos distintos |
| Vehículo detenido muchos frames      | Una unidad presente/esperando y ningún cruce antes de atravesar la línea                |
| Cola que avanza y oclusiones         | Evolución validada contra referencia manual; observación y estimación distinguibles     |
| Cruce y oscilaciones junto a línea   | Un evento según dirección/regla; medir omisiones y duplicados                           |
| Saturación o vehículos lejanos       | Verificar resolución y truncamiento por límite de detecciones                           |
| Sin vehículos / sin imágenes         | Cero para frame válido vacío; estado no disponible para caída de observación            |
| Reinicios y entregas repetidas       | Sesión y deduplicación consistentes con la política acordada                            |
| Varias cámaras / vistas superpuestas | Seguimiento aislado, orígenes separados y regla explícita de doble observación          |
| Pérdida de cámara o broker           | Diagnóstico, aislamiento y recuperación; sin reproducir datos antiguos como actuales    |

Preparar vídeos de maqueta y tráfico real con referencia manual y evaluar por separado. Reconocer vehículos reales no demuestra reconocer juguetes, ni viceversa. Ajustar o entrenar cuando los errores medidos lo justifiquen. Comparar precisión, duplicados, omisiones, latencia y memoria del pipeline completo, no solo FPS del modelo.

CI debe comprobar builds afectados y contratos/lógica que no necesitan hardware, sin exigir GPU para importar módulos o ejecutar ayuda. No existe todavía una suite funcional que demuestre estas capacidades. Elegir pruebas relevantes del modo, esquema, identidad, conteo y recuperación en vez de reflejar detalles internos.

La revisión anterior verificó sintaxis/configuraciones y ambos comandos de ayuda; reprodujo empaquetado ambiguo, reconteo por TTL y reconexión sin frames. Las compilaciones intentadas quedaron bloqueadas por permisos de la sesión sobre la carpeta global de PlatformIO. No se verificaron cámaras, streams físicos ni la integración propuesta. Esa restricción no demuestra fallo del firmware.

## 10. Información de rendimiento conservada como referencia

Esta información no establece la prioridad de trabajo actual. La capacidad se medirá al validar funcionalidades, sin fijar una cantidad de cámaras por los 6 GB de VRAM ni una frecuencia suficiente para toda escena.

La RTX 2060 está listada por NVIDIA con capacidad CUDA 7.5. Si se decide aprovecharla, elegir driver y distribución PyTorch con soporte para esa arquitectura mediante el selector oficial y validar una inferencia real; la ruta NVIDIA no se traslada a la Radeon de la notebook. [GPU CUDA](https://developer.nvidia.com/cuda/gpus) y [PyTorch](https://pytorch.org/get-started/locally/).

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA no disponible')"
```

Es diagnóstico del entorno, no benchmark. Modelos, lotes y resolución deben medirse con red/decodificación/tracking y frames recientes; lotes pequeños no siempre serán superiores al procesamiento alternado. Los scripts no tienen aún `--device`.

Si luego las alternativas disponibles no cumplen, comparar otros nodos o concentradores. Raspberry Pi 5 con AI HAT+ es una opción de inferencia local que requiere modelo/pipeline compatibles y mediciones; no hay evidencia actual que obligue a comprarla. [Referencia de Raspberry Pi](https://www.raspberrypi.com/documentation/accessories/ai-hat-plus.html).

### Rendimiento de captura e inferencia en ESP: investigación (2026-11-12T21:00:00-03:00)

Creado y última modificación: 2026-11-12T21:00:00-03:00. Fuentes: notas del propietario ("Estudios ESP32", Obsidian), FAQ y repositorios de Espressif y reportes de la comunidad. **Nada aplicado ni medido aún.**

- **Cuello de botella sin medir.** El FPS de `--show` es el del bucle del detector (mínimo entre ESP, WiFi y YOLO en CPU). Antes de tocar firmware, medir por separado: log `MJPG ... AVG fps` del firmware (`app_httpd.cpp:297`, nivel INFO), `ffmpeg -i http://IP:81/stream -t 20 -f null -` (ESP + red sin YOLO), `--show` sobre el stream y sobre un archivo local (solo PC).
- **ESP32-CAM (ESP32 + OV2640).** PCLK máximo del ESP32 clásico: 8 MHz (FAQ de Espressif); el S3 llega a 40 MHz por su interfaz LCD_CAM. En JPEG QVGA el volumen por cuadro es pequeño, así que PCLK no debería limitar (inferencia, sin medir). Ajustes candidatos: XCLK 20→24 MHz, `jpeg_quality` 10→12–15, más luz o menos exposición. Ya aplicados: `fb_count=2` con `CAMERA_GRAB_LATEST` (el driver documenta que dos buffers duplican la tasa en JPEG) y `WiFi.setSleep(false)`. Referencia de la comunidad: ~20–25 FPS en QVGA por WiFi.
- **Alimentación y calor (de las notas del propietario).** USB 2.0 entrega 500 mA; con cable fino o largo la caída al transmitir por WiFi reinicia el ESP. La OV5640 con XCLK alto se calienta (disipador si transmite continuamente). Afecta estabilidad más que FPS.
- **Descartado para el stream:** escala de grises (el JPEG ya viene del sensor y YOLO está entrenado en color), `bitbank2/jpegdec` y `CONFIG_CAMERA_PSRAM_DMA` (sirven a decodificación o RGB en el propio ESP, es decir al modo local).
- **ESP32-S3 + OV5640.** Espressif lista 25 FPS de captura JPEG; sigue bloqueado por pinout y alimentación (D12).
- **Modo local en S3.** El componente `coco_detect` 0.4.1 de ESP-DL (COCO incluye `car`, `truck`, `bus`, `motorcycle`; no requiere entrenar) informa YOLO11n 320×320 en ~1,3 s por cuadro (solo modelo; +~65–100 ms pre/post) y 640×640 en ~5,6 s, frente a 6–26 s en versiones previas. Es coherente con la nota de ESP-DL de 2026-06 ("más de 3× en S3"), pero no se cruzaron fechas y versiones. Con ~0,7 cuadros/s alcanza para presencia y cola (`visible_count`), no para seguimiento y cruces. Requisitos: modelo en FLASH (`param_copy=false`) porque YOLO11n ocupa ~6 MB de gestor y ~3 MB de parámetros; `partitions.csv` actual de 4 MiB no alcanza. `espdet_pico` (esp-detection) da >7 FPS a 224×224 pero requiere entrenar. Trabajo post-MVP.
- **Skill `esp32s3-pie-simd`.** Es la referencia de instrucciones SIMD que Espressif usó para optimizar los operadores de ESP-DL; el beneficio se obtiene actualizando ESP-DL, no escribiendo ensamblador. Útil solo para kernels propios del modo local. No aporta al stream ni al MVP.
- **PC.** torch sin CUDA (§2). Alternativas post-MVP: CUDA en la RTX 2060, o leer el stream en un hilo aparte con el último cuadro (a mano o con `model.track(source=url, stream=True)` de Ultralytics, que lee en otro hilo) para eliminar la latencia acumulada.

## 11. Orden funcional de desarrollo

Todos los incrementos siguientes están **pendientes**. Son un orden propuesto de desarrollo, no funcionalidades entregadas ni una autorización general para implementar. El estudio acotado de viabilidad local puede adelantarse si resuelve una decisión de arquitectura; no debe bloquear reparaciones o contratos independientes.

| ID                                       | Revisar y decidir                                                                                                            | Implementación posterior                                                                                                            | Condición de cierre                                                                                                           |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **I0 — siguiente sesión**                | Configuración de perfil físico/modo/capacidades y contrato mínimo. Separar requisito acordado de nombres/defaults propuestos | Aún es una tarea de planificación; delimitar I1 y sus verificaciones                                                                | Decisión registrada, dudas bloqueantes identificadas y primer incremento suficientemente acotado                              |
| **I1 — base y selección**                | Empaquetado de ambos scripts, representación de selección al compilar y matriz inicial de combinaciones admitidas            | Corregir instalación y agregar selección/configuración explícita manteniendo la ruta externa; rechazar `local` cuando falte soporte | Instalación limpia, builds/configuraciones pertinentes y diagnósticos de combinaciones inválidas; sin fingir inferencia local |
| **I2 — recorrido externo y MQTT**        | Identidad de cámara/productor, salida estructurada y cliente/protocolo definidos en P04                                      | Captura → detecciones → MQTT; estado de dispositivo y recuperación en los extremos que correspondan                                 | Suscriptor independiente recibe resultados reales del origen correcto; vacío y ausencia de observación se distinguen          |
| **I3 — métricas funcionales**            | Zonas, espera, cruces, sesiones y unicidad de P05/P06, con vídeos de referencia                                              | Seguimiento por cámara y métricas de cola/flujo, con eventos deduplicados                                                           | Validación manual/automática separada en maqueta y tráfico real; métricas no implementadas nunca se publican como cero        |
| **I4 — procesamiento local**             | Modelo, runtime, memoria y capacidades del ESP elegido según P01/P03                                                         | Captura, inferencia, estado temporal/métricas y MQTT dentro del ESP compatible                                                      | Evidencia física del pipeline completo y del contrato común; un subconjunto de métricas no se declara cumplimiento total      |
| **I5 — coexistencia y escala funcional** | Sesiones, publicador efectivo, aislamiento y vistas solapadas                                                                | Nodos externos/locales y varias fuentes sin mezclar identidades ni recontar por mensajes repetidos                                  | Fallos/reinicio, productor correcto, aislamiento y capacidades comprobados; sin exigir aún una cantidad arbitraria de cámaras |
| **I6 — gestión del paso**                | Fuente de fase y política de prioridad de P07                                                                                | Integrar fase efectiva y reglas de gestión/actuación únicamente al definirse ese alcance                                            | La salida de telemetría y el control tienen responsabilidades y criterios de aceptación separados                             |

I1 no requiere resolver toda la geometría o política de prioridad. I2 puede probarse con detecciones básicas antes de I3. I4 debe conservar el requisito local a la vista, sin forzar el mismo modelo o código Python que el externo. La evidencia de un modo no prueba el otro. Optimización y expansión de hardware se abordan cuando las funcionalidades y necesidades medidas lo justifiquen.

Para I1, los archivos previsibles son `vision/detector/pyproject.toml`, los módulos de configuración necesarios del firmware, `firmware/camera-server/platformio.ini` y su documentación/checks afectados. La lista es estimada: no prescribe todavía nombres de archivos, macros, nuevos entornos ni una migración de framework. Crear un brief ejecutable después de cerrar las decisiones que afecten ese alcance, no inventarlas como si fueran acuerdos previos.

Estos son incrementos propuestos, no permiso para implementar todos en una solicitud documental. No es necesario reactivar simulación, agregar OTA, crear una interfaz nueva ni introducir base de datos para los primeros hitos.

## 12. Decisiones todavía pendientes

### Registro de decisiones acordadas

| ID  | Decisión vigente del usuario                                                                             | Estado                                                                                            |
| --- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| D01 | Pausar el desarrollo del simulador y conservar hardware/MQTT como referencia                             | Acordada; no reabrir sin nueva necesidad explícita                                                |
| D02 | Centralizar toda la información de `docs/` en este único Markdown                                        | **Reemplazada el 08/11/2026** por la organización de la sección 13                                |
| D03 | Priorizar funcionalidades y arquitectura escalable antes de optimizar recursos de la PC                  | Acordada; CUDA y compras no bloquean la planificación funcional                                   |
| D04 | Seleccionar al compilar/cargar dónde se procesa: externo o local en un ESP compatible                    | Requisito acordado; selector/backend todavía no implementados                                     |
| D05 | Medir presencia, vehículos esperando y conteo de vehículos/pasos para describir flujo y futura prioridad | Requisito acordado; definiciones operativas y tolerancias por cerrar                              |
| D06 | Validar con maqueta y tráfico real                                                                       | Acordada; no extrapolar automáticamente resultados entre escenarios                               |
| D07 | Mantener planificación/revisión con Project Mentor y ejecución de tareas definidas con Coding Agent      | Configuraciones adaptadas; una tarea directa suficientemente definida también permite implementar |
| D08 | Separar percepción, decisión y actuación; unirlas solo por MQTT                                          | Acordada 08/11/2026 (alcance MVP; ver [MVP.md](MVP.md))                                           |
| D09 | En el MVP el ESP solo captura, transmite y declara estado; sin inferencia ni métricas                    | Acordada 08/11/2026                                                                               |
| D10 | Semáforo simulado por software en el MVP                                                                 | Acordada 08/11/2026                                                                               |
| D11 | Política mínima de prioridad acotada al MVP; excepción explícita al I6                                   | Acordada 08/11/2026; la política definitiva sigue pendiente (P07)                                 |
| D12 | El S3/OV5640 entra solo con pinout y alimentación validados; si no, el segundo acceso usa video o webcam | Acordada 08/11/2026                                                                               |
| D13 | Reorganizar `docs/` como índice + MVP + referencia + guías por sistema operativo                         | Acordada y aplicada 08/11/2026                                                                    |

No confundir con acuerdos los nombres de macros/perfiles, el modelo ESPDet-Pico, el uso obligatorio de ESP-IDF, los tópicos/JSON de ejemplo, QoS 0, publicación a 1 Hz, broker local o semántica exacta de unicidad. Son propuestas o referencias que deben evaluarse para el incremento. Tampoco se confirmó todavía que los resultados externos deban regresar al ESP ni quién suministrará la fase efectiva.

### Matriz de decisiones por resolver

| ID                                | Información o decisión necesaria                                                                                    | Qué condiciona                                            | Trabajo independiente que puede continuar                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **P01 — hardware físico**         | Portadora S3, pinout OV5640, memoria efectiva y carga/reset por dispositivo                                         | Validación/carga física del perfil y viabilidad local     | Empaquetado, contratos y pruebas de lógica sin hardware; no inventar pines                              |
| **P02 — selección y capacidades** | Representación de modo al compilar, default, validación de combinaciones y declaración de métricas soportadas       | Configuración de I1 y conexión con backends               | Inspeccionar perfiles y proponer el cambio mínimo; no presentar los perfiles de ejemplo como existentes |
| **P03 — backend local**           | Modelo/runtime, clases, conversión, memoria, captura y estado temporal que permite el chip                          | I4 y cumplimiento funcional local                         | Ruta externa y contrato común; soporte local declarado pendiente/rechazado explícitamente               |
| **P04 — interfaz y red MQTT**     | Contrato mínimo, identidad/eventos, broker/acceso, frecuencia/vigencia, base temporal y necesidad de retorno al ESP | Publicación/consumo interoperable y pruebas físicas de I2 | Parametrización y diseño del esquema; el broker final no obliga a fijar una IP en código                |
| **P05 — geometría y espera**      | Vistas/accesos/carriles, zonas, duración y umbral de espera, avance lento, cobertura/oclusiones                     | `waiting_count` y su validación en I3                     | Captura, detección, diagnóstico y parametrización; no afirmar longitud total de cola no visible         |
| **P06 — unicidad y flujo**        | Regla/dirección de cruce, retorno de un vehículo, sesiones/reinicio, agregados y solapamiento entre cámaras         | Eventos de flujo y deduplicación; significado de «único»  | Seguimiento por cámara y contrato identificado; no prometer identidad física global                     |
| **P07 — fase y prioridad**        | Fuente de fase efectiva, equidad/espera máxima y alcance de actuación                                               | Métricas condicionadas al verde y gestión de I6           | Presencia, espera y cruces por tiempo con fase desconocida; no inferir verde del movimiento             |
| **P08 — aceptación y escala**     | Latencia/calidad aceptables, escenarios anotados y cantidad objetivo al escalar                                     | Criterios finales y capacidad declarada                   | Pruebas de funcionalidad con las dos cámaras; no inventar objetivos de FPS o compras                    |

Resolver primero las filas que afecten el siguiente incremento. Las elecciones rutinarias pueden proponerse fundamentadas; pedir al usuario únicamente datos o decisiones que no puedan obtenerse del repositorio ni resolverse dentro del alcance autorizado. Registrar la elección y su motivo aquí una vez tomada.

## 13. Documentación y coordinación de agentes

Organización de `docs/` (decisión del propietario, 08/11/2026, que reemplaza a D02):

| Documento                                                              | Contenido                                                                                        |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [README.md](README.md)                                                 | Índice y estado actual                                                                           |
| [MVP.md](MVP.md)                                                       | Alcance, arquitectura, requerimientos y calendario del MVP del 13/11 (fuente de verdad del hito) |
| [reference.md](reference.md)                                           | Este archivo: referencia técnica larga, decisiones y orden funcional de desarrollo               |
| [setup-linux.md](setup-linux.md), [setup-windows.md](setup-windows.md) | Puesta en marcha por sistema operativo                                                           |
| [agent_session_context.md](agent_session_context.md)                   | Traspaso para retomar sin el historial del chat                                                  |

El contrato MQTT tiene una única fuente: [protocol/mqtt/README.md](../protocol/mqtt/README.md). Los estudios y el guion narrativo de la presentación quedan en el vault de Obsidian, con un puntero a `MVP.md`. No crear más `.md` en `docs/` sin instrucción explícita. Los README de componentes deben alinearse al cambiar sus interfaces.

Pendientes: alinear rutas y ambos scripts en el README del detector, describir perfiles de IDE realmente disponibles y agregar ejemplos efectivos en `config/examples/` cuando se implementen. La documentación histórica del simulador no requiere rediseño.

El Project Mentor analiza y revisa; el Coding Agent implementa una tarea definida. Cuando se solicite un brief o reporte, registrarlo como sección identificada y fechada en este archivo (`reference.md`), con creación/última modificación en ISO 8601 y zona horaria. El chat puede enlazar y resumir el resultado.

Un brief debe indicar objetivo, alcance, archivos confirmados/estimados, verificaciones, fuera de alcance y decisiones bloqueantes reales. No generar un brief ejecutable si falta decidir algo que impide implementarlo; avanzar con lo independiente y señalar la duda concreta. La separación de roles no obliga a crear subagentes ni a pedir aprobación redundante para trabajo ya autorizado.

## 14. M2-ImplementationBrief — Controlador y semáforo simulado

Creado: 2026-11-12T00:00:00-03:00 · Última modificación: 2026-11-12T20:00:00-03:00 · Hito: M2 de [MVP.md](MVP.md) §10 · Requerimientos: RF-08, RF-09, RF-10, RF-11, RNF-01, RNF-08.

### Parámetros confirmados por el propietario (2026-11-12)

| Parámetro              | Valor                    | Significado                                                                                 |
| ---------------------- | ------------------------ | ------------------------------------------------------------------------------------------- |
| Amarillo               | 2 s                      | Transición fija tras el verde                                                               |
| Todo-rojo              | 2 s                      | Despeje con todos los accesos en rojo entre dos verdes                                      |
| Verde mínimo           | 5 s                      | Una vez dado, el verde no se corta antes                                                    |
| Verde máximo           | 20 s                     | Tope aunque siga habiendo demanda (equidad)                                                 |
| **T (vigencia)**       | 5 s                      | Un dato de `detections` con `processed_at` más viejo que T, o ausente, se considera vencido |
| Ciclo base de respaldo | 10 s de verde por acceso | Secuencia fija que se usa sin datos vigentes (modo seguro)                                  |

### Objetivo

Un proceso controlador y un semáforo simulado, ambos separados del detector y unidos solo por MQTT, de modo que: (a) con datos vigentes el verde pase al acceso con mayor demanda suavizada respetando mínimo y máximo; (b) al cortar la fuente (más de T s sin dato vigente) el controlador vuelva a ciclo fijo y lo declare; (c) el semáforo rechace secuencias inseguras. Cierre verificable de M2: se observa por MQTT un cambio de fase según la demanda y la vuelta a ciclo fijo al detener el detector.

### Alcance

- **Controlador** (`traffic_controller.py`): se suscribe a `trafico/v1/+/detections` (QoS 0). Mantiene por `approach_id` el último dato (`seq`, `session_id`, `processed_at`, `status`) y una demanda suavizada (media móvil exponencial de `visible_count`; el factor es un detalle de implementación, documentarlo). Descarta duplicados y fuera de orden por `seq` dentro de una `session_id`. Publica en `trafico/v1/<interseccion_id>/commands` (QoS 1, sin retención) un comando por cambio de fase.
- **Regla de vigencia (propuesta a confirmar al implementar):** si algún acceso configurado carece de dato vigente `ok`, el controlador usa el ciclo base de respaldo para toda la intersección y lo declara en `reason`. Es lo más simple y seguro; un modo degradado por acceso queda fuera.
- **Semáforo simulado** (`traffic_light_sim.py`): se suscribe a `commands`, valida la secuencia (nunca dos verdes a la vez; verde → amarillo → todo-rojo → siguiente verde; respeta los tiempos), muestra la fase en consola y publica la fase efectiva en `trafico/v1/<interseccion_id>/state` (QoS 1, retenido). Rechaza y registra un comando inseguro sin cambiar de fase. Sin pantalla gráfica; la vista de demo es M3.
- **Esquema del comando (se fija aquí, actualizar [protocolo](../protocol/mqtt/README.md) al implementar):** `v`, `event_id` (único), `intersection_id`, `issued_at` (ISO 8601 UTC), `phase` (objeto `approach_id → green|yellow|red`), `duration_s`, `reason` (`demand` | `fixed_cycle_no_data` | `max_green` | `min_green_hold` …), `mode` (`adaptive` | `fixed`).
- **Configuración por argumentos/constantes** con los valores de la tabla; accesos esperados: `acceso-01` y `acceso-02` (el segundo puede llegar de una fuente alternativa en M3; en M2 se prueba con `mosquitto_pub` como segundo detector).
- Identidades: `client_id` propio por proceso (`controller-<interseccion_id>`, `semaforo-<interseccion_id>`); `interseccion_id` por defecto `inter-01`.
- Cada proceso se reinicia sin reiniciar los otros (RNF-01); el estado retenido del semáforo permite que un controlador recién iniciado conozca la fase efectiva antes de ordenar.
- Logs con `approach_id`, `seq` y motivo de cada decisión (RNF-08); JSONL de decisiones es opcional (RF-13).

### Archivos esperados (estimados)

- `control/traffic_controller.py` y `control/traffic_light_sim.py` (carpeta nueva; ubicación a confirmar, el repositorio no tiene aún un directorio de decisión), más `control/pyproject.toml` o reutilizar el entorno del detector si basta `paho-mqtt`.
- `control/tests/` para la lógica pura (política y validador de secuencia).
- `protocol/mqtt/README.md` (esquema de `commands` y de `state` del semáforo), `docs/MVP.md` (estado de RF-08 a RF-11) y `docs/setup-linux.md` (receta de arranque).

### Tests esperados

- **Lógica, sin broker (pytest):** política (la demanda mayor gana el verde; respeta verde mínimo y máximo; amarillo y todo-rojo siempre presentes; empate; ambos accesos en cero); vigencia (dato más viejo que T, `unavailable`, acceso sin dato → ciclo fijo); dedupe y `seq` fuera de orden; validador del semáforo (rechaza dos verdes, salto verde → verde sin todo-rojo, tiempos menores al mínimo).
- **Integración con Mosquitto local:** `mosquitto_pub` simulando dos accesos con conteos distintos y observar `commands` y `state`; detener la publicación y confirmar `fixed_cycle_no_data` tras T s; reanudar y confirmar la vuelta a modo adaptativo; reiniciar controlador y semáforo por separado.
- **Físicas:** cadena completa con la ESP32-CAM real como acceso 1, y apagar la ESP para provocar `unavailable`. Registrar resultados en `setup-linux.md` §6.

### Fuera de alcance

LEDs o semáforo físico (RF-15), panel/vista de demo (M3), segundo acceso real con S3 (M3, D12), comparación espera fija vs adaptativa (RF-14), `state` con Last Will del ESP (RF-07), política definitiva (P07), persistencia, base de datos, autenticación del broker, métricas de espera/cruce.

### Decisiones bloqueantes

Ninguna. Puntos a confirmar durante la implementación sin detener el trabajo: ubicación de la carpeta `control/` y el criterio "un acceso sin dato fuerza ciclo fijo en toda la intersección".

### Pendiente previo (no es de M2)

Las correcciones del detector (reintento indefinido del stream, cierre limpio con Ctrl+C y Last Will) se aplicaron y el propietario las verificó el 2026-11-12 con ESP32-CAM, Mosquitto local y YOLO reales. El controlador no depende del `unavailable` final, solo de la vigencia T.

**Estado (2026-11-12T00:50:00-03:00):** implementado en `control/` (`traffic_logic.py` lógica pura, `traffic_controller.py`, `traffic_light_sim.py`, `tests/`). Tests de lógica: 36 de 36 OK (`python3 -m unittest discover -s control/tests`). Integración con Mosquitto local (puerto 18830) y accesos simulados con `mosquitto_pub`: cambio de fase por demanda, `fixed_cycle_no_data` tras T s, vuelta a adaptativo, rechazo de dos verdes, reinicio de controlador y semáforo por separado, controlador arrancado con el broker caído. **No verificado:** con el detector real/ESP32-CAM, con Mosquitto en red ni en hardware. Decisiones: carpeta `control/` y "un acceso sin dato fuerza ciclo fijo en toda la intersección" implementadas tal cual; `duration_s` es el mínimo garantizado de la fase; EMA con alpha 0,3; sin Last Will de controlador ni semáforo.

### Corrección 2026-11-12

Creada y última modificación: 2026-11-12T20:00:00-03:00. Hallazgos del ensayo del propietario con una ESP32-CAM real.

- **Causas.** (1) La demanda por acceso es una media móvil exponencial que nunca llega a 0 exacto; `demand > 0` y las comparaciones estrictas sin margen hacían alternar el verde para siempre entre un acceso vacío (residuo) y otro con conteo constante bajo. (2) `mode()` dependía solo de la vigencia instantánea: un `unavailable` o un silencio mayor que T por WiFi débil conmutaba entre fijo y adaptativo sin histéresis. (3) En el semáforo, `FASE`/`MODO` eran tipos de evento pero se leían como valores de modo; en el controlador cada `state` y cada detección ignorada se logueaban en INFO.
- **Parámetros nuevos** (`Params` y flags del controlador, validados): `demand_present` 0,5 (`--demand-present`; vehículos suavizados desde los que hay demanda), `switch_margin` 0,5 (`--switch-margin`), `fail_after` 10 s (`--fail-after`), `recover_after` 3 s (`--recover-after`). T (`--fresh` 5 s) y los demás valores no cambian. Se exige `fail_after >= T`.
- **Política.** Cambio por demanda solo si `mejor >= demand_present` y `mejor >= actual + switch_margin` (tras el verde mínimo); por verde máximo solo si `mejor >= demand_present`. **Reposo** (decisión del propietario): sin demanda en ningún acceso se mantiene el verde indefinidamente, sin comandos; el log registra una línea al entrar (`reposo: sin demanda, se mantiene <fase>`) y otra al salir (`reposo terminado`).
- **Histéresis.** Arranca en fijo. Fijo -> adaptativo cuando todos los accesos llevan `recover_after` seguidos con `ok` vigente (el cronómetro se reinicia si alguno se pierde; se mide por ticks del controlador). Adaptativo -> fijo cuando algún acceso lleva `fail_after` desde el `processed_at` de su último `ok` (incluye la ventana T; un `unavailable` solo cuenta como "sin ok nuevo"; sin ningún `ok` registrado cuenta como perdido). **Gracia** (adaptativo con algún dato vencido, antes de `fail_after`): la ausencia nunca vale cero, no se decide por demanda (con cualquier dato vencido), se mantiene la fase y se rota al siguiente acceso cíclico con `reason=max_green` al cumplirse el verde máximo. Cada transición de modo se registra en el log con su causa. No hay `reason` nuevos.
- **Logs.** Semáforo: `CAMBIO DE FASE` / `ACTUALIZA MODO` / `INICIO` y `orden: modo=.. motivo=..`. Controlador: `state` en DEBUG; detecciones ignoradas: la primera por (acceso, motivo) y luego un resumen con contador cada ~10 s; `--verbose` da el detalle por mensaje y DEBUG.
- **Estado.** Implementado. Verificado automáticamente: `python3 -m unittest discover -s control/tests` (lógica con reloj inyectado; incluye el escenario reproducido de 120 s, margen, reposo, histéresis, gracia, flapping y validación de todos los comandos con `SequenceValidator`). **No verificado:** ejecución de `traffic_controller.py` y `traffic_light_sim.py` contra un broker (el entorno de pruebas no tiene `paho`), ni con la ESP32-CAM real; el log real del controlador y la sensibilidad de `demand_present`/`switch_margin` con conteos reales siguen pendientes. Efecto colateral: en el arranque el primer verde sigue el ciclo fijo (la recuperación exige 3 s).

### Revisión del Project Mentor (2026-11-12T01:15:00-03:00)

Una iteración con el Coding Agent; no hizo falta devolver correcciones.

- **Verificado por el mentor:** 36 de 36 tests con `python3 -m unittest discover -s control/tests`. Los payloads reales del detector (`build_payload` y `build_will_payload` de `traffic_mqtt.py`) los acepta `ControllerLogic.on_detection`: `ok` fresco mantiene modo adaptativo y el will sin `seq` de un acceso pasa la intersección a ciclo fijo.
- **Desvío aceptado:** archivo extra `control/traffic_logic.py` (lógica pura testeable sin broker).
- **Pendiente 1 (bajo):** si el semáforo arranca después del controlador, el primer verde puede llegar antes de que cumpla su todo-rojo inicial; el semáforo lo rechaza y el controlador se resincroniza. Arrancar primero el semáforo evita el `RECHAZADO` del log.
- **Pendiente 2 (decisión del propietario, fuera de M2):** el semáforo no tiene temporizador propio. Si el controlador muere con una fase verde, esa fase queda indefinidamente. Aceptable en una simulación; antes de actuar sobre hardware requiere un fail-safe (p. ej. pasar a amarillo y todo-rojo tras verde máximo más margen sin comandos) y Last Will del semáforo.
- **Pendiente 3:** la vigencia compara `processed_at` del detector con el reloj del controlador; con equipos distintos y desfase mayor que T todo queda en ciclo fijo. En la misma PC no aplica.
- **Sin verificar:** cadena con detector y ESP32-CAM reales conectados al controlador (es el ensayo de M3/M4), Mosquitto en red, y `pytest` con el `.venv` del proyecto (el sandbox no lo ejecuta).

## 15. FailSafe-ImplementationBrief — Latido, lease, watchdog local y Last Will

Creado: 2026-11-12T21:00:00-03:00 · Última modificación: 2026-11-12T20:30:00-03:00 (estado al final; la hora de creación anotada era estimada) · Continúa M2 (§14). Requerimientos: RNF-01, RNF-02; refuerza RF-10 y RF-11. Es robustez de arquitectura, **no** está en la lista de "debe" del MVP: si el tiempo aprieta se recorta antes que M3/M4 (ver MVP.md §10).

### Problema

Hoy, si el controlador muere con una fase en verde, el semáforo simulado queda en esa fase indefinidamente (no tiene temporizador propio). Tampoco puede distinguir un controlador caído de un silencio normal: con demanda cero el controlador mantiene el verde **sin emitir comandos** (política de reposo), así que "no llegan comandos" no prueba que murió. Además, un `state` retenido de un semáforo caído puede hacer que el controlador adopte una fase que ya no existe.

### Decisiones tomadas (propuestas del mentor; el propietario eligió A+B+C+D el 2026-11-12)

- **A. Latido:** el controlador publica cada 1 s en `trafico/v1/<interseccion_id>/controller/heartbeat` (QoS 0, sin retención) `{v, instance_id, seq, sent_at, mode}`, esté en modo adaptativo o fijo y mientras tenga conexión. `instance_id` es un UUID nuevo en cada arranque.
- **B. Lease:** el semáforo considera vivo al controlador mientras reciba **cualquier** mensaje suyo (heartbeat o comando) dentro de `lease` segundos (propuesto 5 s). No se agrega `valid_until` por comando: el latido ya renueva el lease y un campo más sería redundante (descartado a propósito). El lease vence también si el broker o la red caen, sin importar la causa.
- **C. Watchdog local en el semáforo simulado:** al vencer el lease (o al llegar `offline`, ver D) pasa a `mode: failsafe`, `reason: controller_lost` y ejecuta su propia secuencia segura, **nunca saltando de verde a rojo**:
  - si está en verde: continúa ese verde hasta completar `max_green` desde que empezó la fase (si ya lo superó, pasa enseguida a amarillo), luego amarillo(X) → todo-rojo;
  - si está en amarillo o todo-rojo: completa la secuencia en curso;
  - después corre un ciclo fijo local (`fixed_green` por acceso, orden de `--approaches` a partir del siguiente al último verde, con amarillo y todo-rojo) y publica cada cambio en `state` con `mode: failsafe`.
    Las órdenes locales deben pasar por el mismo `SequenceValidator` (se reusa para garantizar la secuencia segura). Mientras está en failsafe ignora y registra los comandos recibidos.
- **Salida del failsafe (histéresis):** solo tras `recover_lease` segundos (propuesto 3 s) de lease sano continuo. Al salir conserva la fase y su `since` y desde ese momento valida los comandos normalmente. El controlador ya se resincroniza adoptando el `state` (aviso: su `_set_phase` usa la hora de adopción, no `since`, así que tras el regreso cree que la fase acaba de empezar; es conservador y aceptable).
- **D. Last Will y estado de proceso:**
  - Controlador: Last Will y estado `online`/`offline` retenido en `trafico/v1/<interseccion_id>/controller/status` (QoS 1) con `instance_id`. Al llegar `offline` el semáforo adelanta el failsafe sin esperar el lease. El will es complementario: no se dispara si cae el broker y tarda 1,5×keepalive; el watchdog es el que protege.
  - Semáforo (prioridad menor, **S**): Last Will/`online`/`offline` retenido en `trafico/v1/<interseccion_id>/light/status`; con `offline` el controlador no adopta el `state` retenido ni emite comandos hasta ver `online`.
  - Opcional (**C**, solo si es trivial): advertir en el log si llegan latidos con dos `instance_id` distintos en menos de `lease` (dos controladores a la vez).
- Parámetros nuevos como flags con validación: controlador `--heartbeat-every` (1 s); semáforo `--lease` (5 s), `--recover-lease` (3 s) y `--fixed-green` (mismo default que el controlador, 10 s). Validar `lease >= 2 × heartbeat_every`. Son propuestas ajustables; no bloquean.

### Alcance

Archivos esperados: `control/traffic_logic.py` (clase pura `FailSafe` o equivalente con reloj inyectado, sin MQTT; el watchdog local reusa `SequenceValidator`), `control/traffic_controller.py` (latido, will, `online`), `control/traffic_light_sim.py` (suscripción a `controller/#`, watchdog, `light/status`), `control/tests/`, `protocol/mqtt/README.md` (tópicos y payloads nuevos; `mode: failsafe` y `reason: controller_lost` en `state`), `docs/MVP.md` (nota en RF-10/RF-11), `docs/setup-linux.md` (receta y pruebas físicas). No crear otros `.md` en `docs/`.

### Tests esperados

- **Lógica pura (unittest, reloj inyectado):** lease que vence y que se renueva con latido o con comando; silencio de comandos con latidos vivos **no** dispara failsafe (reposo); failsafe desde verde temprano, verde pasado de `max_green`, amarillo y todo-rojo; nunca verde→rojo directo; el ciclo local alterna accesos y toda orden o estado generado es aceptado por `SequenceValidator`; ignorar comandos en failsafe; salida solo tras `recover_lease` continuos y reinicio del cronómetro si el lease vuelve a vencer; `offline` adelanta el failsafe; `instance_id` distinto no rompe nada.
- **Integración con Mosquitto local (puerto alto en el sandbox si es posible):** matar el controlador con `kill -9` en verde y observar la secuencia del semáforo; detenerlo con Ctrl+C y comparar; apagar el broker; reiniciar el controlador y observar la salida del failsafe.
- **Físicas (las ejecuta el propietario):** ver la receta que deje el agente en `setup-linux.md`.

### Fuera de alcance

ESP-NOW y coordinación entre semáforos físicos, modo intermitente y monitor de conflictos por hardware, controlador redundante con líder, persistencia, base de datos, autenticación del broker, LEDs, cambios en el detector, política de demanda y sus parámetros (ya corregidos), M3.

### Decisiones bloqueantes

Ninguna. Valores de `lease`, `recover_lease` y `heartbeat_every` son propuestas ajustables con el ensayo.

### Estado y revisión del Project Mentor (2026-11-12T20:30:00-03:00)

**Implementado** por el Coding Agent en una iteración; el mentor no devolvió correcciones.

- **Archivos:** `control/traffic_logic.py` (+`LeaseParams`, `FailSafe`, tópicos/payloads de latido y estado de proceso, `rotation_after`, `SequenceValidator.apply(..., modes=)` y `last_green`; `ControllerLogic.on_light_status`), `control/traffic_controller.py` (latido, Last Will/`online`/`offline` en `controller/status`, respeta `light/status`), `control/traffic_light_sim.py` (watchdog con tick cada `--tick` 0,2 s, suscripción a `controller/#`, Last Will/`online`/`offline` en `light/status`), `control/tests/test_failsafe.py` (29 tests nuevos) y `protocol/mqtt/README.md` (§2.3 y `state`).
- **Verificado por el mentor:** `python3 -m unittest discover -s control/tests` → 83 de 83 OK (54 previos + 29); `py_compile` de los tres archivos OK; revisión del diff contra este brief: secuencia desde verde (hasta `max_green` desde el inicio de la fase), amarillo y todo-rojo; ciclo local desde el siguiente al último verde; toda orden local pasa por `SequenceValidator`; comandos ignorados en failsafe pero renuevan el lease; salida tras `recover_lease` y reinicio del cronómetro; `offline` adelanta el failsafe; `offline` de otra instancia se ignora; aviso de dos `instance_id`.
- **Informado por el Coding Agent, no repetido por el mentor:** integración con Mosquitto 2.1.2 en el puerto 18831 (python3 3.14 + paho 2.2.0 por `PYTHONPATH`): `kill -9` del controlador en verde, Ctrl+C, reinicio, broker detenido (SIGTERM y `kill -9`) y SIGSTOP. Dos corridas suyas quedaron colgadas en el sandbox (verificar con `ps` fuera del sandbox y detenerlas si siguen).
- **Decisiones de implementación (aceptadas):**
  - `keepalive=15` en ambos procesos: el Last Will llega ~20 s después de un `kill -9`; antes actúa el lease (5 s).
  - Gracia de arranque: el semáforo da un lease al controlador para aparecer; **si arranca solo, a los 5 s entra en failsafe y corre el ciclo local** (cambio visible respecto de M2, es correcto).
  - Un `offline` retenido de un controlador anterior, con el semáforo sin instancia conocida, provoca failsafe inmediato hasta que llegan latidos durante 3 s.
  - Un `online` retenido no renueva el lease (puede ser viejo). Salir exige mensajes que abarquen `recover_lease` (un latido aislado no alcanza).
  - Al salir publica `reason: controller_recovered` con el modo del último latido; `mode: failsafe` en `commands` se rechaza (exclusivo del watchdog).
  - Al ignorar un comando en failsafe se republica `state` para que el controlador adopte la fase local.
- **Riesgos y pendientes (no bloquean la demo):**
  - El aviso de dos `instance_id` también aparece en un reinicio rápido del controlador (falso positivo esperado; el texto lo menciona).
  - El controlador tras la salida cree que la fase acaba de empezar (aviso ya previsto en el brief).
  - No verificado con la ESP32-CAM ni el detector real en la cadena, ni con Mosquitto en red. Recetas en [setup-linux.md](setup-linux.md) §4.
