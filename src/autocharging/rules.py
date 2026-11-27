"""Reglas de carga por franja horaria definidas por el usuario (rules.toml).

Dos modos:
  range    -> histeresis clasica: enciende por debajo de `low`, apaga por encima de `high`.
  ready_by -> "listo a una hora": mantiene el nivel de espera (hold_low..hold_high) y
              programa el ultimo tramo para llegar a `target` justo a la hora `ready_by`.
"""
import sys
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
        "lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
ALLOWED_KEYS = {"name", "mode", "days", "start", "end", "low", "high",
                "hold_low", "hold_high", "target", "ready_by"}


def parse_time(text):
    return datetime.strptime(str(text), "%H:%M").time()


@dataclass
class Rule:
    name: str
    mode: str = "range"
    low: float = 20.0
    high: float = 80.0
    hold_low: float = 85.0
    hold_high: float = 90.0
    target: float = 100.0
    ready_by: Optional[time] = None
    start: Optional[time] = None
    end: Optional[time] = None
    days: frozenset = field(default_factory=lambda: frozenset(range(7)))

    def validate(self):
        if self.mode == "range":
            if not 0 <= self.low < self.high <= 100:
                raise ValueError("en modo range se exige 0 <= low < high <= 100")
        elif self.mode == "ready_by":
            if self.ready_by is None:
                raise ValueError("el modo ready_by necesita 'ready_by = \"HH:MM\"'")
            if not 0 <= self.hold_low < self.hold_high <= self.target <= 100:
                raise ValueError("se exige hold_low < hold_high <= target <= 100")
        else:
            raise ValueError(f"modo desconocido '{self.mode}' (usa range o ready_by)")

    def matches(self, now):
        if self.start is None or self.end is None or self.start == self.end:
            return now.weekday() in self.days
        t = now.time()
        if self.start < self.end:
            return self.start <= t < self.end and now.weekday() in self.days
        # la franja cruza la medianoche; los dias se refieren al dia en que empieza
        if t >= self.start:
            return now.weekday() in self.days
        if t < self.end:
            return (now.weekday() - 1) % 7 in self.days
        return False

    def deadline(self, now):
        cand = now.replace(hour=self.ready_by.hour, minute=self.ready_by.minute,
                           second=0, microsecond=0)
        return cand if cand > now else cand + timedelta(days=1)


def default_rule(cfg):
    return Rule(name="por-defecto", mode="range", low=cfg.low, high=cfg.high)


def _build(raw, index):
    unknown = set(raw) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"claves desconocidas: {', '.join(sorted(unknown))}")
    days = frozenset(range(7))
    if "days" in raw:
        try:
            days = frozenset(DAYS[str(d).lower()[:3]] for d in raw["days"])
        except KeyError as e:
            raise ValueError(f"dia no valido: {e} (usa mon..sun o lun..dom)")
    rule = Rule(
        name=str(raw.get("name", f"regla-{index}")),
        mode=str(raw.get("mode", "range")),
        low=float(raw.get("low", 20)),
        high=float(raw.get("high", 80)),
        hold_low=float(raw.get("hold_low", 85)),
        hold_high=float(raw.get("hold_high", 90)),
        target=float(raw.get("target", 100)),
        ready_by=parse_time(raw["ready_by"]) if "ready_by" in raw else None,
        start=parse_time(raw["start"]) if "start" in raw else None,
        end=parse_time(raw["end"]) if "end" in raw else None,
        days=days,
    )
    rule.validate()
    return rule


def load_rules(path):
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    rules = []
    for i, raw in enumerate(data.get("rule", []), 1):
        try:
            rules.append(_build(raw, i))
        except (ValueError, TypeError) as e:
            raise ValueError(f"{path}, regla {i}: {e}")
    return rules


def active_rule(rules, now, default):
    """Primera regla del fichero cuya franja coincide; si ninguna, la regla por defecto."""
    for rule in rules:
        if rule.matches(now):
            return rule
    return default
