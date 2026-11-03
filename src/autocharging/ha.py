"""Integracion con Home Assistant: API REST, enchufe y bateria del movil (app Companion)."""
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime

from .plug import PlugError, PlugState

log = logging.getLogger("autocharging")

UNAVAILABLE = ("unavailable", "unknown", "")
PLUGGED_TRUE = {"on", "true", "ac", "usb", "wireless", "dock", "plugged", "charging"}
PLUGGED_FALSE = {"off", "false", "none", "unplugged", "discharging"}


class HAError(Exception):
    pass


class HAClient:
    """Cliente minimo de la API REST de Home Assistant (solo libreria estandar)."""

    def __init__(self, url, token, timeout=10):
        url = url.rstrip("/")
        self.base = url if url.endswith("/api") else url + "/api"
        self.token = token
        self.timeout = timeout

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            hints = {401: "token no valido", 404: "no encontrado (revisa el entity_id)"}
            raise HAError(f"HTTP {e.code} en {path}: {hints.get(e.code, e.reason)}")
        except (urllib.error.URLError, OSError) as e:
            raise HAError(f"sin conexion con Home Assistant ({self.base}): {e}")
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            raise HAError(f"respuesta no valida en {path}")

    def state(self, entity_id):
        return self._request("GET", f"/states/{entity_id}")

    def call_service(self, domain, service, data):
        return self._request("POST", f"/services/{domain}/{service}", data)

    def set_state(self, entity_id, state, attributes=None):
        return self._request("POST", f"/states/{entity_id}", {"state": state, "attributes": attributes or {}})

    def notify(self, service, message, title="Auto Charging"):
        domain, _, name = service.partition(".")
        if not name:
            raise HAError(f"HA_NOTIFY_SERVICE debe tener la forma notify.xxx, no '{service}'")
        self.call_service(domain, name, {"title": title, "message": message})


def _age_minutes(iso):
    try:
        return (time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) / 60
    except (ValueError, AttributeError):
        return None


class HAPlug:
    """Enchufe controlado a traves de una entidad de Home Assistant (switch.*)."""

    settle_s = 1.5

    def __init__(self, cfg, client, dry_run=False):
        self.cfg, self.client, self.dry_run = cfg, client, dry_run

    def read(self):
        try:
            st = self.client.state(self.cfg.ha_switch)
            if st.get("state") in UNAVAILABLE:
                raise PlugError(f"{self.cfg.ha_switch} no disponible")
            power = None
            if self.cfg.ha_power:
                ps = self.client.state(self.cfg.ha_power)
                if ps.get("state") not in UNAVAILABLE:
                    power = float(ps["state"])
                    unit = (ps.get("attributes") or {}).get("unit_of_measurement", "W")
                    power *= {"kW": 1000.0, "mW": 0.001}.get(unit, 1.0)
        except HAError as e:
            raise PlugError(str(e))
        except ValueError:
            raise PlugError("el sensor de potencia no devuelve un numero")
        return PlugState(st.get("state") == "on", power)

    def set_state(self, on, retries=3):
        if self.dry_run:
            log.info("[dry-run] pondria el enchufe en %s", "ON" if on else "OFF")
            return True
        for attempt in range(1, retries + 1):
            try:
                self.client.call_service("homeassistant", "turn_on" if on else "turn_off",
                                         {"entity_id": self.cfg.ha_switch})
                time.sleep(self.settle_s)
                if self.read().on == on:
                    return True
            except (HAError, PlugError) as e:
                log.warning("Intento %d/%d fallido: %s", attempt, retries, e)
            time.sleep(self.settle_s * attempt)
        return False


class HABattery:
    """Bateria de un movil/portatil con la app Companion (Android o iPhone) via Home Assistant."""

    def __init__(self, cfg, client):
        self.cfg, self.client = cfg, client

    def read(self):
        """(porcentaje, enchufado|None), o None si no hay un dato fiable."""
        try:
            st = self.client.state(self.cfg.ha_battery)
        except HAError as e:
            log.warning("No se pudo leer la bateria en Home Assistant: %s", e)
            return None
        if st.get("state") in UNAVAILABLE:
            return None
        try:
            pct = float(st["state"])
        except (ValueError, KeyError):
            return None
        if not 0 <= pct <= 100:
            return None
        reported = st.get("last_reported")   # se actualiza aunque el valor no cambie
        age = _age_minutes(reported) if reported else None
        if self.cfg.ha_max_age and age is not None and age > self.cfg.ha_max_age:
            log.warning("Dato de bateria antiguo (%.0f min sin informar): se usa la estimacion", age)
            return None
        return pct, self._plugged()

    def _plugged(self):
        try:
            if self.cfg.ha_plugged:
                v = str(self.client.state(self.cfg.ha_plugged).get("state", "")).lower()
                return True if v in PLUGGED_TRUE else False if v in PLUGGED_FALSE else None
            if self.cfg.ha_battery_state:
                raw = str(self.client.state(self.cfg.ha_battery_state).get("state", ""))
                low = raw.lower()
                if low in ("charging", "full", "not_charging"):   # Android: not_charging = enchufado
                    return True
                if low in ("discharging", "not charging"):        # iOS: "Not Charging" = sin cargador
                    return False
        except HAError:
            pass
        return None
