"""Enchufe inteligente Tuya (control local con tinytuya) y tipos comunes de enchufe."""
import logging
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("autocharging")


class PlugError(Exception):
    pass


@dataclass
class PlugState:
    on: bool
    power_w: Optional[float] = None


class Plug:
    """Enchufe Tuya por red local (requiere el extra 'tuya': pip install autocharging[tuya])."""

    def __init__(self, cfg, dry_run=False):
        try:
            import tinytuya
        except ImportError:
            raise SystemExit("Falta tinytuya. Instala con: pip install \"autocharging[tuya]\"")
        self.cfg = cfg
        self.dry_run = dry_run
        self.dev = tinytuya.OutletDevice(cfg.device_id, cfg.ip, cfg.local_key)
        self.dev.set_version(cfg.version)
        for method, value in (("set_socketPersistent", False),
                              ("set_socketRetryLimit", 2),
                              ("set_socketTimeout", 5)):
            if hasattr(self.dev, method):
                getattr(self.dev, method)(value)

    def read_dps(self):
        data = self.dev.status()
        if not isinstance(data, dict) or "dps" not in data:
            err = data.get("Error") if isinstance(data, dict) else data
            raise PlugError(err or "respuesta vacia")
        return data["dps"]

    def read(self):
        dps = self.read_dps()
        raw = dps.get(self.cfg.power_dp)
        power = float(raw) / self.cfg.power_scale if raw is not None else None
        return PlugState(bool(dps.get(str(self.cfg.switch_dp))), power)

    def set_state(self, on, retries=3):
        """Conmuta y verifica leyendo el estado real. Devuelve True si se confirmo."""
        if self.dry_run:
            log.info("[dry-run] pondria el enchufe en %s", "ON" if on else "OFF")
            return True
        for attempt in range(1, retries + 1):
            try:
                if on:
                    self.dev.turn_on(switch=self.cfg.switch_dp)
                else:
                    self.dev.turn_off(switch=self.cfg.switch_dp)
                time.sleep(1.5)
                if self.read().on == on:
                    return True
            except PlugError as e:
                log.warning("Intento %d/%d fallido: %s", attempt, retries, e)
            time.sleep(2 * attempt)
        return False
