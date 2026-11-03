import time

from autocharging.controller import Controller
from autocharging.remote import RemoteStore


def test_hysteresis_with_remote_battery(cfg, plug):
    store = RemoteStore()
    c = Controller(cfg, plug, store)
    for pct in (50, 18):
        store.put("movil", pct)
        c.step()
    assert plug.on is True            # 18% <= 20% -> enciende
    store.put("movil", 50)
    c.step()
    assert plug.on is True            # entre umbrales: no cambia
    store.put("movil", 81)
    c.step()
    assert plug.on is False           # >= 80% -> apaga


def test_abs_max_safety(cfg, plug):
    store = RemoteStore()
    c = Controller(cfg, plug, store)
    plug.on = True
    store.put("movil", 95)
    c.step()
    assert plug.on is False


def test_power_taper_detects_full_charge(cfg, plug):
    c = Controller(cfg, plug, RemoteStore())   # sin dato remoto -> estimado
    plug.on = True
    c.on_since = time.time() - 600
    for watts in (60, 60, 40, 10, 3, 3, 3):
        plug.watts = watts
        c.step()
    assert plug.on is False
    assert c.est.pct == 100.0


def test_max_charge_time(cfg, plug):
    store = RemoteStore()
    c = Controller(cfg, plug, store)
    plug.on = True
    store.put("movil", 50)
    c.on_since = time.time() - (cfg.max_charge_min + 1) * 60
    c.step()
    assert plug.on is False


def test_stale_remote_falls_back_to_estimate(cfg, plug):
    c = Controller(cfg, plug, RemoteStore())
    pct, origin = c._percent()
    assert origin == "estimado"
