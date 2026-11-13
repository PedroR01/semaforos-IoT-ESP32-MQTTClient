"""Watchdog local del semáforo (docs/reference.md §15): lease, secuencia segura propia y Last Will."""
import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from traffic_logic import (ADAPTIVE, ALL_RED, FAILSAFE, FIXED, GREEN, YELLOW, ControllerLogic,  # noqa: E402
                           FailSafe, LeaseParams, Params, SequenceValidator, heartbeat_payload,
                           phase_from_dict, process_status_payload, UnsafeCommand)

APP = ["acceso-01", "acceso-02"]
P = Params()
L = LeaseParams()
T0 = 1_700_000_000.0
ALLOWED = {GREEN: YELLOW, YELLOW: ALL_RED, ALL_RED: GREEN}


def cmd(phase_kind, approach, eid, approaches=APP, duration=None, mode=ADAPTIVE, reason="demand"):
    phase = {a: (phase_kind if a == approach else "red") for a in approaches}
    if duration is None:
        duration = {GREEN: P.min_green_s, YELLOW: P.yellow_s, ALL_RED: P.all_red_s}[phase_kind]
    return {"v": 1, "event_id": eid, "intersection_id": "inter-01", "issued_at": "x",
            "phase": phase, "duration_s": duration, "reason": reason, "mode": mode}


def hb(instance="ctrl-A", seq=1, now=T0, mode=ADAPTIVE):
    return heartbeat_payload(instance, seq, now, mode)


class Light:
    """Semáforo con watchdog; avanza el reloj de a 0.1 s, opcionalmente con latidos a 1 Hz, y registra cada
    orden local aplicada (fase, modo, motivo)."""

    def __init__(self, approaches=APP, lease=L):
        self.now = T0
        self.approaches = approaches
        ids = itertools.count()
        self.v = SequenceValidator("inter-01", approaches, P, T0)
        self.fs = FailSafe(self.v, lease, T0, new_event_id=lambda: str(next(ids)))
        self.heartbeats = True
        self.instance = "ctrl-A"
        self.states = [(T0, self.v.phase, self.v.mode, self.v.reason)]
        self.notes = []
        self.seq = 0

    def step(self):
        self.now = round(self.now + 0.1, 3)
        if self.heartbeats and abs(self.now - round(self.now)) < 1e-6:
            self.seq += 1
            self.fs.on_heartbeat(hb(self.instance, self.seq, self.now), self.now)
        self.record(self.fs.tick(self.now), self.now)
        self.notes += self.fs.pop_notes()

    def record(self, orders, now):
        for o in orders:
            self.states.append((now, phase_from_dict(o["phase"], self.approaches), o["mode"], o["reason"]))

    def run(self, seconds):
        for _ in range(int(round(seconds * 10))):
            self.step()

    def command(self, kind, approach, eid, **kw):
        return self.fs.on_command(cmd(kind, approach, eid, self.approaches, **kw), self.now)

    def green_at(self, approach="acceso-01", t=2.0):
        """Lleva el semáforo (todo-rojo inicial) a verde(approach) en T0+t con latidos vivos."""
        self.run(t - (self.now - T0))
        if self.command(GREEN, approach, f"g-{approach}-{t}") != "changed":
            raise AssertionError("no se pudo preparar el verde")

    def failsafe_states(self):
        return [(round(t - T0, 1), ph) for t, ph, mode, _ in self.states if mode == FAILSAFE]

    def phase_changes(self):
        out = []
        for _, ph, _, _ in self.states:
            if not out or out[-1] != ph:
                out.append(ph)
        return out


