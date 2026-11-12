# Contrato MQTT

Única fuente del contrato MQTT del proyecto. Los demás documentos enlazan aquí. Última revisión: 2026-11-08.

## 1. Contrato legado (sensor-controller, pausado)

No es una API estable:

- El firmware de sensores usa el tópico `semaforo/esp32`.
- `Broker::mqtt_callback` reconoce únicamente el payload textual `Detener`.
- El firmware publica mensajes de diagnóstico (`Probando Mosquitto`) en el mismo tópico.
- No hay autenticación, TLS, versión de payload, correlación ni confirmación.
- La documentación antigua mencionaba `emqx/esp32`, pero el código usa `semaforo/esp32`.

La compatibilidad con `semaforo/esp32` y `Detener`, si se necesita, se implementa mediante un adaptador explícito y temporal. No reutilizar `Detener` como orden del sistema nuevo.

## 2. Contrato del MVP (propuesta; `detections` implementado en el detector el 2026-11-08, sin verificar contra broker)

Raíz de tópicos: `trafico/v1/`. Versión de payload en el campo `v`. Alcance y motivos en [docs/MVP.md](../../docs/MVP.md).

| Tópico | Publica | Contenido | QoS | Retención |
| --- | --- | --- | --- | --- |
| `trafico/v1/<camera_id>/detections` | Detector (percepción) | Conteos y estado de la observación | 0 | No |
| `trafico/v1/<camera_id>/state` | ESP (con Last Will) | `online`/`offline`, IP, RSSI | 1 | Sí |
| `trafico/v1/<interseccion_id>/commands` | Controlador (decisión) | Fase por acceso, duración y motivo | 1 | No |
| `trafico/v1/<interseccion_id>/state` | Semáforo (actuación) | Fase efectiva | 1 | Sí |

Ejemplo de `detections` (ilustrativo; **no es la salida actual** de los scripts):

```json
{
  "v": 1,
  "camera_id": "cam-01",
  "approach_id": "acceso-01",
  "processing_mode": "external",
  "session_id": "sesion-ejemplo-01",
  "seq": 1,
  "processed_at": "2026-11-13T12:00:00Z",
  "status": "ok",
  "metrics": {
    "visible_count": 4,
    "by_class": {"auto": 3, "moto": 1, "bicicleta": 0, "colectivo": 0, "camion": 0}
  }
}
```

Reglas:

- Un frame válido sin vehículos publica ceros. Una cámara caída, un stream sin frames o una inferencia fallida publican `"status": "unavailable"` y no incluyen conteos; nunca ceros.
- Publicar aproximadamente una vez por segundo. `seq` ordena dentro de una `session_id`; el receptor descarta duplicados y datos vencidos.
- `processed_at` es el momento de procesamiento, no el de captura.
- El controlador considera vencido un dato más viejo que T segundos (valor por definir) y pasa a ciclo fijo.
- Las detecciones son telemetría. Solo el controlador publica en `commands`, y el semáforo rechaza secuencias inseguras.
- Un `camera_id` y un `client_id` MQTT por dispositivo o proceso; nunca repetidos.
- Los tópicos `.../telemetry` (sensores y salud del dispositivo) quedan reservados y sin definir.

Cada mensaje de `commands` debe incluir además `event_id`, `phase`, `duration_s` y `reason`. Su esquema exacto se fija al implementar el hito M2.

## 3. Probar el broker

Necesita un broker MQTT real; **`python -m http.server` crea un servidor HTTP y no sirve**. Pasos completos en [setup-linux.md](../../docs/setup-linux.md) (sección 5) y [setup-windows.md](../../docs/setup-windows.md).

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'semaforo/esp32' -v
mosquitto_pub -h 127.0.0.1 -p 1883 -t 'semaforo/esp32' -m 'Detener'
```

Broker público para pruebas (sin garantías ni privacidad; no usar con datos reales):

```bash
mosquitto_sub -h broker.emqx.io -p 1883 -t 'semaforo/esp32' -v
```

## 4. Requisitos antes de actuar sobre hardware

Las detecciones no deben accionar hardware hasta contar con política aprobada y estado seguro. El semáforo físico queda fuera del MVP (D10).
