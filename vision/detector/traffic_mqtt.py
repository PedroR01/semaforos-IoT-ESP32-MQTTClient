"""Publicación MQTT del detector (hito M1). Contrato: protocol/mqtt/README.md §2.

Solo percepción: publica conteos u "unavailable". No decide fases.
"""
import json
from datetime import datetime, timezone

TOPIC_ROOT = "trafico/v1"
PAYLOAD_VERSION = 1
CLASES_LOGICAS = ("auto", "moto", "bicicleta", "colectivo", "camion")


def utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_session_id(camera_id: str, ts: float) -> str:
    return f"{camera_id}-{datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def detections_topic(camera_id: str, root: str = TOPIC_ROOT) -> str:
    return f"{root}/{camera_id}/detections"


def build_payload(*, camera_id: str, approach_id: str, session_id: str, seq: int,
                  now: float, current: dict | None) -> dict:
    """`current` = conteo por clase del frame actual, o None si no hay observación válida.

    Un frame válido sin vehículos es `{}` o ceros -> status ok con ceros.
    None (stream caído, inferencia fallida) -> status unavailable, sin métricas.
    """
    payload = {
        "v": PAYLOAD_VERSION,
        "camera_id": camera_id,
        "approach_id": approach_id,
        "processing_mode": "external",
        "session_id": session_id,
        "seq": seq,
        "processed_at": utc_iso(now),
    }
    if current is None:
        payload["status"] = "unavailable"
        return payload
    by_class = {c: int(current.get(c, 0)) for c in CLASES_LOGICAS}
    payload["status"] = "ok"
    payload["metrics"] = {"visible_count": sum(by_class.values()), "by_class": by_class}
    return payload


def build_will_payload(*, camera_id: str, approach_id: str, session_id: str) -> dict:
    """Payload del Last Will: `unavailable` sin `seq` ni `processed_at`.

    El will se fija al conectar y el broker lo emite después, así que no hay un seq
    ni un instante de procesamiento reales que dar; inventarlos violaría el orden
    por `seq` y la regla de que `processed_at` es el momento de procesamiento.
    """
    return {
        "v": PAYLOAD_VERSION,
        "camera_id": camera_id,
        "approach_id": approach_id,
        "processing_mode": "external",
        "session_id": session_id,
        "status": "unavailable",
    }


class DetectionPublisher:
    """Publica en `<root>/<camera_id>/detections` (QoS 0, sin retención).

    Usa connect_async + loop_start: si el broker no está, el detector sigue
    funcionando y paho reintenta; los mensajes publicados sin conexión se pierden
    (QoS 0), lo que es coherente con datos que vencen en segundos.
    """

    def __init__(self, host: str, port: int, camera_id: str, approach_id: str,
                 session_id: str, root: str = TOPIC_ROOT):
        import paho.mqtt.client as mqtt  # import diferido: no hace falta para los tests

        self.camera_id = camera_id
        self.approach_id = approach_id
        self.session_id = session_id
        self.topic = detections_topic(camera_id, root)
        self.seq = 0
        self._last_info = None
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"detector-{camera_id}",  # un client_id por proceso
        )
        self.client.on_connect = lambda c, u, f, rc, p=None: print(f"[MQTT] conectado a {host}:{port} ({rc})")
        self.client.on_disconnect = lambda c, u, f, rc, p=None: print(f"[MQTT] desconectado ({rc})")
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        # Last Will: cubre caídas sin despedida (kill -9, corte de red). Antes de connect_async.
        will = build_will_payload(camera_id=camera_id, approach_id=approach_id, session_id=session_id)
        self.client.will_set(self.topic, json.dumps(will, ensure_ascii=False), qos=0, retain=False)
        self.client.connect_async(host, port, keepalive=15)
        self.client.loop_start()

    def publish(self, now: float, current: dict | None) -> dict:
        self.seq += 1
        payload = build_payload(camera_id=self.camera_id, approach_id=self.approach_id,
                                session_id=self.session_id, seq=self.seq,
                                now=now, current=current)
        self._last_info = self.client.publish(
            self.topic, json.dumps(payload, ensure_ascii=False), qos=0, retain=False)
        return payload

    def close(self, timeout: float = 2.0):
        # publish() es asíncrono: esperar el envío del último mensaje antes de desconectar.
        # Sin conexión no bloquea más que `timeout` (o falla de inmediato y se ignora).
        if self._last_info is not None:
            try:
                self._last_info.wait_for_publish(timeout=timeout)
            except Exception as e:
                print(f"[MQTT] último mensaje sin confirmar: {e}")
        self.client.loop_stop()
        self.client.disconnect()
