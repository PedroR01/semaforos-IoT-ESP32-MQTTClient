import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from traffic_logic import (ADAPTIVE, ALL_RED, FIXED, GREEN, YELLOW, ControllerLogic, Params,  # noqa: E402
                           SequenceValidator, UnsafeCommand, phase_from_dict, utc_iso)

APP = ["acceso-01", "acceso-02"]
P = Params()
T0 = 1_700_000_000.0


def det(approach, seq, count, now, session="s1", status="ok"):
    p = {"v": 1, "approach_id": approach, "camera_id": "cam", "session_id": session,
         "seq": seq, "processed_at": utc_iso(now), "status": status}
    if status == "ok":
        p["metrics"] = {"visible_count": count}
    return p


def will(approach, session="s1"):
    return {"v": 1, "approach_id": approach, "camera_id": "cam", "session_id": session,
            "status": "unavailable"}


def adaptive_logic(params=P):
    """Lógica con ambos accesos publicando ok (count=3) 1 Hz durante 10 s: ya en ADAPTIVE; último ok en T0+10."""
    logic = ControllerLogic("inter-01", APP, params, T0)
    for t in range(11):
        for a in APP:
            logic.on_detection(det(a, t + 1, 3, T0 + t), T0 + t)
        logic.mode(T0 + t)
    assert logic.mode(T0 + 10) == ADAPTIVE
    return logic


class Sim:
    """Avanza el reloj de a 0.1 s alimentando conteos fijos; recoge los comandos.

    La espera inicial (4.1 s) deja que el modo llegue a ADAPTIVE (datos desde t=1 s + recover_after 3 s)
    antes del primer comando, como en un arranque con detectores ya publicando."""

    def __init__(self, counts=(0, 0), approaches=APP, params=P):
        self.now = T0
        self.counts = list(counts)
        self.approaches = approaches
        self.feed = True
        self.down = set()   # accesos que publican `unavailable` en vez de `ok`
        self.mute = set()   # accesos en silencio (no publican nada)
        self.seq = 0
        ids = itertools.count()
        self.logic = ControllerLogic("inter-01", approaches, params, T0, start_wait_s=4.1,
                                     new_event_id=lambda: str(next(ids)))
        self.cmds = []
        self.notes = []

    def run(self, seconds):
        for _ in range(int(round(seconds * 10))):
            self.now = round(self.now + 0.1, 3)
            if self.feed and abs(self.now - round(self.now)) < 1e-6:  # 1 Hz
                self.seq += 1
                for a, c in zip(self.approaches, self.counts):
                    if a not in self.mute:
                        status = "unavailable" if a in self.down else "ok"
                        self.logic.on_detection(det(a, self.seq, c, self.now, status=status), self.now)
            cmd = self.logic.tick(self.now)
            self.notes += self.logic.pop_notes()
            if cmd:
                self.cmds.append((self.now, cmd))
                self.logic.on_effective_state({"phase": cmd["phase"], "event_id": cmd["event_id"]}, self.now)

    def phases(self):
        return [(round(t - T0, 1), phase_from_dict(c["phase"], self.approaches), c["reason"], c["mode"])
                for t, c in self.cmds]


