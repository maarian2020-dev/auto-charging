from datetime import datetime

from autocharging.controller import Controller
from autocharging.remote import RemoteStore
from autocharging.rules import Rule, parse_time


def night_rule():
    return Rule("noche", mode="ready_by", start=parse_time("22:00"), end=parse_time("07:30"),
                ready_by=parse_time("07:30"), hold_low=90, hold_high=95, target=100)


def make(cfg, plug, hour, minute):
    clock = lambda: datetime(2026, 11, 3, hour, minute)
    return Controller(cfg, plug, RemoteStore(), rules=[night_rule()], clock=clock)


def test_holds_near_full_during_the_night(cfg, plug):
    c = make(cfg, plug, 3, 0)
    want, _ = c.decide(92, "remoto", False, False, 0, night_rule())
    assert want is None                       # 92 % > hold_low: no hace nada
    want, _ = c.decide(88, "remoto", False, False, 0, night_rule())
    assert want is True                       # baja del nivel de espera: recupera
    want, _ = c.decide(96, "remoto", True, False, 10, night_rule())
    assert want is False                      # llega al nivel de espera: para


def test_delays_final_top_up_until_needed(cfg, plug):
    # 92 -> 100 con tiempos genericos: ~20 min * 1,15 + 10 = 33 min antes de las 07:30
    early = make(cfg, plug, 6, 30)
    assert early.decide(92, "remoto", False, False, 0, night_rule())[0] is None
    late = make(cfg, plug, 7, 0)
    want, reason = late.decide(92, "remoto", False, False, 0, night_rule())
    assert want is True and "07:30" in reason


def test_stops_at_target_and_does_not_flap(cfg, plug):
    c = make(cfg, plug, 7, 20)
    assert c.decide(100, "remoto", True, False, 30, night_rule())[0] is False
    assert c.decide(99, "remoto", False, False, 0, night_rule())[0] is None   # deriva 1 %: no reenciende
    assert c.decide(97, "remoto", False, False, 0, night_rule())[0] is True


def test_target_100_not_cut_by_global_safety_limit(cfg, plug):
    c = make(cfg, plug, 7, 20)                # abs_max global = 90, pero el objetivo es 100
    assert c.decide(95, "remoto", True, False, 30, night_rule())[0] is None


def test_final_top_up_is_latched(cfg, plug):
    now = {"t": datetime(2026, 11, 3, 7, 0)}
    c = Controller(cfg, plug, RemoteStore(), rules=[night_rule()], clock=lambda: now["t"])
    assert c.decide(92, "remoto", False, False, 0, night_rule())[0] is True
    now["t"] = datetime(2026, 11, 3, 7, 12)     # el tiempo restante ya es corto, pero sigue cargando
    assert c.decide(97, "remoto", True, False, 12, night_rule())[0] is None
