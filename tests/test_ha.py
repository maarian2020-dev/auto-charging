import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from autocharging.config import Config
from autocharging.controller import Controller
from autocharging.ha import HABattery, HAClient, HAError, HAPlug
from autocharging.remote import RemoteStore

TOKEN = "tok"


class FakeHA:
    def __init__(self):
        self.states = {}
        self.calls = []
        self.power_entity = None     # si se define, su valor sigue al enchufe (65 W encendido / 0 W apagado)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _auth(self):
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    self._send(401, {"message": "unauthorized"})
                    return False
                return True

            def _send(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if not self._auth():
                    return
                if self.path == "/api/":
                    return self._send(200, {"message": "API running."})
                if self.path == "/api/states":
                    return self._send(200, [dict(v, entity_id=k) for k, v in outer.states.items()])
                entity = self.path.removeprefix("/api/states/")
                if entity in outer.states:
                    self._send(200, outer.states[entity])
                else:
                    self._send(404, {"message": "not found"})

            def do_POST(self):
                if not self._auth():
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.startswith("/api/services/"):
                    outer.calls.append((self.path, body))
                    if self.path.endswith(("turn_on", "turn_off")):
                        on = self.path.endswith("turn_on")
                        outer.states[body["entity_id"]]["state"] = "on" if on else "off"
                        if outer.power_entity:
                            outer.states[outer.power_entity]["state"] = "65" if on else "0"
                    self._send(200, [])
                else:
                    entity = self.path.removeprefix("/api/states/")
                    outer.states[entity] = {"state": str(body["state"]), "attributes": body["attributes"]}
                    self._send(200, outer.states[entity])

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def set(self, entity, state, **attrs):
        self.states[entity] = {"state": str(state), "attributes": attrs}


@pytest.fixture
def ha():
    fake = FakeHA()
    yield fake
    fake.server.shutdown()


def ha_cfg(ha, **kw):
    base = dict(backend="homeassistant", ha_url=ha.url, ha_token=TOKEN, ha_switch="switch.cargador",
                ha_power="sensor.cargador_potencia", ha_battery="sensor.movil_battery_level",
                ha_battery_state="sensor.movil_battery_state", target="movil")
    base.update(kw)
    return Config(**base)


def test_client_errors(ha):
    assert HAClient(ha.url, "mal").base.endswith("/api")
    with pytest.raises(HAError, match="token"):
        HAClient(ha.url, "mal").state("sensor.x")
    with pytest.raises(HAError, match="entity_id"):
        HAClient(ha.url, TOKEN).state("sensor.no_existe")
    with pytest.raises(HAError, match="sin conexion"):
        HAClient("http://127.0.0.1:9", TOKEN, timeout=1).state("sensor.x")


def test_plug_reads_and_switches(ha):
    ha.set("switch.cargador", "off")
    ha.set("sensor.cargador_potencia", "0.045", unit_of_measurement="kW")
    plug = HAPlug(ha_cfg(ha), HAClient(ha.url, TOKEN))
    plug.settle_s = 0
    state = plug.read()
    assert state.on is False and state.power_w == pytest.approx(45.0)   # kW -> W
    assert plug.set_state(True) is True
    assert plug.read().on is True
    assert ha.calls[-1][0] == "/api/services/homeassistant/turn_on"


def test_battery_android_and_ios(ha):
    cfg = ha_cfg(ha)
    battery = HABattery(cfg, HAClient(ha.url, TOKEN))
    ha.set("sensor.movil_battery_level", "54")
    ha.set("sensor.movil_battery_state", "Charging")                 # iPhone
    assert battery.read() == (54.0, True)
    ha.set("sensor.movil_battery_state", "Not Charging")             # iPhone sin cargador
    assert battery.read() == (54.0, False)
    ha.set("sensor.movil_battery_state", "discharging")              # Android
    assert battery.read() == (54.0, False)
    ha.set("sensor.movil_battery_state", "not_charging")             # Android enchufado, sin cargar
    assert battery.read() == (54.0, True)
    ha.set("sensor.movil_battery_level", "unavailable")
    assert battery.read() is None


def test_stale_battery_is_ignored(ha):
    battery = HABattery(ha_cfg(ha, ha_max_age=60), HAClient(ha.url, TOKEN))
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    ha.states["sensor.movil_battery_level"] = {"state": "40", "attributes": {}, "last_reported": old}
    assert battery.read() is None
    ha.states["sensor.movil_battery_level"]["last_reported"] = datetime.now(timezone.utc).isoformat()
    assert battery.read()[0] == 40.0


def test_full_cycle_through_home_assistant(ha):
    ha.set("switch.cargador", "off")
    ha.set("sensor.cargador_potencia", "0", unit_of_measurement="W")
    ha.set("sensor.movil_battery_level", "15")
    ha.set("sensor.movil_battery_state", "Not Charging")
    cfg = ha_cfg(ha, ha_notify="notify.mobile_app_pixel")
    client = HAClient(ha.url, TOKEN)
    plug = HAPlug(cfg, client)
    plug.settle_s = 0
    c = Controller(cfg, plug, RemoteStore(), ha_client=client, ha_battery=HABattery(cfg, client))

    c.step()                                                          # 15 % -> enciende
    assert ha.states["switch.cargador"]["state"] == "on"
    published = ha.states["sensor.autocharging_movil"]                # sensor expuesto en HA
    assert published["state"] == "15" and published["attributes"]["origen"] == "ha"

    ha.set("sensor.movil_battery_level", "85")
    c.step()                                                          # 85 % -> apaga
    assert ha.states["switch.cargador"]["state"] == "off"
    assert c.last_pct == (85.0, "ha")


def test_local_psutil_battery_not_used_when_ha_battery_configured(ha):
    """Con HA_BATTERY_ENTITY, nunca se debe caer a la bateria del PC donde corre el script."""
    cfg = ha_cfg(ha, target="local")
    client = HAClient(ha.url, TOKEN)
    ha.set("sensor.movil_battery_level", "unavailable")
    c = Controller(cfg, HAPlug(cfg, client), RemoteStore(), ha_client=client, ha_battery=HABattery(cfg, client))
    assert c._percent()[1] == "estimado"
