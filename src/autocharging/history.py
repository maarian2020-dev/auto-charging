"""Historial de muestras en SQLite: base del aprendizaje."""
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Sample:
    ts: float
    pct: Optional[float]
    origin: str
    on: bool
    power: Optional[float]
    plugged: Optional[bool] = None


class History:
    def __init__(self, path, keep_days=180):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS samples ("
                "ts REAL, device TEXT, pct REAL, origin TEXT, on_ INTEGER, power REAL, plugged INTEGER)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts)")
            self.conn.execute("DELETE FROM samples WHERE ts < ?", (time.time() - keep_days * 86400,))
            self.conn.commit()

    def record(self, ts, device, pct, origin, on, power, plugged=None):
        with self.lock:
            self.conn.execute(
                "INSERT INTO samples VALUES (?,?,?,?,?,?,?)",
                (ts, device, pct, origin, int(bool(on)), power,
                 None if plugged is None else int(bool(plugged))))
            self.conn.commit()

    def samples(self, since_ts, device=None) -> List[Sample]:
        query = "SELECT ts, pct, origin, on_, power, plugged FROM samples WHERE ts >= ?"
        args = [since_ts]
        if device:
            query += " AND device = ?"
            args.append(device)
        with self.lock:
            rows = self.conn.execute(query + " ORDER BY ts", args).fetchall()
        return [Sample(r[0], r[1], r[2], bool(r[3]), r[4], None if r[5] is None else bool(r[5]))
                for r in rows]