class PolicyTests(unittest.TestCase):
    def settle(self, counts, seconds=9):
        s = Sim(counts)
        s.run(seconds)  # arranque: todo-rojo y luego verde inicial
        return s

    def test_arranque_pasa_por_todo_rojo_antes_del_primer_verde(self):
        s = self.settle((0, 0))
        kinds = [p[1][0] for p in s.phases()]
        self.assertEqual(kinds[:2], [ALL_RED, GREEN])

    def test_gana_el_acceso_con_mayor_demanda(self):
        s = Sim((0, 6))
        s.run(9)
        greens = [p for p in s.phases() if p[1][0] == GREEN]
        self.assertEqual(greens[0][1][1], "acceso-02")  # el primer verde va al de mayor demanda

    def test_cambia_por_demanda_tras_el_verde_minimo_no_antes(self):
        s = Sim((0, 0))
        s.run(9)
        first = [p for p in s.phases() if p[1][0] == GREEN][0]
        holder = first[1][1]
        other_idx = 1 - APP.index(holder)
        s.counts[other_idx] = 8
        s.run(15)
        yellow = [p for p in s.phases() if p[1][0] == YELLOW][0]
        self.assertEqual(yellow[2], "demand")
        self.assertGreaterEqual(yellow[0] - first[0], P.min_green_s - 1e-6)

    def test_ciclo_completo_tiene_amarillo_y_todo_rojo(self):
        s = Sim((5, 0))
        s.run(20)
        s.counts = [0, 5]
        s.run(60)
        seq = [p[1][0] for p in s.phases()]
        for a, b in zip(seq, seq[1:]):
            self.assertIn((a, b), {(ALL_RED, GREEN), (GREEN, YELLOW), (YELLOW, ALL_RED)})
        self.assertTrue(seq.count(YELLOW) >= 1)

    def test_amarillo_y_todo_rojo_duran_lo_configurado(self):
        s = Sim((0, 0))
        s.run(40)
        ph = s.phases()
        for (t1, p1, *_), (t2, *_) in zip(ph, ph[1:]):
            if p1[0] == YELLOW:
                self.assertAlmostEqual(t2 - t1, P.yellow_s, delta=0.25)
            if p1[0] == ALL_RED:
                self.assertAlmostEqual(t2 - t1, P.all_red_s, delta=0.25)

    def test_verde_maximo_corta_aunque_siga_la_demanda(self):
        s = Sim((9, 3))
        s.run(60)
        ph = s.phases()
        first_green = next(p for p in ph if p[1][0] == GREEN)
        first_yellow = next(p for p in ph if p[1][0] == YELLOW)
        self.assertEqual(first_yellow[2], "max_green")
        self.assertAlmostEqual(first_yellow[0] - first_green[0], P.max_green_s, delta=0.25)
        self.assertEqual(first_yellow[3], ADAPTIVE)

    def test_empate_no_cambia_de_verde(self):
        s = Sim((4, 4))
        s.run(15)
        self.assertEqual([p[1][0] for p in s.phases()], [ALL_RED, GREEN])

    def test_ceros_no_cambia_antes_del_maximo_y_extiende_el_verde(self):
        s = Sim((0, 0))
        s.run(35)  # supera el verde máximo sin nadie esperando
        self.assertEqual([p[1][0] for p in s.phases()], [ALL_RED, GREEN])

    def test_demanda_suavizada_amortigua_un_pico(self):
        logic = ControllerLogic("inter-01", APP, P, T0)
        for i, c in enumerate([0, 0, 0, 10]):
            logic.on_detection(det("acceso-01", i + 1, c, T0 + i), T0 + i)
        self.assertAlmostEqual(logic.demand_of("acceso-01"), 3.0)  # 0.3 * 10

    def test_un_solo_acceso_nunca_cambia(self):
        s = Sim((3,), approaches=["acceso-01"])
        s.run(40)
        self.assertEqual([p[1][0] for p in s.phases()], [ALL_RED, GREEN])