class LeaseTests(unittest.TestCase):
    def test_sin_controlador_el_lease_de_arranque_vence(self):
        s = Light()
        s.heartbeats = False
        s.run(4.9)
        self.assertFalse(s.fs.active)
        s.run(0.2)
        self.assertTrue(s.fs.active)
        self.assertEqual((s.v.mode, s.v.reason), (FAILSAFE, "controller_lost"))

    def test_latidos_renuevan_el_lease(self):
        s = Light()
        s.run(60)
        self.assertFalse(s.fs.active)

    def test_comandos_renuevan_el_lease_sin_latidos(self):
        s = Light()
        s.heartbeats = False
        s.run(2)
        s.command(GREEN, "acceso-01", "a")
        s.run(4.5)
        s.command(GREEN, "acceso-01", "b")  # refresco: misma fase
        s.run(4.5)
        self.assertFalse(s.fs.active)
        s.run(0.6)
        self.assertTrue(s.fs.active)

    def test_reposo_sin_comandos_con_latidos_no_dispara_failsafe(self):
        s = Light()
        s.green_at()
        s.run(120)  # verde muy por encima de max_green, sin un solo comando
        self.assertFalse(s.fs.active)
        self.assertEqual(s.v.phase, (GREEN, "acceso-01"))

    def test_parametros_invalidos_se_rechazan(self):
        for kw in ({"lease_s": 1.5}, {"heartbeat_every_s": 0}, {"recover_lease_s": -1},
                   {"lease_s": 3, "heartbeat_every_s": 2}):
            with self.assertRaises(ValueError, msg=kw):
                LeaseParams(**kw)
        LeaseParams(lease_s=2, heartbeat_every_s=1)


class SafeSequenceTests(unittest.TestCase):
    def lose_controller(self, s, at):
        s.run(at - (s.now - T0))
        s.heartbeats = False

    def test_desde_verde_temprano_completa_max_green_desde_el_inicio(self):
        s = Light()
        s.green_at(t=2)
        self.lose_controller(s, at=4)  # último latido en T0+4: el lease vence en T0+9
        s.run(40)
        fs = s.failsafe_states()
        self.assertEqual(fs[0], (9.0, (GREEN, "acceso-01")))  # entra declarando failsafe sin cambiar la fase
        self.assertEqual(fs[1], (22.0, (YELLOW, "acceso-01")))  # verde desde T0+2 + max_green 20
        self.assertEqual(fs[2], (24.0, (ALL_RED, None)))
        self.assertEqual(fs[3], (26.0, (GREEN, "acceso-02")))
        self.assertEqual(fs[4], (36.0, (YELLOW, "acceso-02")))  # verde local = fixed_green 10

    def test_verde_pasado_de_max_green_pasa_enseguida_a_amarillo(self):
        s = Light()
        s.green_at(t=2)
        self.lose_controller(s, at=30)
        s.run(10)
        fs = s.failsafe_states()
        self.assertEqual(fs[0], (35.0, (GREEN, "acceso-01")))
        self.assertEqual(fs[1], (35.0, (YELLOW, "acceso-01")))  # en el mismo tick, nunca a rojo directo
        self.assertEqual(fs[2], (37.0, (ALL_RED, None)))

    def test_desde_amarillo_completa_la_secuencia(self):
        s = Light()
        s.green_at(t=2)
        s.run(5)
        self.assertEqual(s.command(YELLOW, "acceso-01", "y"), "changed")  # amarillo en T0+7
        self.lose_controller(s, at=7)
        s.run(15)
        fs = s.failsafe_states()
        # el lease vence en T0+12 con el amarillo (desde T0+7) ya cumplido: lo cierra el propio semáforo
        self.assertEqual([ph for _, ph in fs[:3]], [(YELLOW, "acceso-01"), (ALL_RED, None), (GREEN, "acceso-02")])
        self.assertEqual(fs[1][0], 12.0)
        self.assertEqual(fs[2][0], 14.0)

    def test_desde_todo_rojo_da_verde_al_siguiente_del_ultimo_verde(self):
        s = Light()
        s.green_at(t=2)
        s.run(5)
        s.command(YELLOW, "acceso-01", "y")
        s.run(2)
        self.assertEqual(s.command(ALL_RED, None, "r"), "changed")  # todo-rojo en T0+9
        self.lose_controller(s, at=9)
        s.run(10)
        fs = s.failsafe_states()
        self.assertEqual(fs[0], (14.0, (ALL_RED, None)))
        self.assertEqual(fs[1], (14.0, (GREEN, "acceso-02")))

    def test_sin_verde_previo_el_ciclo_local_empieza_por_el_primer_acceso(self):
        s = Light()
        s.heartbeats = False
        s.run(6)
        self.assertEqual(s.failsafe_states()[1], (5.0, (GREEN, "acceso-01")))

    def test_ciclo_local_alterna_accesos_y_nunca_va_de_verde_a_rojo(self):
        apps = ["acceso-01", "acceso-02", "acceso-03"]
        s = Light(approaches=apps)
        s.run(2)
        s.command(GREEN, "acceso-02", "g")
        s.heartbeats = False
        s.run(120)
        changes = s.phase_changes()
        for prev, new in zip(changes, changes[1:]):
            self.assertEqual(ALLOWED[prev[0]], new[0], f"{prev} -> {new}")
            if prev[0] == GREEN:
                self.assertEqual(new, (YELLOW, prev[1]))
        greens = [a for k, a in changes if k == GREEN]
        self.assertEqual(greens[:5], ["acceso-02", "acceso-03", "acceso-01", "acceso-02", "acceso-03"])

    def test_todo_estado_local_es_aceptado_por_un_validador_independiente(self):
        """Replay de los estados publicados como comandos sobre otro SequenceValidator (sin holgura)."""
        s = Light()
        s.green_at(t=2)
        self.lose_controller(s, at=6)
        s.run(90)
        replay = SequenceValidator("inter-01", APP, P, T0, tolerance_s=0.0)
        replay.apply(cmd(GREEN, "acceso-01", "g"), T0 + 2)
        for i, (t, ph, mode, reason) in enumerate(s.states[2:]):
            kind, app = ph
            replay.apply(cmd(kind, app, f"r{i}", mode=mode, reason=reason,
                             duration=P.max_green_s if kind == GREEN else None), t, modes=(FAILSAFE,))
        self.assertEqual(replay.phase, s.v.phase)

    def test_el_controlador_no_puede_ordenar_modo_failsafe(self):
        s = Light()
        s.run(2)
        with self.assertRaises(UnsafeCommand):
            s.command(GREEN, "acceso-01", "g", mode=FAILSAFE)


