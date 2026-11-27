from datetime import datetime

import pytest

from autocharging.rules import Rule, active_rule, default_rule, load_rules, parse_time

TUE_0400 = datetime(2026, 11, 3, 4, 0)   # martes
MON_2300 = datetime(2026, 11, 2, 23, 0)  # lunes


def test_overnight_window_uses_start_day():
    rule = Rule("noche", start=parse_time("22:00"), end=parse_time("07:30"), days=frozenset({0}))  # solo lunes
    assert rule.matches(MON_2300)
    assert rule.matches(TUE_0400)                        # madrugada del martes = noche del lunes
    assert not rule.matches(datetime(2026, 11, 3, 23, 0))  # martes por la noche: no


def test_first_matching_rule_wins_and_default(cfg):
    night = Rule("noche", start=parse_time("22:00"), end=parse_time("07:30"))
    day = Rule("dia", start=parse_time("07:30"), end=parse_time("22:00"))
    assert active_rule([night, day], datetime(2026, 11, 3, 12, 0), default_rule(cfg)).name == "dia"
    assert active_rule([], datetime(2026, 11, 3, 12, 0), default_rule(cfg)).name == "por-defecto"


def test_deadline_rolls_to_next_day():
    rule = Rule("n", mode="ready_by", ready_by=parse_time("07:30"))
    assert rule.deadline(datetime(2026, 11, 3, 4, 0)) == datetime(2026, 11, 3, 7, 30)
    assert rule.deadline(datetime(2026, 11, 3, 23, 0)) == datetime(2026, 11, 4, 7, 30)


def test_load_example_file(tmp_path):
    rules = load_rules("rules.example.toml")
    assert [r.name for r in rules] == ["noche", "dia"]
    assert rules[0].mode == "ready_by" and rules[0].hold_low == 90


def test_invalid_rules_are_rejected(tmp_path):
    bad = tmp_path / "r.toml"
    bad.write_text('[[rule]]\nmode = "ready_by"\n')            # falta ready_by
    with pytest.raises(ValueError):
        load_rules(bad)
    bad.write_text('[[rule]]\nlow = 90\nhigh = 50\n')           # umbrales invertidos
    with pytest.raises(ValueError):
        load_rules(bad)
    bad.write_text('[[rule]]\nlwo = 10\n')                      # errata en la clave
    with pytest.raises(ValueError):
        load_rules(bad)