class FreshnessTests(unittest.TestCase):
    def test_sin_dato_de_un_acceso_usa_ciclo_fijo_declarado(self):
        s = Sim((5, 5))
        s.feed = False
        s.run(35)
        ph = s.phases()
        self.assertTrue(all(p[3] == FIXED and p[2] == "fixed_cycle_no_data" for p in ph))
        greens = [p for p in ph if p[1][0] == GREEN]
        self.assertEqual([g[1][1] for g in greens[:2]], ["acceso-01", "acceso-02"])
        self.assertAlmostEqual(greens[1][0] - greens[0][0], P.fixed_green_s + P.yellow_s + P.all_red_s, delta=0.3)
        self.assertEqual(greens[0][2], "fixed_cycle_no_data")

    def test_dato_viejo_vence_tras_T_pero_el_modo_espera_fail_after(self):
        logic = adaptive_logic()  # último ok en T0+10
        fresh = logic.data["acceso-01"]
        self.assertTrue(fresh.is_fresh_ok(T0 + 10 + P.fresh_s, P.fresh_s))
        self.assertFalse(fresh.is_fresh_ok(T0 + 10 + P.fresh_s + 0.1, P.fresh_s))
        self.assertEqual(logic.mode(T0 + 10 + P.fresh_s + 1), ADAPTIVE)
        self.assertEqual(logic.mode(T0 + 10 + P.fail_after_s), FIXED)

    def test_unavailable_sostenido_de_un_acceso_fuerza_ciclo_fijo(self):
        logic = adaptive_logic()
        logic.on_detection(det("acceso-02", 99, 0, T0 + 1, status="unavailable"), T0 + 1)
        self.assertEqual(logic.mode(T0 + 1 + P.fail_after_s - 1), ADAPTIVE)
        self.assertEqual(logic.mode(T0 + 20), FIXED)  # último ok en T0+10 -> 10 s sin ok

    def test_ok_sin_processed_at_se_ignora(self):
        logic = ControllerLogic("inter-01", APP, P, T0)
        bad = det("acceso-01", 1, 3, T0)
        del bad["processed_at"]
        self.assertTrue(logic.on_detection(bad, T0).startswith("ignored"))
        self.assertEqual(logic.mode(T0), FIXED)

    def test_cambio_a_ciclo_fijo_en_pleno_verde_se_declara(self):
        s = Sim((3, 3))
        s.run(8)
        n = len(s.cmds)
        s.feed = False
        s.run(P.fail_after_s + 1)
        extra = s.phases()[n:]
        self.assertTrue(extra and extra[0][3] == FIXED and extra[0][2] == "fixed_cycle_no_data")

    def test_recuperacion_vuelve_a_adaptativo_y_lo_declara(self):
        s = Sim((3, 3))
        s.feed = False
        s.run(15)
        self.assertEqual(s.logic.mode(s.now), FIXED)
        s.feed = True
        s.run(P.recover_after_s + 1)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        self.assertEqual(s.phases()[-1][3], ADAPTIVE)
        s.counts = [0, 9]
        s.run(30)
        self.assertEqual(s.phases()[-1][3], ADAPTIVE)

    def test_la_demanda_se_reinicia_tras_un_hueco(self):
        logic = ControllerLogic("inter-01", APP, P, T0)
        logic.on_detection(det("acceso-01", 1, 10, T0), T0)
        logic.on_detection(det("acceso-01", 2, 0, T0 + 30), T0 + 30)
        self.assertEqual(logic.demand_of("acceso-01"), 0.0)


class DedupeTests(unittest.TestCase):
    def setUp(self):
        self.logic = ControllerLogic("inter-01", APP, P, T0)

    def test_duplicado_y_fuera_de_orden_se_descartan(self):
        self.assertEqual(self.logic.on_detection(det("acceso-01", 5, 2, T0), T0), "accepted")
        self.assertTrue(self.logic.on_detection(det("acceso-01", 5, 9, T0), T0).startswith("ignored"))
        self.assertTrue(self.logic.on_detection(det("acceso-01", 4, 9, T0), T0).startswith("ignored"))
        self.assertEqual(self.logic.demand_of("acceso-01"), 2.0)

    def test_nueva_sesion_reinicia_el_orden(self):
        self.logic.on_detection(det("acceso-01", 50, 2, T0), T0)
        self.assertEqual(self.logic.on_detection(det("acceso-01", 1, 2, T0 + 1, session="s2"), T0 + 1), "accepted")

    def test_unavailable_sin_seq_se_acepta_y_marca_sin_dato(self):
        for a in APP:
            self.logic.on_detection(det(a, 1, 3, T0), T0)
        self.assertEqual(self.logic.on_detection(will("acceso-01"), T0 + 1), "accepted")
        self.assertEqual(self.logic.data["acceso-01"].status, "unavailable")
        # no toca el orden: un ok con seq mayor se acepta; uno con seq menor o igual no
        self.assertTrue(self.logic.on_detection(det("acceso-01", 1, 3, T0 + 2), T0 + 2).startswith("ignored"))
        self.assertEqual(self.logic.on_detection(det("acceso-01", 2, 3, T0 + 2), T0 + 2), "accepted")
        self.assertEqual(self.logic.data["acceso-01"].status, "ok")

    def test_will_repetido_no_se_descarta_como_duplicado(self):
        self.assertEqual(self.logic.on_detection(will("acceso-01"), T0), "accepted")
        self.assertEqual(self.logic.on_detection(will("acceso-01"), T0 + 1), "accepted")

    def test_will_de_sesion_anterior_no_pisa_la_sesion_nueva(self):
        self.logic.on_detection(det("acceso-01", 1, 3, T0, session="nueva"), T0)
        self.assertTrue(self.logic.on_detection(will("acceso-01", session="vieja"), T0).startswith("ignored"))
        self.assertEqual(self.logic.data["acceso-01"].status, "ok")

    def test_acceso_desconocido_se_ignora(self):
        self.assertTrue(self.logic.on_detection(det("acceso-99", 1, 3, T0), T0).startswith("ignored"))


