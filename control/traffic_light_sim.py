"""Semáforo simulado (hito M2): actuación. Contrato: protocol/mqtt/README.md §2.

Escucha `commands` y `controller/#`, valida la secuencia (traffic_logic.SequenceValidator), muestra la fase en
consola y publica la fase efectiva en `state` (QoS 1, retenido). Un comando inseguro se rechaza y se registra
sin cambiar de fase; el `state` se vuelve a publicar para que el controlador se resincronice.
Watchdog (traffic_logic.FailSafe): sin latidos ni comandos del controlador durante `--lease` s, o con su
`offline`, pasa a `mode=failsafe` y corre una secuencia segura local hasta que el controlador vuelve.
Publica su propio `online`/`offline` retenido en `light/status` (con Last Will).
"""
import argparse
import json
import logging
import threading
import time

from traffic_logic import (FAILSAFE, OFFLINE, ONLINE, TOPIC_ROOT, FailSafe, LeaseParams, Params, SequenceValidator,
                           UnsafeCommand, commands_topic, controller_heartbeat_topic, controller_status_topic,
                           light_status_topic, phase_from_dict, phase_label, phase_to_dict, process_status_payload, state_topic)

log = logging.getLogger("semaforo")


def build_parser() -> argparse.ArgumentParser:
    d, lease = Params(), LeaseParams()
    p = argparse.ArgumentParser(description="Semáforo simulado (M2) con watchdog local")
    p.add_argument("--mqtt-host", default="127.0.0.1")
    p.add_argument("--mqtt-port", type=int, default=1883)
    p.add_argument("--intersection-id", default="inter-01")
    p.add_argument("--approaches", default="acceso-01,acceso-02", help="accesos de la intersección, separados por coma")
    p.add_argument("--min-green", type=float, default=d.min_green_s)
    p.add_argument("--max-green", type=float, default=d.max_green_s,
                   help="también es el tope del verde en curso al entrar en failsafe")
    p.add_argument("--yellow", type=float, default=d.yellow_s)
    p.add_argument("--all-red", type=float, default=d.all_red_s)
    p.add_argument("--fixed-green", type=float, default=d.fixed_green_s, help="verde por acceso del ciclo local en failsafe (s)")
    p.add_argument("--lease", type=float, default=lease.lease_s,
                   help="s sin latido ni comando del controlador para entrar en failsafe")
    p.add_argument("--recover-lease", type=float, default=lease.recover_lease_s,
                   help="s de mensajes continuos del controlador para salir del failsafe")
    p.add_argument("--heartbeat-every", type=float, default=lease.heartbeat_every_s,
                   help="latido que se asume del controlador; se exige --lease >= 2 x este valor")
    p.add_argument("--tolerance", type=float, default=0.3, help="holgura de tiempo mínimo por latencia (s)")
    p.add_argument("--tick", type=float, default=0.2, help="periodo del watchdog (s)")
    return p


