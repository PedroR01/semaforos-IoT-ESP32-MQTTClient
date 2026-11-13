"""Controlador de semáforo (hito M2): decisión. Contrato: protocol/mqtt/README.md §2.

Escucha `trafico/v1/+/detections`, el `state` del semáforo y su `light/status`; publica `commands` (QoS 1, sin
retención), un latido cada `--heartbeat-every` s en `controller/heartbeat` y su `online`/`offline` retenido en
`controller/status` (con Last Will). La política vive en traffic_logic.py; este archivo solo hace E/S MQTT,
CLI y logs.
"""
import argparse
import json
import logging
import threading
import time
import uuid

from traffic_logic import (OFFLINE, ONLINE, TOPIC_ROOT, ControllerLogic, Params, commands_topic,
                           controller_heartbeat_topic, controller_status_topic, heartbeat_payload,
                           light_status_topic, phase_from_dict, phase_label, process_status_payload, state_topic)

log = logging.getLogger("controller")
IGNORED_SUMMARY_S = 10.0


class IgnoredLog:
    """Limita el log de detecciones ignoradas: la primera por (acceso, motivo) y luego un resumen cada ~10 s."""

    def __init__(self, interval_s: float = IGNORED_SUMMARY_S):
        self.interval_s = interval_s
        self._seen: dict[tuple, list] = {}  # clave -> [último log, repeticiones sin loguear]

    def note(self, approach, outcome: str, now: float) -> str | None:
        """Texto a loguear, o None si esta ocurrencia queda contada para el próximo resumen."""
        key = (approach, outcome.split(" (")[0])  # sin los números variables entre paréntesis
        entry = self._seen.get(key)
        if entry is None:
            self._seen[key] = [now, 0]
            return f"{approach}: {outcome}"
        entry[1] += 1
        if now - entry[0] < self.interval_s:
            return None
        count, entry[0], entry[1] = entry[1], now, 0
        return f"{approach}: {key[1]} (x{count} en los últimos {self.interval_s:.0f} s)"


def build_parser() -> argparse.ArgumentParser:
    d = Params()
    p = argparse.ArgumentParser(description="Controlador de semáforo adaptativo (M2)")
    p.add_argument("--mqtt-host", default="127.0.0.1")
    p.add_argument("--mqtt-port", type=int, default=1883)
    p.add_argument("--intersection-id", default="inter-01")
    p.add_argument("--approaches", default="acceso-01,acceso-02", help="accesos esperados, separados por coma")
    p.add_argument("--min-green", type=float, default=d.min_green_s)
    p.add_argument("--max-green", type=float, default=d.max_green_s)
    p.add_argument("--yellow", type=float, default=d.yellow_s)
    p.add_argument("--all-red", type=float, default=d.all_red_s)
    p.add_argument("--fresh", type=float, default=d.fresh_s, help="T: vigencia de un dato (s)")
    p.add_argument("--fixed-green", type=float, default=d.fixed_green_s, help="verde por acceso en ciclo fijo (s)")
    p.add_argument("--ema-alpha", type=float, default=d.ema_alpha, help="peso de la muestra nueva en la media móvil")
    p.add_argument("--demand-present", type=float, default=d.demand_present,
                   help="vehículos suavizados desde los que un acceso tiene demanda")
    p.add_argument("--switch-margin", type=float, default=d.switch_margin,
                   help="ventaja mínima (vehículos suavizados) sobre el verde actual para cambiar por demanda")
    p.add_argument("--fail-after", type=float, default=d.fail_after_s,
                   help="s sin ok de un acceso (desde su último ok) para pasar a ciclo fijo")
    p.add_argument("--recover-after", type=float, default=d.recover_after_s,
                   help="s seguidos con ok vigente en todos los accesos para volver a adaptativo")
    p.add_argument("--heartbeat-every", type=float, default=1.0,
                   help="s entre latidos; el --lease del semáforo debe ser al menos el doble")
    p.add_argument("--state-wait", type=float, default=2.0, help="espera inicial por el state retenido del semáforo (s)")
    p.add_argument("--tick", type=float, default=0.2)
    p.add_argument("--verbose", action="store_true", help="detalle por mensaje (detecciones, state, ignoradas) y nivel DEBUG")
    return p


