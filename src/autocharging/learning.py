"""Aprendizaje a partir del historial: sesiones de carga, cargadores y tiempos."""
import math
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .history import Sample

MAX_GAP = 600  # s: un hueco mayor parte la sesion
DEFAULT_RATES = {b: 1.0 for b in range(0, 80, 10)}
DEFAULT_RATES.update({80: 1.5, 90: 2.5})  # min por punto de bateria (valores genericos)


def minutes_of_day(ts):
    d = datetime.fromtimestamp(ts)
    return d.hour * 60 + d.minute


def circular_mean_minutes(values):
    if not values:
        return None
    ang = [v / 1440 * 2 * math.pi for v in values]
    x, y = sum(math.cos(a) for a in ang), sum(math.sin(a) for a in ang)
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return (math.atan2(y, x) / (2 * math.pi) * 1440) % 1440


def clock(minutes):
    return f"{int(minutes // 60) % 24:02d}:{int(minutes % 60):02d}"


@dataclass
class Session:
    start: float
    end: float
    peak_w: Optional[float]
    energy_wh: float
    pct_start: Optional[float]
    pct_end: Optional[float]
    samples: List[Sample]

    @property
    def minutes(self):
        return (self.end - self.start) / 60


def _percentile(values, p):
    s = sorted(values)
    return s[int(p * (len(s) - 1))]


def _summarize(chunk):
    powers = [s.power for s in chunk if s.power is not None]
    energy = 0.0
    for a, b in zip(chunk, chunk[1:]):
        if a.power is not None and b.power is not None and b.ts - a.ts <= MAX_GAP:
            energy += (b.ts - a.ts) / 3600 * (a.power + b.power) / 2
    real = [s.pct for s in chunk if s.pct is not None and s.origin != "estimado"]
    return Session(chunk[0].ts, chunk[-1].ts, _percentile(powers, 0.95) if powers else None,
                   energy, real[0] if real else None, real[-1] if real else None, chunk)


def split_sessions(samples):
    """Una sesion = tramo continuo con el enchufe encendido."""
    chunks, cur = [], []
    for s in samples:
        if s.on:
            if cur and s.ts - cur[-1].ts > MAX_GAP:
                chunks.append(cur)
                cur = []
            cur.append(s)
        elif cur:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return [_summarize(c) for c in chunks if len(c) >= 2]


@dataclass
class Charger:
    peak_w: float
    sessions: List[Session]

    @property
    def n(self):
        return len(self.sessions)

    @property
    def typical_start(self):
        return circular_mean_minutes([minutes_of_day(s.start) for s in self.sessions])

    @property
    def median_minutes(self):
        return statistics.median(s.minutes for s in self.sessions)


def cluster_chargers(sessions, min_w=5.0, tol=0.2):
    """Agrupa sesiones por potencia maxima (+-20 %): cada grupo es un cargador distinto."""
    cand = sorted((s for s in sessions if s.peak_w and s.peak_w >= min_w), key=lambda s: s.peak_w)
    groups = []
    for s in cand:
        if groups and s.peak_w <= groups[-1][0].peak_w * (1 + tol):
            groups[-1].append(s)
        else:
            groups.append([s])
    chargers = [Charger(statistics.median(s.peak_w for s in g), g) for g in groups]
    return sorted(chargers, key=lambda c: c.n, reverse=True)


def rate_table(sessions):
    """Minutos por punto de bateria, por tramos de 10 %, medidos con porcentaje real."""
    mins, pts = defaultdict(float), defaultdict(float)
    for sess in sessions:
        real = [s for s in sess.samples if s.pct is not None and s.origin != "estimado"]
        for a, b in zip(real, real[1:]):
            dt, dp = (b.ts - a.ts) / 60, b.pct - a.pct
            if dt <= 0 or dt > MAX_GAP / 60 or dp < 0 or a.pct >= 99:
                continue
            bin_ = min(90, int(a.pct // 10) * 10)
            mins[bin_] += dt
            pts[bin_] += dp
    return {b: mins[b] / pts[b] for b in mins if pts[b] >= 3}


def minutes_for(a, b, tables):
    """Minutos para pasar de a% a b%, usando la primera tabla que tenga cada tramo."""
    a, b = max(0.0, a), min(100.0, b)
    if b <= a:
        return 0.0
    total = 0.0
    for start in range(0, 100, 10):
        overlap = min(b, start + 10) - max(a, start)
        if overlap > 0:
            rate = next((t[start] for t in tables if start in t), DEFAULT_RATES[start])
            total += overlap * rate
    return total


@dataclass
class Data:
    samples: List[Sample]
    sessions: List[Session]
    chargers: List[Charger]
    global_table: dict
    charger_tables: list


class Learner:
    def __init__(self, history, ttl=1800, days=60):
        self.history, self.ttl, self.days = history, ttl, days
        self._data, self._built = None, 0.0

    def data(self, now=None):
        now = now or time.time()
        if self._data is None or now - self._built > self.ttl:
            samples = self.history.samples(now - self.days * 86400)
            sessions = split_sessions(samples)
            chargers = cluster_chargers(sessions)
            self._data = Data(samples, sessions, chargers, rate_table(sessions),
                              [rate_table(c.sessions) for c in chargers])
            self._built = now
        return self._data

    def identify(self, power_w):
        """Indice del cargador conocido mas parecido a power_w (+-25 %), o None."""
        d = self.data()
        if not power_w or not d.chargers:
            return None
        best = min(range(len(d.chargers)), key=lambda i: abs(d.chargers[i].peak_w - power_w))
        return best if abs(d.chargers[best].peak_w - power_w) <= 0.25 * d.chargers[best].peak_w else None

    def needed_minutes(self, a, b, power_w=None):
        d = self.data()
        idx = self.identify(power_w)
        if idx is None and d.chargers:
            idx = 0  # sin dato de potencia: el cargador habitual
        tables = ([d.charger_tables[idx]] if idx is not None else []) + [d.global_table]
        return minutes_for(a, b, tables)
