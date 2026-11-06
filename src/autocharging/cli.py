"""Linea de comandos: autocharging [--probe | --dry-run | --once | --report]."""
import argparse
import json
import logging
import logging.handlers
import os
import time
from pathlib import Path

from . import __version__
from .advice import build_report
from .config import Config, ha_credentials
from .controller import Controller
from .ha import HABattery, HAClient, HAError, HAPlug
from .history import History
from .learning import Learner
from .plug import Plug
from .remote import RemoteStore, start_remote_server
from .rules import load_rules
from .selftest import discover, format_discovery, run_cycle_test, run_selftest

log = logging.getLogger("autocharging")


def setup_logging():
    if log.handlers:      # ya configurado
        return
    logfile = os.getenv("ALC_LOG_FILE", "autocharging.log")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%d/%m/%Y %H:%M:%S")
    for h in (logging.StreamHandler(),
              logging.handlers.RotatingFileHandler(logfile, maxBytes=500_000, backupCount=3)):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)


def load_options_json(path):
    """Opciones del add-on de Home Assistant (/data/options.json) -> variables de entorno."""
    with open(path, encoding="utf-8") as fh:
        for key, value in json.load(fh).items():
            if value is None or value == "":
                continue
            os.environ[key.upper()] = {True: "true", False: "false"}.get(value, str(value)) \
                if isinstance(value, bool) else str(value)


def probe(cfg, plug, client):
    if cfg.backend == "tuya":
        dps = plug.read_dps()
        print(json.dumps(dps, indent=2))
        print(f"\nInterruptor (DPS {cfg.switch_dp}): {dps.get(str(cfg.switch_dp))}")
        raw = dps.get(cfg.power_dp)
        if raw is not None:
            print(f"Potencia (DPS {cfg.power_dp}): {raw} -> {float(raw) / cfg.power_scale:.1f} W")
        else:
            print(f"Sin DPS {cfg.power_dp}: busca arriba un valor que cambie al conectar una carga "
                  "y ajusta POWER_DP / POWER_SCALE.")
    if client is None:
        return
    print("\nEntidades de Home Assistant:")
    for label, entity in (("Enchufe", cfg.ha_switch), ("Potencia", cfg.ha_power),
                          ("Bateria", cfg.ha_battery), ("Estado de carga", cfg.ha_battery_state),
                          ("Enchufado", cfg.ha_plugged)):
        if not entity:
            continue
        try:
            st = client.state(entity)
            unit = (st.get("attributes") or {}).get("unit_of_measurement", "")
            seen = st.get("last_reported") or st.get("last_updated")
            print(f"  {label}: {entity} = {st.get('state')} {unit} (ultimo dato: {seen})")
        except HAError as e:
            print(f"  {label}: {entity} -> ERROR: {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="autocharging", description=__doc__)
    parser.add_argument("--probe", action="store_true", help="muestra el estado del enchufe y de las entidades, y sale")
    parser.add_argument("--dry-run", action="store_true", help="decide y registra, pero no conmuta")
    parser.add_argument("--report", action="store_true",
                        help="muestra lo aprendido (cargadores, tiempos) y consejos de salud, y sale")
    parser.add_argument("--discover", nargs="?", const="", metavar="TEXTO",
                        help="lista enchufes, sensores de potencia y baterias de Home Assistant (opcional: filtrar por TEXTO)")
    parser.add_argument("--selftest", action="store_true",
                        help="comprueba Home Assistant, enchufe, potencia y bateria (con --actuate prueba apagar y encender)")
    parser.add_argument("--actuate", action="store_true", help="con --selftest: apaga y enciende el enchufe de verdad")
    parser.add_argument("--test-cycle", action="store_true",
                        help="prueba real: umbrales pegados al nivel actual hasta ver apagar y encender")
    parser.add_argument("--once", action="store_true", help="un solo ciclo y sale")
    parser.add_argument("--env-file", help="ruta a credentials.env (por defecto ./credentials.env)")
    parser.add_argument("--options-json", help="opciones del add-on de Home Assistant (uso interno)")
    parser.add_argument("--version", action="version", version=f"autocharging {__version__}")
    args = parser.parse_args(argv)

    setup_logging()
    if args.options_json:
        load_options_json(args.options_json)
    if args.discover is not None:
        import getpass
        url, token = ha_credentials(args.env_file)
        url = url or input("URL de Home Assistant (por ejemplo http://192.168.1.156): ").strip()
        token = token or getpass.getpass("Token de acceso de larga duracion (no se muestra): ").strip()
        try:
            found = discover(HAClient(url, token), args.discover)
            print(format_discovery(found))
            if not args.discover and len(found["switch"]) > 5:
                print(f"\nHay {len(found['switch'])} enchufes. Filtra por nombre, por ejemplo: autocharging --discover laptop")
            print("\nAviso: elige con cuidado. Algunos enchufes controlan frigorificos, interruptores generales o el router.")
        except HAError as e:
            raise SystemExit(f"No se pudo consultar Home Assistant: {e}")
        return
    cfg = Config.from_env(args.env_file)

    history = History(cfg.history_db) if cfg.history_db else None
    if args.report:
        if history is None:
            raise SystemExit("HISTORY_DB esta vacio: no hay historial que analizar")
        print("\n".join(build_report(Learner(history), cfg)))
        return

    client = HAClient(cfg.ha_url, cfg.ha_token) if cfg.ha_url and cfg.ha_token else None
    plug = HAPlug(cfg, client, args.dry_run) if cfg.backend == "homeassistant" else Plug(cfg, args.dry_run)
    if args.probe:
        return probe(cfg, plug, client)
    if args.selftest or args.test_cycle:
        if client is None:
            raise SystemExit("Esta prueba necesita HA_URL y HA_TOKEN en el archivo de configuracion.")
        if args.selftest:
            checks = run_selftest(cfg, client, plug, actuate=args.actuate)
            raise SystemExit(1 if any(c.status == "FALLO" for c in checks) else 0)
        result = run_cycle_test(cfg, client, plug, ask=input)
        raise SystemExit(0 if result["ok"] else 1)
    battery = HABattery(cfg, client) if cfg.ha_battery and client else None

    rules = []
    if cfg.rules_file and Path(cfg.rules_file).exists():
        try:
            rules = load_rules(cfg.rules_file)
        except ValueError as e:
            raise SystemExit(f"Error en las reglas: {e}")
        log.info("Reglas cargadas desde %s: %s", cfg.rules_file, ", ".join(r.name for r in rules))
    else:
        log.info("Sin %s: se usa la regla unica %.0f-%.0f%%", cfg.rules_file, cfg.low, cfg.high)

    store = RemoteStore()
    if cfg.remote_port:
        start_remote_server(cfg, store)
    learner = Learner(history) if history is not None else None
    controller = Controller(cfg, plug, store, history=history, rules=rules, learner=learner,
                            ha_client=client, ha_battery=battery)
    log.info("Inicio: enchufe=%s, objetivo=%s, bateria=%s, cada %ds%s", cfg.backend, cfg.target,
             "Home Assistant" if battery else ("remoto/local"), cfg.poll,
             " [dry-run]" if args.dry_run else "")
    try:
        while True:
            controller.step()
            if args.once:
                break
            time.sleep(controller.next_sleep())
    except KeyboardInterrupt:
        log.info("Detenido por el usuario (el enchufe se queda como esta)")
