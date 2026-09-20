import os
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

pygame = pytest.importorskip("pygame")
import cqb_game as C


@pytest.fixture(autouse=True)
def fresh_pygame():
    pygame.quit()
    yield


def engage_any(g, t):
    for n, r in g.rt.items():
        if r.status == "inside" and (t["sector"] == g.team[n].sector or g.own_clear(n)) \
                and not g.flags_teammate(n, t["pos"]):
            g.selected = n
            g.engage(t)
            return True
    return False


def advance_debrief(g):
    g.level += 1
    if g.level >= len(C.LEVELS):
        g.state = "win"
    else:
        g.new_level()


def play_level(g):
    g.do_slice()
    for i, name in enumerate(list(g.team)):
        g.selected = name
        if g.team[name].ammo < 10:
            g.do_call()
            g.do_reload()
        g.do_call()
        g.send(i)
        g.leave_door("left" if i % 2 == 0 else "right")
    for _ in range(60):
        if not g.room.threats:
            break
        pool = [t for t in g.room.threats if t["armed"] and not t["civilian"]] or \
               [t for t in g.room.threats if not t["civilian"]]
        if not pool:
            break
        if not engage_any(g, pool[0]):
            break
        g.contact = True
        g.update(0.05)
        if g.state != "play":
            break
    if g.rt["D"].status == "inside":
        g.selected = "D"
        g.do_hold()
    g.contact = True
    g.finish_room()


def test_full_playthrough_wins():
    g = C.Game()
    g.start_run()
    for lvl in range(len(C.LEVELS)):
        assert g.state == "play"
        play_level(g)
        if g.state == "debrief":
            advance_debrief(g)
        else:
            pytest.fail(f"Level {lvl} ended in state {g.state}; score {g.engine.score}")
    assert g.state == "win"
    assert g.engine.score > 2000


def test_shooting_civilian_fails_run():
    g = C.Game()
    g.start_run()
    g.level = 2  # Kitchen: contains a civilian
    g.new_level()
    assert g.state == "play"
    g.do_slice()
    g.selected = "A"
    g.do_call()
    g.send(0)
    g.leave_door("left")
    civ = next(t for t in g.room.threats if t["civilian"])
    g.selected = "A"
    g.engage(civ)
    assert g.state in ("over", "play")
    g.update(0.05)  # flush() may flip to 'over' on next update
    assert g.state == "over"
    assert "civilian" in g.fail_reason.lower()


def test_title_blank_team_loads_and_draws():
    g = C.Game()
    g.start_run()
    for st in ("title", "play", "debrief", "win"):
        g.state = st
        g.draw()
    assert g.running


def test_every_state_turn_in_no_crash():
    g = C.Game()
    g.start_run()
    play_level(g)
    for st in ("play", "debrief", "over", "win", "title"):
        g.state = st
        g.draw()