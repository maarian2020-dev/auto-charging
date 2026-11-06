"""Autodiagnostico y pruebas reales guiadas contra Home Assistant (--discover, --selftest, --test-cycle)."""
import time
from dataclasses import dataclass, replace

from .controller import Controller
from .ha import HABattery, HAError
from .plug import PlugError
from .remote import RemoteStore

OK, WARN, FAIL = "OK", "AVISO", "FALLO"


@dataclass
class Check:
    status: str
    name: str
    detail: str = ""


# ------------------------------------------------------------------ descubrimiento
def discover(client, text=""):
    """Entidades utiles para la configuracion: enchufes, sensores de potencia y de bateria."""
    text = text.lower()
    found = {"switch": [], "power": [], "battery": []}
    for s in client.states():
        eid = s.get("entity_id", "")
        attrs = s.get("attributes") or {}
        name = attrs.get("friendly_name", "")
        if text and text not in eid.lower() and text not in name.lower():
            continue
        unit = attrs.get("unit_of_measurement", "")
        row = (eid, str(s.get("state")), name, unit)
        domain = eid.split(".")[0]
        if domain == "switch":
            found["switch"].append(row)
        elif domain == "sensor" and (attrs.get("device_class") == "power" or unit in ("W", "kW")):
            found["power"].append(row)
        elif domain == "sensor" and (attrs.get("device_class") == "battery" or "battery" in eid):
            found["battery"].append(row)
    return {k: sorted(v) for k, v in found.items()}


def format_discovery(found):
    titles = {"switch": ("Enchufes (HA_SWITCH_ENTITY)", "estado"),
              "power": ("Sensores de potencia (HA_POWER_ENTITY)", "valor"),
              "battery": ("Baterias de moviles/portatiles (HA_BATTERY_ENTITY)", "valor")}
    lines = []
    for key, (title, col) in titles.items():
        lines.append(f"\n{title}:")
        if not found[key]:
            lines.append("  (ninguna)")
        for eid, state, name, unit in found[key]:
            lines.append(f"  {eid}  [{col}: {state} {unit}]".rstrip() + (f"  - {name}" if name else ""))
    return "\n".join(lines)


# ------------------------------------------------------------------- lectura de bateria
def read_battery(cfg, client):
    """(porcentaje, enchufado, origen) de la fuente que usara el programa, o None."""
    if cfg.ha_battery:
        r = HABattery(cfg, client).read()
        return (r[0], r[1], "ha") if r else None
    if cfg.target == "local":
        try:
            import psutil
            b = psutil.sensors_battery()
        except ImportError:
            return None
        return (float(b.percent), b.power_plugged, "local") if b else None
    return None


# -------------------------------------------------------------------------- selftest
def run_selftest(cfg, client, plug, actuate=False, ask=input, sleep=time.sleep, out=print):
    checks = []

    def add(status, name, detail=""):
        checks.append(Check(status, name, detail))
        out(f"[{status}] {name}" + (f": {detail}" if detail else ""))

    # 1. Home Assistant y token
    try:
        client.ping()
        add(OK, "Home Assistant responde y acepta el token", client.base)
    except HAError as e:
        add(FAIL, "Home Assistant no responde", str(e))
        return checks

    # 2. Enchufe
    try:
        state = plug.read()
    except PlugError as e:
        add(FAIL, "No se puede leer el enchufe", str(e))
        return checks
    add(OK, "Enchufe leido", f"{cfg.ha_switch} esta {'ON' if state.on else 'OFF'}")

    # 3. Potencia
    if state.power_w is None:
        add(WARN, "Sin sensor de potencia", "no habra deteccion de fin de carga por consumo ni aprendizaje de cargadores")
    elif state.on and state.power_w < 5:
        add(WARN, "Enchufe ON pero casi sin consumo", f"{state.power_w:.1f} W: ¿esta el cargador conectado al portatil?")
    else:
        add(OK, "Potencia leida", f"{state.power_w:.1f} W")

    # 4. Bateria
    batt = read_battery(cfg, client)
    if batt is None:
        add(FAIL, "No se puede leer la bateria", "revisa TARGET_DEVICE / HA_BATTERY_ENTITY (el portatil debe tener bateria)")
    else:
        add(OK, "Bateria leida", f"{batt[0]:.0f} % (origen: {batt[2]}), enchufado: {batt[1]}")
        if state.on and (state.power_w or 0) > 10 and batt[1] is False:
            add(WARN, "Incoherencia", "el enchufe consume pero el equipo dice que no esta enchufado")

    # 5. Umbrales
    add(OK, "Umbrales", f"low={cfg.low:.0f}  high={cfg.high:.0f}  abs_max={cfg.abs_max:.0f}")

    # 6. Actuacion (opcional)
    if actuate:
        if batt is None or batt[0] < 30:
            add(WARN, "Prueba de actuacion omitida", "la bateria debe ser al menos 30 %")
        elif not state.on:
            add(WARN, "Prueba de actuacion omitida", "el enchufe debe estar ON al empezar")
        elif ask("Voy a APAGAR el enchufe unos segundos y a encenderlo de nuevo. ¿Continuar? (s/n): ").strip().lower() \
                not in ("s", "si", "sí", "y", "yes"):
            add(WARN, "Prueba de actuacion cancelada por el usuario")
        else:
            ok_on = False
            try:
                t0 = time.time()
                ok_off = plug.set_state(False)
                lat_off = time.time() - t0
                add(OK if ok_off else FAIL, "Apagado confirmado" if ok_off else "El apagado no se confirmo",
                    f"{lat_off:.1f} s")
                sleep(8)
                p_off = plug.read()
                if p_off.power_w is not None:
                    add(OK if p_off.power_w < 5 else WARN, "Consumo con el enchufe apagado", f"{p_off.power_w:.1f} W")
                b_off = read_battery(cfg, client)
                if b_off and b_off[1] is not None:
                    add(OK if b_off[1] is False else WARN, "El equipo detecta que se corto la carga",
                        f"enchufado: {b_off[1]}")
            finally:
                t1 = time.time()
                ok_on = plug.set_state(True)       # siempre se deja el enchufe encendido
                lat_on = time.time() - t1
            add(OK if ok_on else FAIL, "Encendido confirmado" if ok_on else "El encendido NO se confirmo: enciende el enchufe a mano",
                f"{lat_on:.1f} s")
            if max(lat_off, lat_on) > 8:
                add(WARN, "Respuesta lenta", "mas de 8 s en confirmar; usa un intervalo de comprobacion amplio")

    fails = sum(c.status == FAIL for c in checks)
    warns = sum(c.status == WARN for c in checks)
    out("\nRESULTADO: " + ("NO APTO" if fails else "APTO CON AVISOS" if warns else "APTO"))
    return checks


