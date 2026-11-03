"""Configuracion leida de variables de entorno / credentials.env."""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _f(name, default):
    return float(os.getenv(name, default))


@dataclass
class Config:
    device_id: str = ""
    ip: str = ""
    local_key: str = ""
    version: float = 3.3
    switch_dp: int = 1
    power_dp: str = "19"
    power_scale: float = 10.0
    low: float = 20.0
    high: float = 80.0
    abs_max: float = 90.0
    poll: int = 60
    target: str = "local"
    remote_port: int = 0
    token: str = ""
    remote_max_age: int = 600
    capacity_wh: float = 50.0
    efficiency: float = 0.85
    start_pct: float = 50.0
    drain_pct_h: float = 8.0
    full_ratio: float = 0.15
    full_abs_w: float = 5.0
    min_charge_w: float = 15.0
    full_samples: int = 5
    max_charge_min: float = 360.0
    rules_file: str = "rules.toml"
    history_db: str = "autocharging.db"
    backend: str = "tuya"            # tuya | homeassistant
    ha_url: str = ""
    ha_token: str = ""
    ha_switch: str = ""
    ha_power: str = ""
    ha_battery: str = ""
    ha_battery_state: str = ""
    ha_plugged: str = ""
    ha_notify: str = ""
    ha_max_age: float = 180.0        # minutos

    def validate(self):
        if not self.low < self.high <= self.abs_max <= 100:
            raise ValueError("Umbrales invalidos: se exige LOW < HIGH <= ABS_MAX <= 100")

    @classmethod
    def from_env(cls, env_file=None):
        path = Path(env_file or os.getenv("ALC_ENV_FILE", "credentials.env"))
        load_dotenv(path)
        supervisor = os.getenv("SUPERVISOR_TOKEN")        # dentro del add-on de Home Assistant
        ha_url = os.getenv("HA_URL") or ("http://supervisor/core/api" if supervisor else "")
        ha_token = os.getenv("HA_TOKEN") or supervisor or ""
        backend = os.getenv("PLUG_BACKEND") or ("homeassistant" if os.getenv("HA_SWITCH_ENTITY") else "tuya")
        if backend not in ("tuya", "homeassistant"):
            sys.exit("PLUG_BACKEND debe ser tuya o homeassistant")
        needed = (["DEVICE_ID", "DEVICE_IP_ADDRESS", "LOCAL_KEY"] if backend == "tuya"
                  else ["HA_SWITCH_ENTITY"])
        missing = [k for k in needed if not os.getenv(k)]
        if backend == "homeassistant":
            missing += [k for k, v in (("HA_URL", ha_url), ("HA_TOKEN", ha_token)) if not v]
        if missing:
            sys.exit(f"Faltan variables en {path}: {', '.join(missing)}")
        if os.getenv("HA_BATTERY_ENTITY") and not (ha_url and ha_token):
            sys.exit("HA_BATTERY_ENTITY necesita HA_URL y HA_TOKEN")
        cfg = cls(
            device_id=os.getenv("DEVICE_ID", ""),
            ip=os.getenv("DEVICE_IP_ADDRESS", ""),
            local_key=os.getenv("LOCAL_KEY", ""),
            version=_f("TUYA_VERSION", 3.3),
            switch_dp=int(_f("SWITCH_DP", 1)),
            power_dp=os.getenv("POWER_DP", "19"),
            power_scale=_f("POWER_SCALE", 10),
            low=_f("BATTERY_LOW", 20),
            high=_f("BATTERY_HIGH", 80),
            abs_max=_f("BATTERY_ABS_MAX", 90),
            poll=int(_f("POLL_SECONDS", 60)),
            target=os.getenv("TARGET_DEVICE", "local"),
            remote_port=int(_f("REMOTE_PORT", 0)),
            token=os.getenv("REMOTE_TOKEN", ""),
            remote_max_age=int(_f("REMOTE_MAX_AGE", 600)),
            capacity_wh=_f("CAPACITY_WH", 50),
            efficiency=_f("CHARGE_EFFICIENCY", 0.85),
            start_pct=_f("EST_START_PERCENT", 50),
            drain_pct_h=_f("EST_DRAIN_PCT_PER_HOUR", 8),
            full_ratio=_f("FULL_RATIO", 0.15),
            full_abs_w=_f("FULL_ABS_W", 5),
            min_charge_w=_f("MIN_CHARGE_W", 15),
            full_samples=int(_f("FULL_SAMPLES", 5)),
            max_charge_min=_f("MAX_CHARGE_MINUTES", 360),
            rules_file=os.getenv("RULES_FILE", "rules.toml"),
            history_db=os.getenv("HISTORY_DB", "autocharging.db"),
            backend=backend,
            ha_url=ha_url,
            ha_token=ha_token,
            ha_switch=os.getenv("HA_SWITCH_ENTITY", ""),
            ha_power=os.getenv("HA_POWER_ENTITY", ""),
            ha_battery=os.getenv("HA_BATTERY_ENTITY", ""),
            ha_battery_state=os.getenv("HA_BATTERY_STATE_ENTITY", ""),
            ha_plugged=os.getenv("HA_PLUGGED_ENTITY", ""),
            ha_notify=os.getenv("HA_NOTIFY_SERVICE", ""),
            ha_max_age=_f("HA_MAX_AGE_MINUTES", 180),
        )
        try:
            cfg.validate()
        except ValueError as e:
            sys.exit(str(e))
        return cfg