class ResyncTests(unittest.TestCase):
    def test_adopta_el_state_retenido_al_arrancar(self):
        logic = ControllerLogic("inter-01", APP, P, T0)
        out = logic.on_effective_state({"phase": {"acceso-01": "red", "acceso-02": "green"}, "event_id": "x"}, T0)
        self.assertTrue(out.startswith("adopted"))
        self.assertEqual(logic.phase, (GREEN, "acceso-02"))

    def test_state_inventado_con_dos_verdes_se_ignora(self):
        logic = ControllerLogic("inter-01", APP, P, T0)
        out = logic.on_effective_state({"phase": {"acceso-01": "green", "acceso-02": "green"}}, T0)
        self.assertTrue(out.startswith("ignored"))
        self.assertIsNone(logic.phase)


def cmd(phase, duration, eid, mode="adaptive", reason="demand", inter="inter-01"):
    return {"v": 1, "event_id": eid, "intersection_id": inter, "issued_at": "x",
            "phase": phase, "duration_s": duration, "reason": reason, "mode": mode}


G1 = {"acceso-01": "green", "acceso-02": "red"}
G2 = {"acceso-01": "red", "acceso-02": "green"}
Y1 = {"acceso-01": "yellow", "acceso-02": "red"}
RR = {"acceso-01": "red", "acceso-02": "red"}


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.v = SequenceValidator("inter-01", APP, P, T0)

    def go_green(self):
        self.assertEqual(self.v.apply(cmd(G1, 5, "a"), T0 + 2), "changed")

    def test_secuencia_segura_completa(self):
        self.go_green()
        self.assertEqual(self.v.apply(cmd(Y1, 2, "b"), T0 + 7), "changed")
        self.assertEqual(self.v.apply(cmd(RR, 2, "c"), T0 + 9), "changed")
        self.assertEqual(self.v.apply(cmd(G2, 5, "d"), T0 + 11), "changed")
        self.assertEqual(self.v.phase, (GREEN, "acceso-02"))

    def test_rechaza_dos_verdes(self):
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd({"acceso-01": "green", "acceso-02": "green"}, 5, "a"), T0 + 5)
        self.assertEqual(self.v.phase, (ALL_RED, None))

    def test_rechaza_verde_a_verde_sin_todo_rojo(self):
        self.go_green()
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd(G2, 5, "b"), T0 + 20)
        self.assertEqual(self.v.phase, (GREEN, "acceso-01"))

    def test_rechaza_verde_a_todo_rojo_saltando_amarillo(self):
        self.go_green()
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd(RR, 2, "b"), T0 + 20)

    def test_rechaza_cortar_verde_antes_del_minimo(self):
        self.go_green()
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd(Y1, 2, "b"), T0 + 2 + 3)

    def test_rechaza_duracion_menor_al_minimo(self):
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd(G1, 1, "a"), T0 + 5)

    def test_rechaza_verde_antes_de_completar_todo_rojo_inicial(self):
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd(G1, 5, "a"), T0 + 0.5)

    def test_rechaza_intersection_incorrecta_y_phase_incompleta(self):
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd(G1, 5, "a", inter="otra"), T0 + 5)
        with self.assertRaises(UnsafeCommand):
            self.v.apply(cmd({"acceso-01": "green"}, 5, "b"), T0 + 5)

    def test_event_id_repetido_es_duplicado_y_misma_fase_refresca(self):
        self.go_green()
        self.assertEqual(self.v.apply(cmd(G1, 5, "a"), T0 + 3), "duplicate")
        self.assertEqual(self.v.apply(cmd(G1, 10, "b", mode="fixed", reason="fixed_cycle_no_data"), T0 + 3),
                         "refreshed")
        self.assertEqual(self.v.mode, "fixed")
        self.assertEqual(self.v.since, T0 + 2)

    def test_state_payload_refleja_la_fase_efectiva(self):
        self.go_green()
        st = self.v.state_payload(T0 + 2)
        self.assertEqual(st["phase"], G1)
        self.assertEqual(st["event_id"], "a")


