"""Semáforo simulado (hito M2): actuación. Contrato: protocol/mqtt/README.md §2.

Escucha `commands`, valida la secuencia (traffic_logic.SequenceValidator), muestra la fase en consola y
publica la fase efectiva en `state` (QoS 1, retenido). Un comando inseguro se rechaza y se registra sin
cambiar de fase; el `state` se vuelve a publicar para que el controlador se resincronice.
"""
import argparse
import json
import logging
import time

from traffic_logic import Params, SequenceValidator, UnsafeCommand, commands_topic, phase_label, phase_to_dict, state_topic

log = logging.getLogger("semaforo")


def build_parser() -> argparse.ArgumentParser:
    d = Params()
    p = argparse.ArgumentParser(description="Semáforo simulado (M2)")
    p.add_argument("--mqtt-host", default="127.0.0.1")
    p.add_argument("--mqtt-port", type=int, default=1883)
    p.add_argument("--intersection-id", default="inter-01")
    p.add_argument("--approaches", default="acceso-01,acceso-02", help="accesos de la intersección, separados por coma")
    p.add_argument("--min-green", type=float, default=d.min_green_s)
    p.add_argument("--max-green", type=float, default=d.max_green_s)
    p.add_argument("--yellow", type=float, default=d.yellow_s)
    p.add_argument("--all-red", type=float, default=d.all_red_s)
    p.add_argument("--tolerance", type=float, default=0.3, help="holgura de tiempo mínimo por latencia (s)")
    return p


def main(argv=None):
    import paho.mqtt.client as mqtt  # import diferido: la lógica no lo necesita

    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    approaches = [a.strip() for a in args.approaches.split(",") if a.strip()]
    params = Params(yellow_s=args.yellow, all_red_s=args.all_red, min_green_s=args.min_green,
                    max_green_s=args.max_green)
    light = SequenceValidator(args.intersection_id, approaches, params, time.time(), args.tolerance)
    cmd_topic, st_topic = commands_topic(args.intersection_id), state_topic(args.intersection_id)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"semaforo-{args.intersection_id}")
    client.reconnect_delay_set(min_delay=1, max_delay=10)

    def publish_state():
        client.publish(st_topic, json.dumps(light.state_payload(time.time()), ensure_ascii=False),
                       qos=1, retain=True)

    def show(prefix: str):
        # CAMBIO DE FASE: la fase cambió; ACTUALIZA MODO: misma fase con modo o motivo nuevo.
        # `orden:` es la última orden recibida (en amarillo/todo-rojo/verde conserva el motivo que originó el cambio).
        luces = " ".join(f"{a}={v.upper()}" for a, v in phase_to_dict(light.phase, approaches).items())
        print(f"[{time.strftime('%H:%M:%S')}] {prefix} {phase_label(light.phase):<20} | {luces} "
              f"| orden: modo={light.mode} motivo={light.reason}", flush=True)

    def on_connect(c, userdata, flags, rc, props=None):
        log.info("conectado a %s:%s (%s)", args.mqtt_host, args.mqtt_port, rc)
        c.subscribe(cmd_topic, qos=1)
        publish_state()  # reafirma la fase efectiva (tras arrancar pisa el retenido de una ejecución anterior)

    def on_message(c, userdata, msg):
        try:
            cmd = json.loads(msg.payload)
        except ValueError:
            log.warning("RECHAZADO comando no JSON en %s", msg.topic)
            return
        try:
            outcome = light.apply(cmd, time.time())
        except UnsafeCommand as e:
            log.warning("RECHAZADO event_id=%s: %s (la fase sigue en %s)",
                        cmd.get("event_id") if isinstance(cmd, dict) else None, e, phase_label(light.phase))
            publish_state()
            return
        if outcome == "duplicate":
            log.info("comando duplicado ignorado event_id=%s", cmd["event_id"])
            return
        show("CAMBIO DE FASE" if outcome == "changed" else "ACTUALIZA MODO")
        publish_state()

    client.on_connect, client.on_message = on_connect, on_message
    client.on_disconnect = lambda c, u, f, rc, p=None: log.warning("desconectado (%s)", rc)
    client.connect_async(args.mqtt_host, args.mqtt_port, keepalive=15)
    client.loop_start()
    show("INICIO")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("cerrando")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
