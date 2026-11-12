"""Lógica pura de M2 (sin MQTT ni reloj propio): política del controlador y validador del semáforo.

Contrato: protocol/mqtt/README.md §2. Brief: docs/reference.md §14.
Todo método que depende del tiempo recibe `now` (segundos epoch) para poder probarlo sin esperar.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

TOPIC_ROOT = "trafico/v1"
PAYLOAD_VERSION = 1

GREEN, YELLOW, ALL_RED = "green", "yellow", "all_red"
LIGHT_VALUES = ("green", "yellow", "red")
ADAPTIVE, FIXED = "adaptive", "fixed"
REASON_FIXED = "fixed_cycle_no_data"


@dataclass(frozen=True)
class Params:
    """Valores confirmados el 2026-11-12 (docs/reference.md §14)."""
    yellow_s: float = 2.0
    all_red_s: float = 2.0
    min_green_s: float = 5.0
    max_green_s: float = 20.0
    fresh_s: float = 5.0          # T: vigencia de un dato `ok`
    fixed_green_s: float = 10.0   # ciclo base de respaldo, verde por acceso
    ema_alpha: float = 0.3        # peso de la muestra nueva en la media móvil exponencial
    demand_present: float = 0.5   # vehículos suavizados desde los que un acceso "tiene demanda"
    switch_margin: float = 0.5    # ventaja mínima sobre el verde actual para cambiar por demanda
    fail_after_s: float = 10.0    # sin `ok` nuevo durante este tiempo (desde el último) -> ciclo fijo
    recover_after_s: float = 3.0  # todos con `ok` vigente durante este tiempo seguido -> adaptativo

    def __post_init__(self):
        if not (0 < self.ema_alpha <= 1):
            raise ValueError("ema_alpha debe estar en (0, 1]")
        if not (0 < self.min_green_s <= self.fixed_green_s and self.min_green_s <= self.max_green_s):
            raise ValueError("se exige 0 < min_green <= fixed_green y min_green <= max_green")
        if self.demand_present <= 0 or self.switch_margin < 0:
            raise ValueError("se exige demand_present > 0 y switch_margin >= 0")
        if self.fail_after_s < self.fresh_s or self.recover_after_s < 0:
            raise ValueError("se exige fail_after >= fresh (T) y recover_after >= 0")


Phase = tuple  # (GREEN|YELLOW|ALL_RED, approach_id | None)


def utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text) -> float | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def commands_topic(intersection_id: str, root: str = TOPIC_ROOT) -> str:
    return f"{root}/{intersection_id}/commands"


def state_topic(intersection_id: str, root: str = TOPIC_ROOT) -> str:
    return f"{root}/{intersection_id}/state"


def phase_to_dict(phase: Phase, approaches) -> dict:
    kind, approach = phase
    if kind == ALL_RED:
        return {a: "red" for a in approaches}
    return {a: (kind if a == approach else "red") for a in approaches}


def phase_from_dict(phase: dict, approaches) -> Phase:
    """Convierte `approach_id -> luz` en una fase segura; ValueError con el motivo si no lo es."""
    if not isinstance(phase, dict) or set(phase) != set(approaches):
        raise ValueError(f"phase debe tener exactamente los accesos {sorted(approaches)}")
    if any(v not in LIGHT_VALUES for v in phase.values()):
        raise ValueError("valores de luz permitidos: green, yellow, red")
    greens = [a for a, v in phase.items() if v == "green"]
    yellows = [a for a, v in phase.items() if v == "yellow"]
    if len(greens) > 1:
        raise ValueError(f"dos o más verdes a la vez: {sorted(greens)}")
    if greens and yellows:
        raise ValueError("verde y amarillo a la vez")
    if len(yellows) > 1:
        raise ValueError(f"dos o más amarillos a la vez: {sorted(yellows)}")
    if greens:
        return (GREEN, greens[0])
    if yellows:
        return (YELLOW, yellows[0])
    return (ALL_RED, None)


def phase_label(phase: Phase) -> str:
    kind, approach = phase
    return kind if approach is None else f"{kind}({approach})"


def min_duration(kind: str, params: Params) -> float:
    return {GREEN: params.min_green_s, YELLOW: params.yellow_s, ALL_RED: params.all_red_s}[kind]


# ---------------------------------------------------------------- controlador

@dataclass
class ApproachData:
    session_id: str
    last_seq: int | None
    status: str
    processed_at: float | None
    demand: float | None  # media móvil exponencial de visible_count

    def is_fresh_ok(self, now: float, fresh_s: float) -> bool:
        return (self.status == "ok" and self.processed_at is not None
                and now - self.processed_at <= fresh_s)


class ControllerLogic:
    """Política del controlador: recibe detecciones y estado del semáforo, emite comandos en `tick`.

    Secuencia: verde(X) -> amarillo(X) -> todo-rojo -> verde(Y). El verde dura al menos `min_green_s`
    y como máximo `max_green_s`. Modo con histéresis: arranca en FIXED; pasa a ADAPTIVE cuando todos los
    accesos llevan `recover_after_s` con `ok` vigente, y vuelve a FIXED cuando algún acceso lleva
    `fail_after_s` sin `ok` (medido desde el `processed_at` de su último `ok`). En FIXED la intersección usa
    el ciclo fijo (`fixed_green_s` por acceso, en orden) con `reason=fixed_cycle_no_data`. En ADAPTIVE con
    algún dato vencido (gracia) se mantiene el verde, sin decidir por demanda, hasta `max_green_s`.
    Sin demanda en ningún acceso (reposo) el verde actual se mantiene indefinidamente.
    """

    def __init__(self, intersection_id: str, approaches, params: Params, now: float,
                 start_wait_s: float = 2.0, new_event_id=lambda: uuid.uuid4().hex):
        self.intersection_id = intersection_id
        self.approaches = list(approaches)
        self.params = params
        self.start_wait_s = start_wait_s  # espera inicial por el `state` retenido del semáforo
        self._new_event_id = new_event_id
        self._created = now
        self.data: dict[str, ApproachData] = {}
        self.phase: Phase | None = None
        self.phase_since = now
        self.last_event_id: str | None = None
        self.announced_mode: str | None = None
        self.last_green: str | None = None
        self.pending_target: str | None = None
        self.pending_reason: str | None = "startup"
        self._mode = FIXED
        self._last_ok: dict[str, float] = {}  # processed_at del último `ok` de cada acceso (sobrevive a `unavailable`)
        self._all_fresh_since: float | None = None
        self.resting = False
        self.notes: list[str] = []  # transiciones de modo/reposo para el log; se vacían con pop_notes()

    # -- entrada de detecciones

    def on_detection(self, payload: dict, now: float) -> str:
        """Devuelve 'accepted' o un texto 'ignored: motivo' (para el log)."""
        if not isinstance(payload, dict):
            return "ignored: payload no es un objeto"
        approach = payload.get("approach_id")
        if approach not in self.approaches:
            return f"ignored: acceso no configurado ({approach!r})"
        status, session, seq = payload.get("status"), payload.get("session_id"), payload.get("seq")
        if status not in ("ok", "unavailable") or not isinstance(session, str):
            return "ignored: status o session_id inválidos"
        if seq is not None and (not isinstance(seq, int) or isinstance(seq, bool)):
            return "ignored: seq inválido"
        if status == "ok" and seq is None:
            return "ignored: ok sin seq"
        prev = self.data.get(approach)
        if seq is None:
            return self._accept_will(approach, session, prev)
        if prev and prev.session_id == session and prev.last_seq is not None and seq <= prev.last_seq:
            return f"ignored: duplicado o fuera de orden (seq {seq} <= {prev.last_seq})"
        return self._store(approach, payload, session, seq, status, prev)

    def _accept_will(self, approach, session, prev) -> str:
        """`unavailable` sin seq (Last Will): no entra en el orden por seq ni en el dedupe."""
        if prev and prev.session_id != session:
            return "ignored: unavailable sin seq de otra sesión"
        if prev is None:
            self.data[approach] = ApproachData(session, None, "unavailable", None, None)
        else:
            prev.status, prev.demand = "unavailable", None
        return "accepted"

    def _store(self, approach, payload, session, seq, status, prev) -> str:
        if status == "unavailable":
            self.data[approach] = ApproachData(session, seq, status, None, None)
            return "accepted"
        processed_at = parse_iso(payload.get("processed_at"))
        count = (payload.get("metrics") or {}).get("visible_count")
        if processed_at is None or not isinstance(count, (int, float)) or isinstance(count, bool) or count < 0:
            return "ignored: ok sin processed_at o visible_count válidos"
        reseed = (prev is None or prev.demand is None or prev.status != "ok"
                  or prev.processed_at is None or processed_at - prev.processed_at > self.params.fresh_s)
        a = self.params.ema_alpha
        demand = float(count) if reseed else a * count + (1 - a) * prev.demand
        self.data[approach] = ApproachData(session, seq, "ok", processed_at, demand)
        self._last_ok[approach] = max(processed_at, self._last_ok.get(approach, processed_at))
        return "accepted"

    # -- estado efectivo del semáforo

    def on_effective_state(self, state: dict, now: float) -> str:
        """El semáforo manda: si su fase difiere de la que creemos (arranque, reinicio, rechazo), se adopta."""
        try:
            phase = phase_from_dict(state["phase"], self.approaches)
        except (KeyError, TypeError, ValueError) as e:
            return f"ignored: state inválido ({e})"
        if state.get("event_id") == self.last_event_id and self.last_event_id is not None:
            return "confirmed"
        if phase == self.phase:
            return "confirmed"
        self._set_phase(phase, now)
        self.announced_mode = state.get("mode") if state.get("mode") in (ADAPTIVE, FIXED) else None
        self.pending_target = None
        return f"adopted {phase_label(phase)}"

    # -- política

    def pop_notes(self) -> list[str]:
        notes, self.notes = self.notes, []
        return notes

    def _all_fresh(self, now: float) -> bool:
        return all(a in self.data and self.data[a].is_fresh_ok(now, self.params.fresh_s)
                   for a in self.approaches)

    def mode(self, now: float) -> str:
        """Modo con histéresis. Con estado: llamarlo con `now` no decreciente (lo hace `tick`)."""
        p = self.params
        if self._mode == ADAPTIVE:
            for a in self.approaches:
                last = self._last_ok.get(a)
                if last is None or now - last >= p.fail_after_s:
                    cause = "sin ningún ok" if last is None else f"sin ok hace {now - last:.1f} s"
                    self._switch_mode(FIXED, f"MODO adaptativo -> fijo: {a} {cause}")
                    break
        elif not self._all_fresh(now):
            self._all_fresh_since = None
        else:
            if self._all_fresh_since is None:
                self._all_fresh_since = now
            if now - self._all_fresh_since >= p.recover_after_s:
                self._switch_mode(ADAPTIVE, f"MODO fijo -> adaptativo: datos ok continuos "
                                            f"{now - self._all_fresh_since:.1f} s")
        return self._mode

    def _switch_mode(self, mode: str, note: str):
        self._mode, self._all_fresh_since = mode, None
        self.notes.append(note)

    def demand_of(self, approach: str) -> float:
        d = self.data.get(approach)
        return d.demand if d and d.demand is not None else 0.0

    def tick(self, now: float) -> dict | None:
        """Devuelve un comando si corresponde cambiar de fase (o reanunciar el modo), si no None."""
        mode = self.mode(now)  # también durante la espera inicial: el cronómetro de recuperación corre
        if now - self._created < self.start_wait_s:
            return None  # deja llegar el state retenido y las primeras detecciones antes de decidir
        if self.phase is None:
            return self._emit((ALL_RED, None), now, mode)
        self._update_resting(mode, now)
        kind, approach = self.phase
        elapsed = now - self.phase_since
        if kind == GREEN:
            decision = self._green_decision(mode, approach, elapsed, now)
            if decision:
                self.pending_target, reason = decision
                self.pending_reason = None if mode == FIXED else reason
                return self._emit((YELLOW, approach), now, mode)
        elif kind == YELLOW:
            if elapsed >= self.params.yellow_s:
                return self._emit((ALL_RED, None), now, mode)
        elif elapsed >= self.params.all_red_s:
            target = self.pending_target or self._choose_target(mode, self.last_green)
            return self._emit((GREEN, target), now, mode)
        if mode != self.announced_mode:  # cambio de modo sin cambio de fase: declararlo
            return self._emit(self.phase, now, mode, reason=REASON_FIXED if mode == FIXED else "data_recovered")
        return None

    def _rotation_after(self, approach):
        n = len(self.approaches)
        start = self.approaches.index(approach) + 1 if approach in self.approaches else 0
        return [self.approaches[(start + i) % n] for i in range(n)]

    def _choose_target(self, mode: str, last: str | None) -> str:
        order = self._rotation_after(last)
        return order[0] if mode == FIXED else self._highest_demand(order)

    def _highest_demand(self, order):
        """Mayor demanda; en empate gana el primero de `order` (el siguiente cíclico)."""
        best = order[0]
        for a in order[1:]:
            if self.demand_of(a) > self.demand_of(best):
                best = a
        return best

    def _update_resting(self, mode: str, now: float):
        """Reposo: verde en modo adaptativo, todos los datos vigentes y ninguna demanda."""
        resting = (self.phase[0] == GREEN and mode == ADAPTIVE and self._all_fresh(now)
                   and all(self.demand_of(a) < self.params.demand_present for a in self.approaches))
        if resting != self.resting:
            self.resting = resting
            self.notes.append(f"reposo: sin demanda, se mantiene {phase_label(self.phase)}" if resting
                              else "reposo terminado")

    def _green_decision(self, mode, current, elapsed, now):
        """(acceso siguiente, motivo) si el verde debe terminar ya; None si continúa."""
        p = self.params
        order = self._rotation_after(current)[:-1]  # los demás, empezando por el siguiente cíclico
        if mode == FIXED:
            return (order[0], REASON_FIXED) if order and elapsed >= p.fixed_green_s else None
        if not order or elapsed < p.min_green_s:
            return None
        if not self._all_fresh(now):  # gracia: un dato vencido nunca vale cero ni decide; solo rige el máximo
            return (order[0], "max_green") if elapsed >= p.max_green_s else None
        best = self._highest_demand(order)
        best_demand = self.demand_of(best)
        if best_demand < p.demand_present:
            return None  # reposo, o solo residuo de la media móvil
        if elapsed >= p.max_green_s:
            return best, "max_green"
        if best_demand >= self.demand_of(current) + p.switch_margin:
            return best, "demand"
        return None

    def _set_phase(self, phase: Phase, now: float):
        self.phase, self.phase_since = phase, now
        if phase[0] == GREEN:
            self.last_green = phase[1]

    def _emit(self, phase: Phase, now: float, mode: str, reason: str | None = None) -> dict:
        kind, _ = phase
        if reason is None:
            reason = REASON_FIXED if mode == FIXED else (self.pending_reason or "demand")
        if phase != self.phase:
            self._set_phase(phase, now)
        duration = self.params.fixed_green_s if (kind == GREEN and mode == FIXED) \
            else min_duration(kind, self.params)
        self.last_event_id = self._new_event_id()
        self.announced_mode = mode
        return {
            "v": PAYLOAD_VERSION,
            "event_id": self.last_event_id,
            "intersection_id": self.intersection_id,
            "issued_at": utc_iso(now),
            "phase": phase_to_dict(phase, self.approaches),
            "duration_s": duration,
            "reason": reason,
            "mode": mode,
        }

    def describe(self, now: float) -> str:
        """Demanda y último seq por acceso, para el log de cada decisión (RNF-08)."""
        parts = []
        for a in self.approaches:
            d = self.data.get(a)
            if d is None:
                parts.append(f"{a}: sin dato")
            else:
                age = "-" if d.processed_at is None else f"{now - d.processed_at:.1f}s"
                parts.append(f"{a}: {d.status} demanda={self.demand_of(a):.2f} seq={d.last_seq} edad={age}")
        return "; ".join(parts)


# ------------------------------------------------------------------ semáforo

class UnsafeCommand(Exception):
    """Comando rechazado; el mensaje es el motivo para el log."""


class SequenceValidator:
    """Estado efectivo del semáforo simulado y reglas de secuencia segura.

    Arranca en todo-rojo. Transiciones permitidas: todo-rojo -> verde(X); verde(X) -> amarillo(X);
    amarillo(X) -> todo-rojo. La fase actual debe haber durado su mínimo (con `tolerance_s` por la
    latencia de red entre los relojes del controlador y del semáforo).
    """

    def __init__(self, intersection_id: str, approaches, params: Params, now: float,
                 tolerance_s: float = 0.3):
        self.intersection_id = intersection_id
        self.approaches = list(approaches)
        self.params = params
        self.tolerance_s = tolerance_s
        self.phase: Phase = (ALL_RED, None)
        self.since = now
        self.duration_s = params.all_red_s
        self.event_id: str | None = None
        self.mode: str | None = None
        self.reason = "sim_start"
        self._seen_events: set[str] = set()

    def apply(self, cmd, now: float) -> str:
        """'changed', 'refreshed' (misma fase, nuevo modo/motivo) o 'duplicate'; UnsafeCommand si se rechaza."""
        if not isinstance(cmd, dict):
            raise UnsafeCommand("el comando no es un objeto JSON")
        event_id, mode, duration = cmd.get("event_id"), cmd.get("mode"), cmd.get("duration_s")
        if not isinstance(event_id, str) or not event_id:
            raise UnsafeCommand("falta event_id")
        if event_id in self._seen_events:
            return "duplicate"
        if cmd.get("intersection_id") != self.intersection_id:
            raise UnsafeCommand(f"intersection_id {cmd.get('intersection_id')!r} no corresponde")
        if mode not in (ADAPTIVE, FIXED) or not isinstance(cmd.get("reason"), str):
            raise UnsafeCommand("mode o reason inválidos")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            raise UnsafeCommand("duration_s inválido")
        try:
            new = phase_from_dict(cmd.get("phase"), self.approaches)
        except ValueError as e:
            raise UnsafeCommand(str(e)) from e
        if duration < min_duration(new[0], self.params):
            raise UnsafeCommand(f"duration_s {duration} menor al mínimo de {new[0]} "
                                f"({min_duration(new[0], self.params)})")
        outcome = "refreshed" if new == self.phase else self._check_transition(new, now)
        self._seen_events.add(event_id)
        if outcome == "changed":
            self.phase, self.since = new, now
        self.duration_s, self.event_id, self.mode, self.reason = duration, event_id, mode, cmd["reason"]
        return outcome

    def _check_transition(self, new: Phase, now: float) -> str:
        cur_kind, cur_app = self.phase
        allowed = {GREEN: (YELLOW, cur_app), YELLOW: (ALL_RED, None)}.get(cur_kind)
        valid = (new == allowed) if allowed else new[0] == GREEN
        if not valid:
            raise UnsafeCommand(f"transición no permitida {phase_label(self.phase)} -> {phase_label(new)}")
        held = now - self.since
        need = min_duration(cur_kind, self.params)
        if held + self.tolerance_s < need:
            raise UnsafeCommand(f"{phase_label(self.phase)} lleva {held:.1f}s, mínimo {need}s")
        return "changed"

    def state_payload(self, now: float) -> dict:
        return {
            "v": PAYLOAD_VERSION,
            "intersection_id": self.intersection_id,
            "phase": phase_to_dict(self.phase, self.approaches),
            "since": utc_iso(self.since),
            "duration_s": self.duration_s,
            "event_id": self.event_id,
            "mode": self.mode,
            "reason": self.reason,
            "updated_at": utc_iso(now),
        }