class FailsafeCommandsAndRecoveryTests(unittest.TestCase):
    def failsafe_in_green(self):
        s = Light()
        s.green_at(t=2)
        s.heartbeats = False
        s.run(30)  # lease vencido en T0+7; luego secuencia local
        self.assertTrue(s.fs.active)
        return s

    def test_en_failsafe_ignora_los_comandos(self):
        s = self.failsafe_in_green()
        phase, since = s.v.phase, s.v.since
        kind, app = phase
        nxt = YELLOW if kind == GREEN else GREEN
        self.assertEqual(s.command(nxt, app or "acceso-01", "x"), "ignored_failsafe")
        self.assertEqual((s.v.phase, s.v.since, s.v.mode), (phase, since, FAILSAFE))

    def test_sale_solo_tras_recover_lease_continuo_y_conserva_fase(self):
        s = self.failsafe_in_green()
        s.instance = "ctrl-B"
        s.heartbeats = True
        s.run(3.5)  # latidos en +1, +2, +3: abarcan 2 s
        self.assertTrue(s.fs.active)
        phase, since = s.v.phase, s.v.since
        s.run(1)  # latido en +4: 3 s desde el primero
        self.assertFalse(s.fs.active)
        self.assertEqual((s.v.phase, s.v.since), (phase, since))
        self.assertEqual((s.v.mode, s.v.reason), (ADAPTIVE, "controller_recovered"))
        self.assertIn("FAILSAFE terminado", " ".join(s.notes))

    def test_un_latido_aislado_no_alcanza_para_salir(self):
        s = self.failsafe_in_green()
        s.fs.on_heartbeat(hb("ctrl-B", 1, s.now), s.now)
        s.run(4.9)  # lease sano 4.9 s pero sin más mensajes
        self.assertTrue(s.fs.active)

    def test_el_cronometro_de_recuperacion_se_reinicia_si_el_lease_vuelve_a_vencer(self):
        s = self.failsafe_in_green()
        t0 = s.now
        s.fs.on_heartbeat(hb("ctrl-B", 1, s.now), s.now)
        s.run(2)
        s.fs.on_heartbeat(hb("ctrl-B", 2, s.now), s.now)  # +2 s: aún no
        s.run(5.5)  # vence de nuevo (sin mensajes 5 s)
        self.assertTrue(s.fs.active)
        s.heartbeats = True
        s.run(2.5)  # latidos nuevos: el cronómetro arranca de cero aunque desde t0 pasaron > 3 s
        self.assertTrue(s.fs.active, s.now - t0)
        s.run(1)
        self.assertFalse(s.fs.active)

    def test_tras_salir_valida_comandos_normalmente(self):
        s = self.failsafe_in_green()
        s.heartbeats = True
        s.run(4)
        self.assertFalse(s.fs.active)
        self.assertEqual(s.v.phase, (GREEN, "acceso-02"))  # verde local desde T0+26
        with self.assertRaises(UnsafeCommand):
            s.command(ALL_RED, None, "bad")  # verde -> rojo directo
        self.assertEqual(s.command(YELLOW, "acceso-02", "ok"), "changed")

    def test_comandos_en_failsafe_renuevan_el_lease_para_salir(self):
        s = self.failsafe_in_green()
        for i in range(4):
            s.fs.on_command(cmd(GREEN, "acceso-01", f"c{i}"), s.now)
            s.run(1)
        self.assertFalse(s.fs.active)


