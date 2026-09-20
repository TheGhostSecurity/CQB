import pytest

from cqb_rules_engine import Engine, Action, Operator, Room, generate_rules

RULES = generate_rules("normal")


def team():
    return {"A": Operator("A", "point", "left"),
            "B": Operator("B", "second", "right"),
            "C": Operator("C", "third", "far"),
            "D": Operator("D", "rear", "rear")}


def room():
    return Room(threats=[
        {"id": "T1", "sector": "left",  "armed": True,  "civilian": False},
        {"id": "T2", "sector": "right", "armed": False, "civilian": False},
        {"id": "C1", "sector": "far",   "armed": False, "civilian": True}])


def eng(overrides=None):
    t, r = team(), room()
    if overrides:
        if overrides.get("low_ammo"):
            t[overrides["low_ammo"]] = Operator(overrides["low_ammo"], "op", "left", 2)
    return Engine(RULES, t, r)


def enter(a, call="go", seconds=3, steps=1):
    return Action(a, "enter", {"call": call, "seconds": seconds, "steps_in_doorway": steps})


def bad_names(e):
    return {r[2] for r in e.log if r[3].strip() == "BAD"}


def test_good_run_passes():
    e = eng()
    for a in [Action("A", "slice_pie"),
              enter("A"), enter("B"),
              Action("A", "engage", {"target": "T1", "sector": "left"}),
              Action("B", "engage", {"target": "T2", "sector": "right"}),
              Action("D", "hold", {"facing_back": True})]:
        e.step(a)
    assert not e.failed
    assert e.score > 100
    # both hostiles neutralized; the civilian is never engaged
    assert [t["id"] for t in e.room.threats] == ["C1"]


def test_enter_without_slice_penalized():
    e = eng()
    e.step(enter("A"))
    assert "Slice the pie" in bad_names(e)


def test_wrong_stack_order_penalized():
    e = eng()
    e.step(Action("A", "slice_pie"))
    e.step(enter("B"))
    assert "Stack order" in bad_names(e)


def test_speed_rule_threshold():
    e = eng()
    e.step(Action("A", "slice_pie"))
    e.step(enter("A", seconds=4))
    assert "Speed" not in bad_names(e)
    e2 = eng()
    e2.step(Action("A", "slice_pie"))
    e2.step(enter("A", seconds=5))
    assert "Speed" in bad_names(e2)


def test_civilian_shot_is_fatal():
    e = eng()
    e.step(Action("A", "slice_pie"))
    e.step(enter("A"))
    e.step(enter("B"))
    e.step(Action("A", "engage", {"target": "C1", "sector": "far"}))
    assert e.failed
    assert "Protect civilians" in bad_names(e)
    # the fatal rule should have applied its full -100 penalty
    assert any(r[2] == "Protect civilians" and r[4] == -100 for r in e.log)


def test_low_ammo_entry_penalized():
    e = eng(overrides={"low_ammo": "A"})
    e.step(Action("A", "slice_pie"))
    e.step(enter("A"))
    assert "Ammo check" in bad_names(e)


def test_reload_restores_ammo():
    e = eng(overrides={"low_ammo": "A"})
    e.step(Action("A", "reload", {"call": "reloading"}))
    assert e.team["A"].ammo == 30


def test_threat_priority_armed_first():
    e = eng()
    e.step(Action("A", "slice_pie"))
    e.step(enter("A"))
    e.step(Action("A", "engage", {"target": "T2", "sector": "right"}))  # unarmed while T1 armed
    assert "Threat priority" in bad_names(e)


def test_sector_discipline():
    e = eng()
    e.step(Action("A", "slice_pie"))
    e.step(enter("A"))
    e.step(Action("A", "engage", {"target": "T1", "sector": "left"}))   # own sector: clean
    assert "Sector discipline" not in bad_names(e)
    e2 = eng()
    e2.step(Action("A", "slice_pie"))
    e2.step(enter("A"))
    e2.step(Action("A", "engage", {"target": "T2", "sector": "right"}))  # other sector, own not clear
    assert "Sector discipline" in bad_names(e2)


def test_no_flagging():
    e = eng()
    e.step(Action("A", "slice_pie"))
    e.step(enter("A"))
    e.step(enter("B"))
    e.step(Action("A", "engage", {"target": "T1", "sector": "left", "muzzle_on_teammate": True}))
    assert "No flagging" in bad_names(e)


def test_reload_requires_call_for_reward():
    e = eng()
    e.step(Action("A", "reload", {"call": "reloading"}))
    assert "Call your reload" not in bad_names(e)
    e2 = eng()
    e2.step(Action("A", "reload", {"call": ""}))
    assert "Call your reload" in bad_names(e2)


def test_hold_rear_requires_facing_back():
    e = eng()
    e.step(Action("D", "hold", {"facing_back": False}))
    assert "Rear security" in bad_names(e)


def test_rules_export_round_trip(tmp_path):
    from cqb_rules_engine import export_rules, load_rules
    p = tmp_path / "rules.json"
    export_rules(RULES, str(p))
    loaded = load_rules(str(p))
    assert len(loaded) == len(RULES)
    assert loaded[0].id == RULES[0].id


@pytest.mark.parametrize("diff,mult", [("easy", 0.5), ("normal", 1.0), ("hard", 1.5)])
def test_difficulty_scales_penalties(diff, mult):
    rules = generate_rules(diff)
    assert next(r for r in rules if r.id == "R10").penalty == int(100 * mult)
    assert next(r for r in rules if r.id == "R06").penalty == int(20 * mult)