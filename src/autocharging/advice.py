"""Informe y consejos de carga a partir de lo aprendido (orientativo)."""
import statistics
import time

from .learning import MAX_GAP, circular_mean_minutes, clock, minutes_for, minutes_of_day


def health_metrics(samples):
    known = high = 0.0
    low_events = 0
    gained = 0.0
    prev = None
    for s in samples:
        if s.pct is None or s.origin == "estimado":
            prev = None
            continue
        if prev is not None and 0 < s.ts - prev.ts <= MAX_GAP:
            w = s.ts - prev.ts
            known += w
            if prev.pct >= 95:
                high += w
            if prev.pct >= 10 and s.pct < 10:
                low_events += 1
            if s.pct > prev.pct:
                gained += s.pct - prev.pct
        prev = s
    return {"known_s": known, "high_share": high / known if known else 0.0,
            "low_events": low_events, "cycles": gained / 100}


def departure_minutes(samples):
    """Hora del dia (min) en que se desenchufa tras llevar 2 h o mas enchufado."""
    out, since, last = [], None, None
    for s in samples:
        if s.plugged is None:
            since = last = None
            continue
        if last is not None and s.ts - last.ts > 3600:
            since = None
        if s.plugged:
            if since is None:
                since = s.ts
        else:
            if since is not None and last is not None and last.plugged and last.ts - since >= 7200:
                out.append(minutes_of_day(s.ts))
            since = None
        last = s
    return out


def build_report(learner, cfg, now=None):
    now = now or time.time()
    d = learner.data(now)
    if len(d.samples) < 30:
        return ["Todavia no hay datos suficientes. Deja el programa funcionando unos dias "
                "(cuantos mas ciclos de carga, mejor aprende)."]
    days = max((d.samples[-1].ts - d.samples[0].ts) / 86400, 0.01)
    lines = [f"Datos analizados: {len(d.samples)} muestras en {days:.1f} dias, "
             f"{len(d.sessions)} sesiones de carga."]

    if d.chargers:
        lines += ["", "Cargadores detectados (por potencia y hora; no puedo saber el lugar exacto):"]
        total = sum(c.n for c in d.chargers)
        for i, c in enumerate(d.chargers):
            if i == 0 and c.n >= 3:
                tag = "habitual"
            elif c.n < max(2, 0.2 * total):
                tag = "puntual (otro cargador, coche u otro lugar)"
            else:
                tag = "frecuente"
            start = clock(c.typical_start) if c.typical_start is not None else "?"
            lines.append(f"  - ~{c.peak_w:.0f} W [{tag}]: {c.n} sesiones, inicio tipico ~{start}, "
                         f"duracion mediana {c.median_minutes:.0f} min")
        habitual = d.chargers[0]
        if len(d.chargers) > 1:
            for c in d.chargers[1:]:
                if c.peak_w > 1.5 * habitual.peak_w and c.n < habitual.n:
                    lines.append(f"    Nota: el cargador de ~{c.peak_w:.0f} W es mucho mas rapido que el "
                                 "habitual; ocasionalmente no pasa nada, pero evita usarlo a diario si "
                                 "el dispositivo se calienta.")

        tables = [d.charger_tables[0], d.global_table]
        lines += ["", "Tiempo de carga estimado con el cargador habitual:"]
        for a, b in ((10, 80), (20, 100), (50, 100), (80, 100)):
            lines.append(f"  - de {a} % a {b} %: ~{minutes_for(a, b, tables):.0f} min")

    dep = departure_minutes(d.samples)
    lines.append("")
    if len(dep) >= 3:
        mean = circular_mean_minutes(dep)
        spread = statistics.pstdev(((m - mean + 720) % 1440) - 720 for m in dep)
        lines.append(f"Hora de desconexion habitual: ~{clock(mean)} ({len(dep)} veces, "
                     f"variacion +-{spread:.0f} min).")
        lines.append(f"  Sugerencia: ready_by = \"{clock((mean - max(10, spread)) % 1440)}\" en rules.toml.")
    else:
        lines.append("Hora de desconexion: aun no hay datos. El dispositivo debe informar de 'plugged' "
                     "(el portatil lo hace solo; en el movil, el script de Termux).")

    m = health_metrics(d.samples)
    lines += ["", "Salud de la bateria (orientativo):"]
    if m["known_s"] < 3600:
        lines.append("  - Sin porcentaje real suficiente para valorarla (solo estimaciones).")
        return lines
    lines.append(f"  - Tiempo al 95-100 %: {m['high_share'] * 100:.0f} %")
    lines.append(f"  - Descargas por debajo del 10 %: {m['low_events']}")
    lines.append(f"  - Ciclos equivalentes por dia: {m['cycles'] / days:.2f}")
    tips = []
    if m["high_share"] > 0.35:
        tips.append("Pasa mucho tiempo casi llena. Usa una regla ready_by con nivel de espera mas bajo "
                    "(p. ej. hold 80-90 %) para que el ultimo tramo se cargue justo antes de desenchufar.")
    if m["low_events"] >= 3:
        tips.append("Hay descargas profundas repetidas; enchufa antes de llegar al 10-20 %.")
    if m["cycles"] / days > 1.5:
        tips.append("Mas de 1,5 ciclos al dia: considera cargas cortas intermedias en lugar de vaciar y llenar.")
    if not tips:
        tips.append("Tus habitos de carga son buenos; no hay nada que corregir por ahora.")
    lines += [f"  * {t}" for t in tips]
    return lines