class StatusTests(unittest.TestCase):
    def test_offline_adelanta_el_failsafe(self):
        s = Light()
        s.green_at(t=2)
        s.run(1)
        s.heartbeats = False
        s.fs.on_controller_status(process_status_payload("inter-01", "offline", instance_id="ctrl-A"), s.now)
        s.step()
        self.assertTrue(s.fs.active)
        self.assertIn("offline", " ".join(s.notes))

    def test_offline_de_otra_instancia_no_afecta(self):
        s = Light()
        s.run(3)
        out = s.fs.on_controller_status(process_status_payload("inter-01", "offline", instance_id="viejo"), s.now)
        self.assertTrue(out.startswith("ignored"))
        s.run(10)
        self.assertFalse(s.fs.active)

    def test_offline_retenido_al_arrancar_sin_instancia_conocida_entra_en_failsafe(self):
        s = Light()
        s.heartbeats = False
        s.fs.on_controller_status({"v": 1, "status": "offline", "instance_id": "x"}, s.now)
        s.step()
        self.assertTrue(s.fs.active)

    def test_online_retenido_no_renueva_el_lease(self):
        s = Light()
        s.heartbeats = False
        for _ in range(6):
            s.fs.on_controller_status(process_status_payload("inter-01", "online", 0, instance_id="A"), s.now)
            s.run(1)
        self.assertTrue(s.fs.active)

    def test_instance_id_distinto_renueva_el_lease_y_avisa(self):
        s = Light()
        s.run(3)
        s.instance = "ctrl-B"
        s.run(10)
        self.assertFalse(s.fs.active)
        warnings = [n for n in s.notes if "dos instance_id" in n]
        self.assertEqual(len(warnings), 1)

    def test_latido_sin_instance_id_no_renueva(self):
        s = Light()
        s.heartbeats = False
        for _ in range(6):
            self.assertTrue(s.fs.on_heartbeat({"v": 1, "seq": 1}, s.now).startswith("ignored"))
            s.run(1)
        self.assertTrue(s.fs.active)