def main(argv=None):
    import paho.mqtt.client as mqtt  # import diferido: la lógica no lo necesita

    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    approaches = [a.strip() for a in args.approaches.split(",") if a.strip()]
    try:
        params = Params(yellow_s=args.yellow, all_red_s=args.all_red, min_green_s=args.min_green,
                        max_green_s=args.max_green, fixed_green_s=args.fixed_green)
        lease = LeaseParams(lease_s=args.lease, recover_lease_s=args.recover_lease,
                            heartbeat_every_s=args.heartbeat_every)
    except ValueError as e:
        parser.error(str(e))
    now = time.time()
    light = SequenceValidator(args.intersection_id, approaches, params, now, args.tolerance)
    watchdog = FailSafe(light, lease, now)
    lock = threading.Lock()  # validador y watchdog se tocan desde el hilo de paho y desde el bucle principal
    connected = threading.Event()
    cmd_topic, st_topic = commands_topic(args.intersection_id), state_topic(args.intersection_id)
    hb_topic, ctrl_status_topic = (controller_heartbeat_topic(args.intersection_id),
                                   controller_status_topic(args.intersection_id))
    own_status_topic = light_status_topic(args.intersection_id)
    controller_filter = f"{TOPIC_ROOT}/{args.intersection_id}/controller/#"

    def status_json(status, ts=None):
        return json.dumps(process_status_payload(args.intersection_id, status, ts))

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"semaforo-{args.intersection_id}")
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.will_set(own_status_topic, status_json(OFFLINE), qos=1, retain=True)

    def publish_state():
        client.publish(st_topic, json.dumps(light.state_payload(time.time()), ensure_ascii=False),
                       qos=1, retain=True)

    def show(prefix: str, order: dict | None = None):
        # CAMBIO DE FASE: la fase cambió; ACTUALIZA MODO: misma fase con modo o motivo nuevo; FAILSAFE/...: orden
        # local del watchdog. `orden:` es la última orden aceptada (del controlador o local).
        if order is None:
            phase, mode, reason = light.phase, light.mode, light.reason
        else:
            phase, mode, reason = phase_from_dict(order["phase"], approaches), order["mode"], order["reason"]
        luces = " ".join(f"{a}={v.upper()}" for a, v in phase_to_dict(phase, approaches).items())
        print(f"[{time.strftime('%H:%M:%S')}] {prefix} {phase_label(phase):<20} | {luces} "
              f"| orden: modo={mode} motivo={reason}", flush=True)

    def on_connect(c, userdata, flags, rc, props=None):
        log.info("conectado a %s:%s (%s)", args.mqtt_host, args.mqtt_port, rc)
        c.publish(own_status_topic, status_json(ONLINE, time.time()), qos=1, retain=True)
        c.subscribe([(cmd_topic, 1), (controller_filter, 1)])
        with lock:
            publish_state()  # reafirma la fase efectiva (tras arrancar pisa el retenido de una ejecución anterior)
        connected.set()

    def on_command(cmd, now):
        try:
            outcome = watchdog.on_command(cmd, now)
        except UnsafeCommand as e:
            log.warning("RECHAZADO event_id=%s: %s (la fase sigue en %s)",
                        cmd.get("event_id") if isinstance(cmd, dict) else None, e, phase_label(light.phase))
            publish_state()
            return
        if outcome == "duplicate":
            log.info("comando duplicado ignorado event_id=%s", cmd["event_id"])
        elif outcome == "ignored_failsafe":
            log.info("IGNORADO en failsafe event_id=%s (la fase sigue en %s)",
                     cmd.get("event_id") if isinstance(cmd, dict) else None, phase_label(light.phase))
            publish_state()  # para que el controlador adopte la fase local
        else:
            show("CAMBIO DE FASE" if outcome == "changed" else "ACTUALIZA MODO")
            publish_state()

    def on_message(c, userdata, msg):
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            log.warning("payload no JSON en %s", msg.topic)
            if msg.topic != cmd_topic:
                return
            payload = None  # en commands igual renueva el lease y se rechaza como comando inválido
        now = time.time()
        with lock:
            if msg.topic == cmd_topic:
                on_command(payload, now)
            elif msg.topic == hb_topic:
                outcome = watchdog.on_heartbeat(payload, now)
                if outcome != "accepted":
                    log.warning("latido %s", outcome)
            elif msg.topic == ctrl_status_topic:
                log.info("controller/status: %s", watchdog.on_controller_status(payload, now))

    def on_disconnect(c, userdata, flags, rc, props=None):
        connected.clear()
        log.warning("desconectado (%s); el watchdog sigue corriendo", rc)

    client.on_connect, client.on_message, client.on_disconnect = on_connect, on_message, on_disconnect
    client.connect_async(args.mqtt_host, args.mqtt_port, keepalive=15)
    client.loop_start()
    show("INICIO")
    log.info("watchdog lease=%s recover_lease=%s fixed_green=%s", lease.lease_s, lease.recover_lease_s,
             params.fixed_green_s)
    try:
        while True:
            time.sleep(args.tick)
            with lock:
                orders = watchdog.tick(time.time())  # el lease vence en silencio: no depende de mensajes
                notes = watchdog.pop_notes()
                for note in notes:
                    log.warning(note) if note.startswith(("FAILSAFE:", "AVISO")) else log.info(note)
                for order in orders:
                    show("FAILSAFE" if order["mode"] == FAILSAFE else "SALE DE FAILSAFE", order)
                if orders:
                    publish_state()
    except KeyboardInterrupt:
        log.info("cerrando: publica offline")
    finally:
        if connected.is_set():  # cierre limpio: el broker no publica el Last Will, se avisa explícitamente
            info = client.publish(own_status_topic, status_json(OFFLINE, time.time()), qos=1, retain=True)
            info.wait_for_publish(timeout=2)
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
