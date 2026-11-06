import pytest

from autocharging.ha import HAClient, HAPlug
from autocharging.selftest import discover, format_discovery, run_cycle_test, run_selftest
from test_ha import TOKEN, FakeHA, ha, ha_cfg  # noqa: F401  (ha es una fixture)


def setup_laptop(ha, level="60", plug_on=True):
    ha.power_entity = "sensor.cargador_potencia"
    ha.set("switch.cargador", "on" if plug_on else "off", friendly_name="Laptop Charger")
    ha.set("sensor.cargador_potencia", "65" if plug_on else "0", unit_of_measurement="W", device_class="power")
    ha.set("sensor.movil_battery_level", level, device_class="battery")
    ha.set("sensor.movil_battery_state", "Charging")
    cfg = ha_cfg(ha)
    client = HAClient(ha.url, TOKEN)
    plug = HAPlug(cfg, client)
    plug.settle_s = 0
    return cfg, client, plug


def test_discover_groups_and_filters(ha):
    setup_laptop(ha)
    ha.set("switch.luz_patio", "off", friendly_name="Luz Patio")
    found = discover(HAClient(ha.url, TOKEN))
    assert [r[0] for r in found["switch"]] == ["switch.cargador", "switch.luz_patio"]
    assert found["power"][0][0] == "sensor.cargador_potencia"
    assert "sensor.movil_battery_level" in [r[0] for r in found["battery"]]
    only = discover(HAClient(ha.url, TOKEN), "laptop")                  # filtra por nombre amigable
    assert [r[0] for r in only["switch"]] == ["switch.cargador"]
    assert "Laptop Charger" in format_discovery(only)


def test_selftest_read_only_is_apto(ha):
    cfg, client, plug = setup_laptop(ha)
    out = []
    checks = run_selftest(cfg, client, plug, out=out.append)
    assert not [c for c in checks if c.status == "FALLO"]
    assert out[-1].endswith("APTO")
    assert ha.calls == []                      # sin --actuate no se toca el enchufe


def test_selftest_reports_failures(ha):
    cfg, client, plug = setup_laptop(ha)
    bad = HAClient(ha.url, "token-malo")
    out = []
    checks = run_selftest(cfg, bad, plug, out=out.append)
    assert checks[0].status == "FALLO" and "token" in checks[0].detail
    ha.set("sensor.movil_battery_level", "unavailable")
    checks = run_selftest(cfg, client, plug, out=out.append)
    assert any(c.status == "FALLO" and "bateria" in c.name for c in checks)


def test_selftest_actuate_leaves_plug_on(ha):
    cfg, client, plug = setup_laptop(ha)
    out = []
    checks = run_selftest(cfg, client, plug, actuate=True, ask=lambda _: "s", sleep=lambda _: None, out=out.append)
    names = [c.name for c in checks]
    assert "Apagado confirmado" in names and "Encendido confirmado" in names
    assert ha.states["switch.cargador"]["state"] == "on"                 # siempre termina encendido
    assert [c[0] for c in ha.calls] == ["/api/services/homeassistant/turn_off", "/api/services/homeassistant/turn_on"]


def test_selftest_actuate_respects_refusal_and_low_battery(ha):
    cfg, client, plug = setup_laptop(ha)
    run_selftest(cfg, client, plug, actuate=True, ask=lambda _: "n", sleep=lambda _: None, out=lambda *_: None)
    assert ha.calls == []
    ha.set("sensor.movil_battery_level", "20")
    out = []
    run_selftest(cfg, client, plug, actuate=True, ask=lambda _: "s", sleep=lambda _: None, out=out.append)
    assert ha.calls == [] and any("omitida" in line for line in out)


def test_cycle_test_sees_off_then_on_and_ends_on(ha):
    cfg, client, plug = setup_laptop(ha, level="60")

    def tick(on):                                  # la bateria sube cargando y baja sin cargar
        level = float(ha.states["sensor.movil_battery_level"]["state"]) + (1 if on else -1)
        ha.set("sensor.movil_battery_level", str(level), device_class="battery")

    out = []
    result = run_cycle_test(cfg, client, plug, max_minutes=5, step_s=0, sleep=lambda _: None,
                            out=out.append, tick=tick)
    assert result["ok"] is True
    assert [e[0] for e in result["events"]] == ["OFF", "ON"]
    assert ha.states["switch.cargador"]["state"] == "on"


def test_cycle_test_refuses_unsafe_start(ha):
    cfg, client, plug = setup_laptop(ha, level="15")
    out = []
    assert run_cycle_test(cfg, client, plug, out=out.append)["ok"] is False
    assert ha.calls == []
    cfg, client, plug = setup_laptop(ha, level="60", plug_on=False)
    assert run_cycle_test(cfg, client, plug, out=out.append)["ok"] is False
    assert ha.calls == []


def test_cycle_test_restores_plug_even_if_it_times_out(ha):
    cfg, client, plug = setup_laptop(ha, level="60")
    out = []
    # la bateria no se mueve: se apaga? no (no llega a high) -> sin ciclo, pero el enchufe sigue encendido
    result = run_cycle_test(cfg, client, plug, max_minutes=0, step_s=0, sleep=lambda _: None, out=out.append)
    assert result["ok"] is False
    assert ha.states["switch.cargador"]["state"] == "on"
