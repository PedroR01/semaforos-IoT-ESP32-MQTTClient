# Contrato MQTT

## Estado actual

El contrato actual es legado y no debe considerarse una API estable:

- El firmware de sensores usa el tópico `semaforo/esp32`.
- `Broker::mqtt_callback` reconoce únicamente el payload textual `Detener`.
- El firmware publica mensajes de diagnóstico en el mismo tópico.
- No hay autenticación, TLS, versión de payload, correlación, confirmación ni integración con el detector Python.
- La documentación antigua menciona `emqx/esp32`, pero el código usa `semaforo/esp32`.

## Dirección futura

Antes de conectar YOLO con el semáforo se debe aprobar una versión del contrato que separe, como mínimo:

- `.../commands`: órdenes dirigidas al controlador.
- `.../state`: estado efectivo del semáforo.
- `.../telemetry`: sensores y salud del dispositivo.
- `.../detections`: eventos producidos por visión.

Cada mensaje deberá definir versión, `device_id`, `event_id`, timestamp, origen, unidades, QoS, retención, duplicados, autorización y comportamiento ante errores. Las detecciones deben comenzar como telemetría; no deben accionar hardware hasta especificar política y estado seguro.

La compatibilidad con `semaforo/esp32` y `Detener` debe implementarse, si se necesita, mediante un adaptador explícito y temporal.