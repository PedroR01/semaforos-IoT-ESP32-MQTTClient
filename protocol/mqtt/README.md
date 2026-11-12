# Contrato MQTT

Única fuente del contrato MQTT del proyecto. Los demás documentos enlazan aquí. Última revisión: 2026-11-12.

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
- **Last Will del detector:** al conectar, el detector registra en el mismo tópico `detections` un mensaje de última voluntad con `status: "unavailable"` (QoS 0, sin retención). El broker lo publica si el detector desaparece sin despedirse (crash, `kill -9`, corte de red). Ese mensaje **no incluye `seq` ni `processed_at`** (es fijo y no tendría un valor honesto), ni `metrics`; sí incluye `v`, `camera_id`, `approach_id`, `session_id` y `processing_mode`. Por tanto, en un mensaje `unavailable` `seq` y `processed_at` son opcionales: el receptor debe aceptarlo y no descartarlo por falta de `seq` ni usarlo para el orden o el descarte de duplicados. El detector, además, publica un `unavailable` normal (con `seq`) al cerrarse con limpieza y mientras el stream no esté disponible. Verificado el 2026-11-12 (Ctrl+C, apagado de la ESP y corte del broker).
- El controlador considera vencido un dato `ok` cuyo `processed_at` es más viejo que T = 5 s (o ausente) y, si algún acceso configurado lleva al menos 10 s sin `ok` (medido desde el `processed_at` de su último `ok`; un `unavailable` no cambia el modo por sí solo), pasa toda la intersección a ciclo fijo. Vuelve a adaptativo cuando todos los accesos llevan 3 s seguidos con `ok` vigente. Entre ambos umbrales (dato vencido pero antes de 10 s) se mantiene el modo y la fase actual, sin tratar la ausencia como cero. Sin cambios en los campos ni en los valores de `reason`.
- Las detecciones son telemetría. Solo el controlador publica en `commands`, y el semáforo rechaza secuencias inseguras.
- Un `camera_id` y un `client_id` MQTT por dispositivo o proceso; nunca repetidos.
- Los tópicos `.../telemetry` (sensores y salud del dispositivo) quedan reservados y sin definir.

### 2.1 `commands` (controlador → semáforo; implementado el 2026-11-12, probado con Mosquitto local, sin hardware)

```json
{
  "v": 1,
  "event_id": "771b7be73b544c9cab8e59e8ce30a23d",
  "intersection_id": "inter-01",
  "issued_at": "2026-11-12T03:44:28Z",
  "phase": {"acceso-01": "yellow", "acceso-02": "red"},
  "duration_s": 2.0,
  "reason": "demand",
  "mode": "adaptive"
}
```

- `phase`: `approach_id -> green|yellow|red`, con exactamente los accesos de la intersección. Fases válidas: un solo verde y el resto rojo; un solo amarillo y el resto rojo; todo rojo.
- `duration_s`: **tiempo mínimo garantizado** de esa fase, no su duración total. Amarillo = 2 s, todo-rojo = 2 s; verde adaptativo = verde mínimo (5 s; dura hasta el siguiente comando, máximo 20 s); verde en ciclo fijo = 10 s. La fase vigente dura hasta el siguiente comando.
- `reason`: `demand`, `max_green`, `fixed_cycle_no_data`, `startup` (arranque), `data_recovered` (vuelta a adaptativo). `min_green_hold` no se emite.
- `mode`: `adaptive` o `fixed` (ciclo base de respaldo por falta de dato vigente).
- Secuencia: todo-rojo -> verde(X) -> amarillo(X) -> todo-rojo -> verde(Y). Un cambio de modo sin cambio de fase se declara con un comando de la **misma** fase y nuevo `mode`/`reason` (el semáforo lo acepta como "refresco").
- QoS 1, sin retención, un `event_id` único por comando (el semáforo ignora un `event_id` repetido).

### 2.2 `state` del semáforo (semáforo → todos; QoS 1, retenido)

```json
{
  "v": 1,
  "intersection_id": "inter-01",
  "phase": {"acceso-01": "red", "acceso-02": "green"},
  "since": "2026-11-12T03:44:32Z",
  "duration_s": 5.0,
  "event_id": "e525d174e08b4fd6b41604a27c55e3ec",
  "mode": "adaptive",
  "reason": "demand",
  "updated_at": "2026-11-12T03:44:32Z"
}
```

- Es la **fase efectiva**. `since` es cuándo cambió de fase; `event_id`, `mode` y `reason` son los del último comando aceptado (`null` / `sim_start` al arrancar, que parte en todo-rojo).
- Se publica al conectar, tras cada comando aceptado y **tras cada comando rechazado** (para que el controlador se resincronice).
- El controlador adopta la fase de un `state` cuyo `event_id` no es el último que emitió y cuya fase difiere de la que cree; así un controlador recién iniciado conoce la fase efectiva antes de ordenar.
- El semáforo rechaza (registra y no cambia de fase) un comando con: dos o más verdes, verde y amarillo a la vez, transición fuera de la secuencia (p. ej. verde -> verde o verde -> todo-rojo), `duration_s` menor al mínimo de la fase, fase actual que no cumplió su tiempo mínimo (holgura 0,3 s por latencia), `intersection_id` ajeno o campos inválidos.
- Sin Last Will del semáforo: si el proceso muere, el `state` retenido queda con la última fase.

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