def main(argv=None):
    import paho.mqtt.client as mqtt  # import diferido: la lógica no lo necesita

    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(name)s %(message)s")
    approaches = [a.strip() for a in args.approaches.split(",") if a.strip()]
    if args.heartbeat_every <= 0:
        parser.error("--heartbeat-every debe ser > 0")
    try:
        params = Params(yellow_s=args.yellow, all_red_s=args.all_red, min_green_s=args.min_green,
                        max_green_s=args.max_green, fresh_s=args.fresh, fixed_green_s=args.fixed_green,
                        ema_alpha=args.ema_alpha, demand_present=args.demand_present,
                        switch_margin=args.switch_margin, fail_after_s=args.fail_after,
                        recover_after_s=args.recover_after)
    except ValueError as e:
        parser.error(str(e))
    instance_id = uuid.uuid4().hex  # nuevo en cada arranque: el semáforo distingue instancias
    logic = ControllerLogic(args.intersection_id, approaches, params, time.time(), args.state_wait)
    ignored_log = IgnoredLog()
    lock = threading.Lock()  # la lógica se toca desde el hilo de paho y desde el bucle principal
    connected = threading.Event()
    cmd_topic, st_topic = commands_topic(args.intersection_id), state_topic(args.intersection_id)
    hb_topic, status_topic = controller_heartbeat_topic(args.intersection_id), controller_status_topic(args.intersection_id)
    light_topic = light_status_topic(args.intersection_id)
    det_filter = f"{TOPIC_ROOT}/+/detections"

    def status_json(status, now=None):
        return json.dumps(process_status_payload(args.intersection_id, status, now, instance_id=instance_id))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"controller-{args.intersection_id}")
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.will_set(status_topic, status_json(OFFLINE), qos=1, retain=True)

    def on_connect(c, userdata, flags, rc, props=None):
        log.info("conectado a %s:%s (%s) instance_id=%s", args.mqtt_host, args.mqtt_port, rc, instance_id)
        c.publish(status_topic, status_json(ONLINE, time.time()), qos=1, retain=True)
        c.subscribe([(det_filter, 0), (st_topic, 1), (light_topic, 1)])  # al reconectar se vuelve a suscribir
        connected.set()

    def on_disconnect(c, userdata, flags, rc, props=None):
        connected.clear()
        log.warning("desconectado (%s); sin comandos hasta reconectar", rc)

    def on_message(c, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            log.warning("payload no JSON en %s", msg.topic)
            return
        now = time.time()
        with lock:
            if msg.topic == light_topic:
                log.info("light/status: %s", logic.on_light_status(payload, now))
                for note in logic.pop_notes():  # el bucle principal no vacía notas mientras está desconectado
                    log.info(note)
                return
            if msg.topic == st_topic:
                outcome = logic.on_effective_state(payload, now)
                log.debug("state del semáforo: %s -> %s", _summary(payload, approaches), outcome)
                return
            outcome = logic.on_detection(payload, now)
        if outcome == "accepted":
            log.debug("detections %s seq=%s status=%s: accepted", payload["approach_id"],
                      payload.get("seq"), payload.get("status"))
            return
        approach = payload.get("approach_id") if isinstance(payload, dict) else None
        text = outcome if args.verbose else ignored_log.note(approach, outcome, now)
        if text:
            log.info("detections %s", text)

    client.on_connect, client.on_disconnect, client.on_message = on_connect, on_disconnect, on_message
    client.connect_async(args.mqtt_host, args.mqtt_port, keepalive=15)  # el broker puede estar caído al arrancar
    client.loop_start()
    log.info("controlador %s accesos=%s params=%s heartbeat_every=%s", args.intersection_id, approaches,
             params, args.heartbeat_every)
    hb_seq, next_hb = 0, 0.0
    try:
        while True:
            time.sleep(args.tick)
            if not connected.is_set():
                continue  # un comando QoS 1 encolado sin conexión llegaría vencido
            now = time.time()
            with lock:
                if now >= next_hb:  # en cualquier modo y aunque no haya comandos (reposo)
                    hb_seq, next_hb = hb_seq + 1, now + args.heartbeat_every
                    client.publish(hb_topic, json.dumps(heartbeat_payload(instance_id, hb_seq, now,
                                                                          logic.current_mode)), qos=0, retain=False)
                cmd = logic.tick(now)
                summary = logic.describe(now) if cmd else ""
                notes = logic.pop_notes()
            for note in notes:  # antes del COMANDO que provocan
                log.info(note)
            if cmd:
                client.publish(cmd_topic, json.dumps(cmd, ensure_ascii=False), qos=1, retain=False)
                log.info("COMANDO %s mode=%s reason=%s duration_s=%s event_id=%s | %s",
                         phase_label(phase_from_dict(cmd["phase"], approaches)), cmd["mode"],
                         cmd["reason"], cmd["duration_s"], cmd["event_id"], summary)
    except KeyboardInterrupt:
        log.info("cerrando: publica offline")
    finally:
        if connected.is_set():  # cierre limpio: el broker no publica el Last Will, se avisa explícitamente
            info = client.publish(status_topic, status_json(OFFLINE, time.time()), qos=1, retain=True)
            info.wait_for_publish(timeout=2)
        client.disconnect()
        client.loop_stop()


def _summary(state, approaches) -> str:
    try:
        return phase_label(phase_from_dict(state["phase"], approaches))
    except (KeyError, TypeError, ValueError):
        return "?"


if __name__ == "__main__":
    main()