class ControllerValidatorIntegrationTests(unittest.TestCase):
    """Todo comando que emite la política debe ser aceptado por el validador, con y sin datos."""

    def test_comandos_de_la_politica_son_aceptados(self):
        for feed in (True, False):
            s = Sim((6, 0))
            s.feed = feed
            v = SequenceValidator("inter-01", APP, P, T0)
            for i in range(6):
                s.run(10)
                s.counts = list(reversed(s.counts))
            for t, c in s.cmds:
                v.apply(c, t)  # UnsafeCommand haría fallar el test


def validate(sim, approaches=APP, params=P):
    """Pasa todos los comandos del escenario por el validador del semáforo (UnsafeCommand hace fallar)."""
    v = SequenceValidator("inter-01", approaches, params, T0)
    for t, c in sim.cmds:
        v.apply(c, t)


def mode_notes(sim):
    return [n for n in sim.notes if n.startswith("MODO")]


def modes(sim):
    return [(round(t - T0, 1), c["mode"], c["reason"]) for t, c in sim.cmds]


def green_changes(sim, reason=None):
    """Comandos que sacan al verde actual (verde -> amarillo)."""
    return [(round(t - T0, 1), c["reason"]) for t, c in sim.cmds
            if "yellow" in c["phase"].values() and (reason is None or c["reason"] == reason)]


class DemandPolicyTests(unittest.TestCase):
    """Corrección 2026-11-12, problema 1: residuo de la EMA, margen y reposo."""

    def test_residuo_de_ema_no_alterna_el_verde_para_siempre(self):
        # Escenario reportado: acceso-01 con 5 durante 10 s y luego 0; acceso-02 con 2 constante; 120 s.
        s = Sim((5, 2))
        s.run(10)
        s.counts = [0, 2]
        s.run(110)
        to_02 = [p for p in s.phases() if p[1] == (GREEN, "acceso-02")]
        self.assertEqual(len(to_02), 1)
        # tras el primer cambio hacia acceso-02 no hay más comandos de fase
        self.assertEqual(s.phases()[-1][1], (GREEN, "acceso-02"))
        self.assertGreater(s.now - s.cmds[-1][0], P.max_green_s)  # verde mantenido más allá del máximo
        self.assertLess(s.logic.demand_of("acceso-01"), P.demand_present)
        self.assertTrue(s.logic.resting or s.logic.demand_of("acceso-02") >= P.demand_present)
        validate(s)

    def test_destello_fantasma_aislado_no_cambia_el_verde(self):
        s = Sim((0, 0))
        s.run(12)
        holder = s.phases()[-1][1]
        n = len(s.cmds)
        ghost = 1 - APP.index(holder[1])
        s.counts[ghost] = 1
        s.run(1)
        s.counts[ghost] = 0
        s.run(60)
        self.assertEqual(len(s.cmds), n)

    def test_margen_menor_no_cambia_y_mayor_si(self):
        for other, expect_change in ((2.3, False), (2.7, True)):
            s = Sim((2, 2))  # acceso-01 verde con demanda 2.0 (EMA estable); otro con `other`
            s.run(9)
            holder = s.phases()[-1][1][1]
            s.counts[1 - APP.index(holder)] = other
            n = len(s.cmds)
            s.run(10)  # la EMA del otro llega a ~other; margen 0.5 sobre 2.0
            self.assertEqual(len(s.cmds) > n and s.phases()[n][3] == ADAPTIVE and s.phases()[n][2] == "demand",
                             expect_change, other)

    def test_reposo_mantiene_verde_sin_comandos_y_sale_con_demanda(self):
        s = Sim((0, 0))
        s.run(9)
        n = len(s.cmds)
        s.run(90)
        self.assertEqual(len(s.cmds), n)  # >60 s sin comandos
        self.assertTrue(s.logic.resting)
        holder = s.phases()[-1][1][1]
        other = 1 - APP.index(holder)
        s.counts[other] = 4  # demanda >= umbral en el otro acceso
        t_demand = s.now
        s.run(15)
        self.assertFalse(s.logic.resting)
        leave = green_changes(s)[0][0] + T0  # el verde (ya pasado del máximo) se cede enseguida
        self.assertLess(leave - t_demand, 2.0)
        validate(s)

    def test_reposo_se_registra_una_vez_por_entrada(self):
        s = Sim((0, 0))
        s.run(60)
        self.assertEqual(sum(n.startswith("reposo: sin demanda, se mantiene") for n in s.notes), 1)
        self.assertEqual(sum(n == "reposo terminado" for n in s.notes), 0)
        s.counts = [4, 0]
        s.run(40)
        s.counts = [0, 0]
        s.run(80)
        starts = sum(n.startswith("reposo: sin demanda") for n in s.notes)
        ends = sum(n == "reposo terminado" for n in s.notes)
        self.assertEqual(starts, 2)
        self.assertEqual(ends, 1)
        self.assertTrue(s.logic.resting)

    def test_verde_maximo_solo_rota_si_el_otro_tiene_demanda_presente(self):
        s = Sim((2, 0))  # acceso-02 vacío: el verde de acceso-01 supera el máximo sin cambiar
        s.run(60)
        self.assertEqual(green_changes(s, "max_green"), [])
        s.counts = [2, 1]
        s.run(30)
        self.assertTrue(green_changes(s, "max_green") or green_changes(s, "demand"))
        validate(s)

    def test_parametros_invalidos_se_rechazan(self):
        for kw in ({"demand_present": 0}, {"switch_margin": -1}, {"fail_after_s": 1.0}, {"recover_after_s": -1}):
            with self.assertRaises(ValueError):
                Params(**kw)


