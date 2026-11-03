"""Estimacion del porcentaje integrando la energia medida por el enchufe."""
import time


class Estimator:
    def __init__(self, cfg):
        self.cfg = cfg
        self.pct = cfg.start_pct
        self.last = time.time()

    def update(self, on, power_w):
        now = time.time()
        dt_h = (now - self.last) / 3600
        self.last = now
        if on and power_w is not None:
            self.pct += power_w * dt_h * self.cfg.efficiency / self.cfg.capacity_wh * 100
        elif not on:
            self.pct -= self.cfg.drain_pct_h * dt_h
        self.pct = max(0.0, min(100.0, self.pct))

    def sync(self, pct):
        self.pct = pct
