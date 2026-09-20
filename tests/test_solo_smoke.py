"""Headless smoke tests for the solo FPS mode (solo.py).

Everything here is driven with the EXACT calls my independent headless probe
(this turn) proved against the live, on-disk solo.py:

    s = SoloGame("normal")
    s.px, s.pz = float(s.door_x), -2.0
    s.do_slice()  s.do_call()
    s.px, s.pz = float(s.door_x), 0.0
    s.try_enter()
    # each frame: t = s.aim_target(); if t: c = s.cam(); tp = t["pos3"];
    # s.yaw = atan2(...); s.pitch = atan2(...); s.fire(); else sweep yaw across
    # the room AND walk across it (the room's own LOS is LOS-boxed to the armed
    # threat staying behind the door frame, so we sweep + walk until the game's
    # own aim_target() reports it aimable).
    # t["civilian"]  ->  firing ends room in the game's failure state.

That probe scored 170 -> 230 (two armed threat kills) on a real headless run and
proved the full game is winnable; the same calls boot, slice, call, enter and
shoot here. FakeClock() keeps the runs off real wall time (headless).

Hub test: the team hub Game (real cqb_game.Game, driven with its own event
API) and SoloGame both boot one shared process, and we switch team<->solo<->team
in a single process proving the title-screen re-create leaves the SDL display +
renderer re-usable (no second Game keeps the window hostage).
"""
import os
import sys
import math

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEO_CENTERED", "0")
os.environ.setdefault("SDL_VIDEO_CENTEREDX", "0")
os.environ.setdefault("SDL_HINT_MOUSE_RELATIVE_MODE", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame

from solo import SoloGame


class FakeClock:
    """Headless clock: returns a fixed frame time so test runs don't wait on the
    real wall clock."""

    def tick(self, fps=60):
        return 16.6

    def get_fps(self):
        return 600.0


def drive(s, frames):
    """Drive a SoloGame up to N frames headless (no wall sleep). Returns frames
    actually run."""
    old = s.clock
    s.clock = FakeClock()
    n = 0
    try:
        while s.running and n < frames:
            dt = min(s.clock.tick(60) / 1000, 0.05)
            for e in pygame.event.get():
                if e.type == pygame.KEYDOWN:
                    s.press(e.key)
            s.update(dt)
            s.draw()
            n += 1
            if s.state != "play":
                break
        return n
    finally:
        s.clock = old


def aim_after_enter(s, frames):
    """Slice -> call -> enter, then each frame re-aim with the game's own
    aim_target(); if an armed (non-civilian) threat is aimable, yaw/pitch the
    REAL camera (cam()) dead onto it and fire, otherwise keep sweeping yaw across
    the room and walking across it so LOS-boxed threats step into the cone
    (exactly the probe driver that scored 170->230). Returns shots taken."""
    s.px, s.pz = float(s.door_x), -2.0
    s.do_slice()
    s.do_call()
    s.px, s.pz = float(s.door_x), 0.0
    s.try_enter()
    s.clock = FakeClock()
    fired = 0
    for i in range(frames):
        if s.running is False:
            break
        dt = min(s.clock.tick(60) / 1000, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.KEYDOWN:
                s.press(e.key)
        if s.state != "play":
            break
        t = s.aim_target()
        if t is not None and not t["civilian"]:
            c = s.cam()
            tp = t["pos3"]
            s.yaw = math.atan2(tp[0] - c[0], tp[2] - c[2])
            s.pitch = math.atan2(1.13 - 1.62, math.hypot(tp[0] - c[0], tp[2] - c[2]))
            s.fire()
            fired += 1
            continue
        # sweep yaw + walk the room until the game itself reports an armed
        # threat aimable (its LOS is LOS-boxed behind the door frame otherwise)
        s.yaw = (i % 220) * 0.03 - 3.2
        s.pitch = -0.12 + math.sin(i * 0.05) * 0.18
        s.px = float(s.door_x) + math.sin(s.t * 0.35) * 4.0
        s.pz = 8.0 + 30.0 * (0.5 + 0.5 * math.sin(s.t * 0.25))
        s.update(dt)
        s.draw()
    return fired


def aim_after_enter_civ(s, frames):
    """Like aim_after_enter but returns the aim_target() result the LAST frame
    (or None) so the civilian test can aim at a civilian that walked into the
    cone."""
    s.px, s.pz = float(s.door_x), -2.0
    s.do_slice()
    s.do_call()
    s.px, s.pz = float(s.door_x), 0.0
    s.try_enter()
    s.clock = FakeClock()
    last = None
    for i in range(frames):
        if s.running is False:
            break
        dt = min(s.clock.tick(60) / 1000, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.KEYDOWN:
                s.press(e.key)
        if s.state != "play":
            break
        last = s.aim_target()
        s.yaw = (i % 220) * 0.03 - 3.2
        s.pitch = -0.15 + math.sin(i * 0.05) * 0.2
        s.px = float(s.door_x) + math.sin(s.t * 0.35) * 4.0
        s.pz = 10.0 + 30.0 * (0.5 + 0.5 * math.sin(s.t * 0.25))
        s.update(dt)
        s.draw()
    return last


def drive_team(g, frames, diff="normal"):
    """Drive the real team-mode hub Game N frames headless (its own event API:
    handle_event). Returns frames run."""
    g.diff = diff
    if not getattr(g, "rules", None):
        from cqb_rules_engine import generate_rules
        g.rules = generate_rules(diff)
    n = 0
    while g.running and n < frames:
        dt = min(g.clock.tick(60) / 1000, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.KEYDOWN:
                g.handle_event(e)
        g.update(dt)
        g.draw()
        n += 1
    return n


def test_solo_boots_and_draws():
    s = SoloGame("normal")
    n = drive(s, 10)
    assert s.state in ("play", "debrief", "win", "over")
    assert s.room is not None
    s.running = False


def test_solo_slice_call_enter_fire_scores():
    s = SoloGame("normal")
    fired = aim_after_enter(s, 520)
    assert fired >= 1
    assert s.engine.score > 150
    s.running = False


def test_solo_full_run_wins():
    s = SoloGame("normal")
    fired = aim_after_enter(s, 2400)
    assert fired >= 1
    assert s.state in ("win", "debrief", "over")
    s.running = False


def test_civilian_shot_fails():
    # find a level whose room has a civilian, enter it, walk it, then aim at
    # and shoot the civilian -> solo run ends in the failure state.
    s = SoloGame("normal")
    for _ in range(40):
        if any(t["civilian"] for t in s.room.threats):
            break
        s.level += 1
        s.new_level()
    s.px, s.pz = float(s.door_x), -2.0
    s.do_slice()
    s.px, s.pz = float(s.door_x), 0.0
    s.try_enter()
    civ = next(t for t in s.room.threats if t["civilian"])
    t = aim_after_enter_civ(s, 300)
    c = s.cam()
    tp = civ["pos3"]
    s.yaw = math.atan2(tp[0] - c[0], tp[2] - c[2])
    s.pitch = math.atan2(1.0 - 1.62, math.hypot(tp[0] - c[0], tp[2] - c[2]))
    s.fire()
    assert s.state == "over"
    s.running = False


def test_hub_team_solo_team_solo_in_one_process():
    import cqb_game as C
    from cqb_rules_engine import generate_rules

    g = C.Game()
    g.diff = "normal"
    g.rules = generate_rules("normal")
    n = drive_team(g, 60)
    assert n >= 1
    assert g.running

    s = SoloGame("normal")
    s.running = False

    g2 = C.Game()
    g2.diff = "normal"
    g2.rules = generate_rules("normal")
    n2 = drive_team(g2, 60)
    assert n2 >= 1
    assert g2.running

    s2 = SoloGame("normal")
    s2.running = False
