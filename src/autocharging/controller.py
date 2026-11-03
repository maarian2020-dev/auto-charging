"""Logica de decision: cuando encender y apagar el enchufe."""
import logging
import re
import time
from datetime import datetime, timedelta

from .estimator import Estimator
from .ha import HAError
from .learning import minutes_for
from .plug import PlugError
from .rules import active_rule, default_rule

log = logging.getLogger("autocharging")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "local"


class Controller:
    def __init__(self, cfg, plug, store, history=None, rules=None, learner=None, clock=None,
                 ha_client=None, ha_battery=None):
        self.cfg, self.plug, self.store = cfg, plug, store
        self.history, self.rules, self.learner = history, rules or [], learner
        self.ha_client, self.ha_battery = ha_client, ha_battery
        self.clock = clock or datetime.now
        self.est = Estimator(cfg)
        self.errors = 0
        self.on_since = None
        self.max_power = 0.0
        self.low_count = 0
        self.plugged = None
        self.topup_deadline = None   # carga final ya iniciada para esta hora limite
        self.last_pct = None
        self.last_action = ""
        self.warned_no_power = False

    # ------------------------------------------------------------ lecturas
    def _note_power(self, power):
        if power is None and not self.warned_no_power:
            log.warning("El enchufe no reporta potencia: sin deteccion por consumo ni aprendizaje de "
                        "cargadores. Revisa POWER_DP (Tuya) o HA_POWER_ENTITY (Home Assistant).")
            self.warned_no_power = True

    def _percent(self):
        self.plugged = None
        if self.ha_battery is not None:
            reading = self.ha_battery.read()
            if reading is not None:
                self.plugged = reading[1]
                return reading[0], "ha"
        if self.cfg.target != "local":
            state = self.store.get_state(self.cfg.target, self.cfg.remote_max_age)
            if state is not None:
                self.plugged = state[1]
                return state[0], "remoto"
        elif self.ha_battery is None:
            import psutil
            battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
            if battery is not None:
                self.plugged = battery.power_plugged
                return float(battery.percent), "local"
        return self.est.pct, "estimado"

    def _track_session(self, on, power):
        """Devuelve True si la caida de potencia indica fin de carga."""
        now = time.time()
        if not on:
            self.on_since, self.max_power, self.low_count = None, 0.0, 0
            return False
        if self.on_since is None:
            self.on_since = now
        if power is None:
            return False
        self.max_power = max(self.max_power, power)
        floor = max(self.cfg.full_abs_w, self.cfg.full_ratio * self.max_power)
        if self.max_power >= self.cfg.min_charge_w and power < floor:
            self.low_count += 1
        else:
            self.low_count = 0
        return self.low_count >= self.cfg.full_samples and now - self.on_since >= 300

    def _needed(self, a, b):
        """Minutos necesarios para ir de a% a b% (aprendidos, o valores genericos)."""
        if self.learner is not None:
            return self.learner.needed_minutes(a, b, power_w=self.max_power or None)
        return minutes_for(a, b, [])

    # ------------------------------------------------------------ decision
    def decide(self, pct, origin, on, taper, minutes_on, rule=None, now=None):
        """Devuelve (quiere_encendido | None, motivo)."""
        c = self.cfg
        rule = rule or default_rule(c)
        now = now or self.clock()
        if rule.mode == "ready_by":
            cap, hi, lo = max(c.abs_max, rule.target), rule.hold_high, rule.hold_low
        else:
            cap, hi, lo = max(c.abs_max, rule.high), rule.high, rule.low

        if on and pct >= cap:
            return False, f"limite de seguridad {cap:.0f}%"
        if on and origin == "estimado" and taper:
            return False, "fin de carga detectado por caida de potencia"
        if on and minutes_on >= c.max_charge_min:
            return False, f"tiempo maximo de carga ({c.max_charge_min:.0f} min)"

        if rule.mode == "ready_by":
            needed = self._needed(pct, rule.target)
            deadline = rule.deadline(now)
            start_at = deadline - timedelta(minutes=needed * 1.15 + 10)
            if now >= start_at:
                self.topup_deadline = deadline       # cierra el plan: no vuelve a la fase de espera
            if self.topup_deadline == deadline:      # fase de carga final programada
                if pct >= rule.target:
                    return (False, f"objetivo {rule.target:.0f}% alcanzado") if on else (None, "")
                if on:
                    return None, ""
                if pct <= rule.target - 2:
                    return True, (f"plan '{rule.name}': listo a las {rule.ready_by:%H:%M}, "
                                  f"faltan ~{needed:.0f} min de carga")
                return None, ""

        if on and pct >= hi:
            return False, f"alcanzado {hi:.0f}% (regla '{rule.name}')"
        if not on and pct <= lo:
            return True, f"bateria baja: {pct:.0f}% (regla '{rule.name}')"
        return None, ""

    # ------------------------------------------------------------ Home Assistant
    def _notify(self, message):
        if self.ha_client is None or not self.cfg.ha_notify:
            return
        try:
            self.ha_client.notify(self.cfg.ha_notify, message)
        except HAError as e:
            log.warning("No se pudo enviar la notificacion: %s", e)

    def _publish(self, pct, origin, on, power, rule):
        """Expone el estado como sensor en Home Assistant (sensor.autocharging_<dispositivo>)."""
        if self.ha_client is None:
            return
        attrs = {"friendly_name": f"Auto Charging {self.cfg.target}", "unit_of_measurement": "%",
                 "origen": origin, "enchufe": "on" if on else "off", "regla": rule.name,
                 "potencia_w": None if power is None else round(power, 1),
                 "enchufado": self.plugged, "ultima_accion": self.last_action}
        try:
            self.ha_client.set_state(f"sensor.autocharging_{_slug(self.cfg.target)}", round(pct), attrs)
        except HAError as e:
            log.debug("No se pudo publicar el sensor: %s", e)

    # ------------------------------------------------------------ ciclo
    def step(self):
        try:
            state = self.plug.read()
        except PlugError as e:
            self.errors += 1
            log.warning("Enchufe sin respuesta (%d seguidos): %s", self.errors, e)
            if self.errors == 5:
                self._notify("El enchufe no responde: no se puede controlar la carga.")
            return
        self.errors = 0
        on, power = state.on, state.power_w
        self._note_power(power)
        taper = self._track_session(on, power)
        self.est.update(on, power)
        pct, origin = self._percent()
        self.last_pct = (pct, origin)
        if origin != "estimado":
            self.est.sync(pct)
        now = self.clock()
        rule = active_rule(self.rules, now, default_rule(self.cfg))
        if self.history is not None:
            self.history.record(time.time(), self.cfg.target, pct, origin, on, power, self.plugged)
        log.info("bateria=%.0f%% (%s) enchufe=%s potencia=%s regla=%s", pct, origin,
                 "ON" if on else "OFF", f"{power:.1f}W" if power is not None else "n/d", rule.name)

        minutes_on = (time.time() - self.on_since) / 60 if self.on_since else 0
        want, reason = self.decide(pct, origin, on, taper, minutes_on, rule, now)
        if want is not None:
            log.info("Accion: %s -> %s", "ENCENDER" if want else "APAGAR", reason)
            if self.plug.set_state(want):
                self.last_action = f"{'ON' if want else 'OFF'}: {reason}"
                if not want and "potencia" in reason:
                    self.est.sync(100.0)  # recalibra: carga completa
                if not want and reason.startswith("objetivo"):
                    self._notify(f"Bateria al {pct:.0f} %: ya puedes desenchufar.")
            else:
                log.error("No se pudo confirmar el cambio de estado del enchufe")
        self._publish(pct, origin, on, power, rule)

    def next_sleep(self):
        pct, origin = self.last_pct or self._percent()
        if origin != "estimado":
            now = self.clock()
            rule = active_rule(self.rules, now, default_rule(self.cfg))
            edges = ((rule.hold_low, rule.hold_high) if rule.mode == "ready_by" else (rule.low, rule.high))
            if min(abs(pct - e) for e in edges) <= 3:
                return min(self.cfg.poll, 20)
            if rule.mode == "ready_by" and rule.deadline(now) - now <= timedelta(hours=3):
                return min(self.cfg.poll, 30)
        return self.cfg.poll