# ---------------------------------------------------------------------- ciclo real
def run_cycle_test(cfg, client, plug, max_minutes=45, step_s=15, sleep=time.sleep, out=print, tick=None):
    """Corte real con umbrales pegados al nivel actual: espera ver APAGAR y despues ENCENDER.

    Siempre deja el enchufe encendido al terminar. `tick(on)` es un gancho solo para pruebas.
    """
    batt = read_battery(cfg, client)
    if batt is None:
        out("[FALLO] No se puede leer la bateria: prueba cancelada.")
        return {"ok": False, "events": []}
    pct = batt[0]
    if not 25 <= pct <= 90:
        out(f"[FALLO] Bateria al {pct:.0f} %: para esta prueba debe estar entre 25 y 90 %.")
        return {"ok": False, "events": []}
    try:
        if not plug.read().on:
            out("[FALLO] El enchufe debe estar ON al empezar.")
            return {"ok": False, "events": []}
    except PlugError as e:
        out(f"[FALLO] No se puede leer el enchufe: {e}")
        return {"ok": False, "events": []}

    low, high = max(1.0, pct - 1), min(100.0, pct + 2)
    test_cfg = replace(cfg, low=low, high=high, abs_max=max(cfg.abs_max, high + 2), poll=step_s)
    battery = HABattery(test_cfg, client) if test_cfg.ha_battery else None
    controller = Controller(test_cfg, plug, RemoteStore(), ha_client=client, ha_battery=battery)
    out(f"Prueba de ciclo: bateria {pct:.0f} %, se apagara al llegar a {high:.0f} % y se encendera al bajar a {low:.0f} %.")
    out("Usa el equipo con normalidad (navegar, video) para que baje antes. Ctrl+C para cancelar.")

    events, last_on = [], True
    deadline = time.time() + max_minutes * 60
    try:
        while time.time() < deadline:
            controller.step()
            try:
                now_on = plug.read().on
            except PlugError:
                now_on = last_on
            if now_on != last_on:
                pct_now = controller.last_pct[0] if controller.last_pct else float("nan")
                events.append(("ON" if now_on else "OFF", pct_now))
                out(f"  -> enchufe {'ENCENDIDO' if now_on else 'APAGADO'} con bateria {pct_now:.0f} %")
                last_on = now_on
            if [e[0] for e in events][:2] == ["OFF", "ON"]:
                break
            if tick:
                tick(now_on)
            sleep(step_s)
    except KeyboardInterrupt:
        out("Cancelado por el usuario.")
    finally:
        if not plug.set_state(True):
            out("[AVISO] No se pudo confirmar el encendido final: ENCIENDE EL ENCHUFE A MANO.")
    ok = [e[0] for e in events][:2] == ["OFF", "ON"]
    out("\nRESULTADO: " + ("APTO: el programa corto y reanudo la carga." if ok else
                           "INCOMPLETO: no se vio el ciclo completo (APAGAR y despues ENCENDER)."))
    return {"ok": ok, "events": events}