class HysteresisTests(unittest.TestCase):
    """Corrección 2026-11-12, problema 2: histéresis del modo y periodo de gracia."""

    def adaptive_sim(self, counts=(3, 3)):
        s = Sim(counts)
        s.run(9)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        return s

    def test_arranque_sin_datos_es_fijo(self):
        s = Sim((0, 0))
        s.feed = False
        s.run(15)
        self.assertEqual(s.logic.mode(s.now), FIXED)
        self.assertEqual({m for _, m, _ in modes(s)}, {FIXED})

    def test_unavailable_aislado_no_cambia_el_modo(self):
        s = self.adaptive_sim()
        notes = len(mode_notes(s))
        s.down = {"acceso-02"}
        s.run(2)
        s.down = set()
        s.run(20)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        self.assertEqual(len(mode_notes(s)), notes)
        self.assertNotIn(FIXED, {m for _, m, _ in modes(s)})
        validate(s)

    def test_silencio_mayor_a_T_pero_menor_a_fail_after_no_cambia_el_modo(self):
        s = self.adaptive_sim()
        notes = len(mode_notes(s))
        s.mute = {"acceso-01"}
        s.run(6)  # >T=5 s
        s.mute = set()
        s.run(10)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        self.assertEqual(len(mode_notes(s)), notes)
        self.assertNotIn(FIXED, {m for _, m, _ in modes(s)})

    def test_silencio_de_fail_after_pasa_a_fijo_con_comando_y_log(self):
        s = self.adaptive_sim()
        n = len(s.cmds)
        last_ok = s.now
        s.mute = {"acceso-02"}
        s.run(P.fail_after_s + 1)
        sent = modes(s)[n:]
        self.assertEqual(sent[0][1:], (FIXED, "fixed_cycle_no_data"))
        self.assertGreaterEqual(sent[0][0] + 0.0, round(last_ok - T0 + P.fail_after_s - 1.0, 1))
        note = [x for x in s.notes if x.startswith("MODO adaptativo -> fijo: acceso-02 sin ok hace")]
        self.assertEqual(len(note), 1)
        validate(s)

    def test_unavailable_sostenido_pasa_a_fijo(self):
        s = self.adaptive_sim()
        s.down = {"acceso-01"}
        s.run(P.fail_after_s + 2)
        self.assertEqual(s.logic.mode(s.now), FIXED)

    def test_recuperar_exige_recover_after_seguidos(self):
        s = self.adaptive_sim()
        s.mute = {"acceso-02"}
        s.run(P.fail_after_s + 1)
        self.assertEqual(s.logic.mode(s.now), FIXED)
        # alternar ok / unavailable cada 2 s: nunca hay 3 s seguidos de ok vigente
        for _ in range(10):
            s.mute, s.down = set(), set()
            s.run(2)
            s.down = {"acceso-02"}
            s.run(2)
        self.assertEqual(s.logic.mode(s.now), FIXED)
        s.down = set()
        s.run(P.recover_after_s + 1)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        self.assertEqual(modes(s)[-1][1:], (ADAPTIVE, "data_recovered"))
        self.assertTrue(any(n.startswith("MODO fijo -> adaptativo: datos ok continuos") for n in s.notes))
        validate(s)

    def test_flapping_ok_3s_falta_2s_durante_60s_no_cambia_de_modo(self):
        s = self.adaptive_sim()
        notes = len(mode_notes(s))
        for _ in range(12):
            s.down = set()
            s.run(3)
            s.down = {"acceso-02"}
            s.run(2)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        self.assertEqual(len(mode_notes(s)), notes)
        self.assertNotIn(FIXED, {m for _, m, _ in modes(s)})
        validate(s)

    def test_gracia_no_decide_por_demanda_con_dato_vencido_y_respeta_max_green(self):
        s = self.adaptive_sim((3, 0))
        holder = s.phases()[-1][1][1]
        other = APP[1 - APP.index(holder)]
        n, notes = len(s.cmds), len(mode_notes(s))
        # el otro acceso tiene demanda alta pero envía unavailable (vencido): no decide ni vale cero
        s.counts[1 - APP.index(holder)] = 9
        s.down = {other}
        s.run(P.fail_after_s - 3)  # dentro de la gracia, antes del verde máximo
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        self.assertEqual(len(s.cmds), n)  # sin cambio por demanda
        s.down = set()  # el dato vuelve dentro de la gracia: sigue adaptativo, sin comandos de modo
        s.run(2)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        self.assertEqual(len(mode_notes(s)), notes)
        self.assertNotIn(FIXED, {m for _, m, _ in modes(s)})

    def test_gracia_en_max_green_con_modo_aun_adaptativo(self):
        # fail_after grande: el dato vencido sigue en gracia cuando se cumple el verde máximo
        params = Params(fail_after_s=60.0)
        s = Sim((3, 3), params=params)
        s.run(9)
        holder = s.phases()[-1][1][1]
        other = APP[1 - APP.index(holder)]
        s.mute = {other}
        s.counts = [3, 3]
        s.run(30)
        self.assertEqual(s.logic.mode(s.now), ADAPTIVE)
        rotations = [p for p in s.phases() if p[1][0] == YELLOW]
        self.assertTrue(rotations and rotations[0][2] == "max_green")
        self.assertEqual(s.phases()[-1][1][0] in (GREEN, YELLOW, ALL_RED), True)
        greens = [p[1][1] for p in s.phases() if p[1][0] == GREEN]
        self.assertEqual(greens[-1], other)  # rotó al siguiente cíclico aunque su dato esté vencido
        validate(s, params=params)

    def test_todos_los_comandos_de_los_escenarios_son_aceptados(self):
        s = Sim((5, 2))
        s.run(10)
        s.counts = [0, 2]
        s.run(30)
        s.mute = {"acceso-01"}
        s.run(30)
        s.mute, s.down = set(), {"acceso-02"}
        s.run(15)
        s.down = set()
        s.run(40)
        validate(s)


class IgnoredLogTests(unittest.TestCase):
    def test_primera_ocurrencia_y_luego_resumen_cada_10s(self):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from traffic_controller import IgnoredLog
        lg = IgnoredLog()
        out = [lg.note("acceso-01", f"ignored: duplicado o fuera de orden (seq {i} <= 9)", float(i)) for i in range(25)]
        self.assertIn("ignored", out[0])
        self.assertEqual([i for i, o in enumerate(out) if o], [0, 10, 20])
        self.assertIn("x10", out[10])
        self.assertIsNotNone(lg.note("acceso-02", "ignored: ok sin seq", 25.0))  # otra clave: primera vez


if __name__ == "__main__":
    unittest.main()
