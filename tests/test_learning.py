import time

from autocharging.advice import build_report, departure_minutes
from autocharging.history import History, Sample
from autocharging.learning import Learner, cluster_chargers, split_sessions


def charge_samples(t0, watts, minutes=60, start_pct=20, min_per_point=2.0):
    return [Sample(t0 + i * 60, start_pct + int(i / min_per_point), "remoto", True, watts, True)
            for i in range(minutes)]


def test_sessions_and_charger_clusters():
    base = time.time() - 10 * 86400
    samples = []
    for day in range(4):                                        # 4 noches con ~40 W
        samples += charge_samples(base + day * 86400, 40 + day)
    samples += charge_samples(base + 5 * 86400, 65)             # 1 carga puntual a 65 W
    sessions = split_sessions(samples)
    assert len(sessions) == 5
    chargers = cluster_chargers(sessions)
    assert len(chargers) == 2
    assert chargers[0].n == 4 and 40 <= chargers[0].peak_w <= 44    # el habitual primero


def test_learned_time_replaces_default():
    history = History(":memory:")
    t0 = time.time() - 3600
    for s in charge_samples(t0, 40, minutes=59, start_pct=20, min_per_point=2.0):
        history.record(s.ts, "movil", s.pct, s.origin, s.on, s.power, s.plugged)
    learner = Learner(history)
    # 2 min por punto aprendidos (el generico seria 1 min/punto): 20 -> 40 = ~40 min
    assert 35 <= learner.needed_minutes(20, 40, power_w=40) <= 45


def test_departure_time_learned_from_plugged_flag():
    base = time.time() - 5 * 86400
    samples = []
    for day in range(4):
        t = base + day * 86400
        samples += [Sample(t + i * 600, 80, "remoto", True, 30, True) for i in range(30)]   # 5 h enchufado
        samples.append(Sample(t + 30 * 600, 100, "remoto", False, 0, False))                # desenchufa
    assert len(departure_minutes(samples)) == 4


def test_report_with_and_without_data():
    history = History(":memory:")
    learner = Learner(history)
    assert "datos suficientes" in build_report(learner, None)[0]
    t0 = time.time() - 3600 * 5
    for i in range(300):
        history.record(t0 + i * 60, "movil", 100, "remoto", False, 0, True)   # siempre al 100 %
    text = "\n".join(build_report(Learner(history), None))
    assert "95-100" in text and "ready_by" in text