class ControllerSideTests(unittest.TestCase):
    def test_heartbeat_y_status_payloads(self):
        p = heartbeat_payload("abc", 7, T0, FIXED)
        self.assertEqual(set(p), {"v", "instance_id", "seq", "sent_at", "mode"})
        will = process_status_payload("inter-01", "offline", instance_id="abc")
        self.assertNotIn("sent_at", will)
        self.assertEqual(process_status_payload("inter-01", "online", T0, instance_id="abc")["status"], "online")

    def test_semaforo_offline_no_adopta_state_ni_emite_comandos_hasta_online(self):
        logic = ControllerLogic("inter-01", APP, P, T0, start_wait_s=0)
        self.assertEqual(logic.on_light_status({"status": "offline"}, T0), "offline")
        st = {"phase": {"acceso-01": "green", "acceso-02": "red"}, "event_id": "viejo"}
        self.assertTrue(logic.on_effective_state(st, T0).startswith("ignored"))
        self.assertIsNone(logic.phase)
        self.assertIsNone(logic.tick(T0 + 5))
        logic.on_light_status({"status": "online"}, T0 + 6)
        self.assertEqual(logic.on_effective_state({"phase": st["phase"], "event_id": "nuevo"}, T0 + 6),
                         "adopted green(acceso-01)")
        self.assertIn("semáforo offline", " ".join(logic.pop_notes()))

    def test_offline_olvida_la_fase_creida(self):
        logic = ControllerLogic("inter-01", APP, P, T0, start_wait_s=0)
        logic.on_effective_state({"phase": {"acceso-01": "green", "acceso-02": "red"}}, T0)
        logic.on_light_status({"status": "offline"}, T0 + 1)
        logic.on_light_status({"status": "online"}, T0 + 2)
        c = logic.tick(T0 + 2)
        self.assertEqual(phase_from_dict(c["phase"], APP), (ALL_RED, None))


class ControllerDiesTests(unittest.TestCase):
    """Controlador real (ControllerLogic) ordenando al semáforo con watchdog; muere en verde y vuelve."""

    def test_controlador_muere_en_verde_y_al_volver_retoma_sin_rechazos(self):
        ids = itertools.count()
        new_logic = lambda t: ControllerLogic("inter-01", APP, P, t, start_wait_s=2.0,  # noqa: E731
                                             new_event_id=lambda: f"c{next(ids)}")
        s = Light()
        logic = new_logic(T0)
        alive, rejected, now = True, [], T0
        for i in range(1, 1500):  # 150 s
            now = round(T0 + i * 0.1, 3)
            if i == 200:
                self.assertEqual(s.v.phase, (GREEN, "acceso-02"))  # verde desde T0+18
                alive = False  # muere (kill -9) sin `offline`; último latido en T0+19: el lease vence en T0+24
            if i == 700:
                alive, logic = True, new_logic(now)
                logic.on_effective_state(s.v.state_payload(now), now)  # state retenido
            if alive:
                if i % 10 == 0:
                    s.fs.on_heartbeat(hb("ctrl", i, now, logic.current_mode), now)
                c = logic.tick(now)
                if c:
                    try:
                        if s.fs.on_command(c, now) in ("changed", "refreshed"):
                            s.record([c], now)
                    except UnsafeCommand as e:
                        rejected.append((round(now - T0, 1), str(e)))
                    logic.on_effective_state(s.v.state_payload(now), now)
            s.now = now
            orders = s.fs.tick(now)
            s.record(orders, now)
            if orders and alive:
                logic.on_effective_state(s.v.state_payload(now), now)
        local = [(round(t - T0, 1), ph) for t, ph, m, _ in s.states if m == FAILSAFE]
        self.assertEqual(local[:4], [(24.0, (GREEN, "acceso-02")), (38.0, (YELLOW, "acceso-02")),
                                     (40.0, (ALL_RED, None)), (42.0, (GREEN, "acceso-01"))])
        self.assertFalse(s.fs.active)
        self.assertNotEqual(s.v.mode, FAILSAFE)
        self.assertIn((FIXED, "controller_recovered"), [(m, r) for _, _, m, r in s.states])
        self.assertEqual(rejected, [])
        changes = s.phase_changes()
        for prev, new in zip(changes, changes[1:]):
            self.assertEqual(ALLOWED[prev[0]], new[0], f"{prev} -> {new}")


if __name__ == "__main__":
    unittest.main()
