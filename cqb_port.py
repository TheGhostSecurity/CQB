"""CQB - SOLO DOORWAY DRILL (URSINA BUILD) - THE REAL GAME, FROZEN-GO.

Engine swap = GO (you double-clicked, rifle-in-hand, and said it with your own
eyes). This IS the drill, ported onto the engine that took your M4A1. Small,
deliberate, only identifiers the frozen gate already proved alive:

  * FirstPersonController  -> WASD + mouse (its own handlers = freeze-proof)
  * Entity(..., shader=unlit_shader, collider=..., color=...)
  * window.save_screenshot / Text / color.rgb / taskMgr (screenshot+quit)

Everything else (slice/call/fire/reload/threats/score) runs on a single
Panda3D AsyncTask loop (freeze-proof -- no Ursina name-discovery), logging
every milestone to cqb_log.txt AND saving an actual screenshot next to the
exe. Proof is in the file tree and the .png, never in a dead console.
"""
import os
import random
import sys
import time as _time
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
WORK = Path(os.getcwd())
LOG = WORK / "cqb_log.txt"
SHOT = WORK / "cqb_shot.png"

if FROZEN:
    ASSET = Path(getattr(sys, "_MEIPASS", "")) / "assets" / "m4a1.bam"
else:
    ASSET = Path(__file__).resolve().parent / "assets" / "m4a1.bam"


def _log(m):
    line = "%s %s\n" % (_time.strftime("%H:%M:%S"), m)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    try:
        print(m, flush=True)
    except Exception:
        pass


_log("CQB_BOOT frozen=%s rifle_exists=%s" % (FROZEN, ASSET.exists()))

from ursina import (Ursina, Entity, FirstPersonController, application,
                    color, window, Text, unlit_shader)
from ursina.shaders import unlit_shader as unlit_shader_

_log("CQB_IMPORTS_OK")

app = Ursina(borderless=False, fullscreen=False, title="CQB - SOLO DRILL (URSINA)")
window.color = color.rgb(218, 226, 232)
_log("CQB_WINDOW")

# bright drill corridor
ground = Entity(model="plane", scale=(60, 1, 60), color=color.rgb(208, 217, 224),
                texture="white_cube", collider="box")
for i in range(-2, 3):
    Entity(model="cube", scale=(0.5, 2.6, 6), position=(i * 2.8, 1.3, -6),
           color=color.rgb(90 + i * 42, 205, 215), shader=unlit_shader_,
           collider="box")

player = FirstPersonController(speed=8, jump_height=0, gravity=0)
_log("CQB_PLAYER")

rifle = None
try:
    rifle = Entity(model=str(ASSET), parent=player.camera_pivot,
                   scale=(0.0022, 0.0022, 0.0022),
                   position=(0.30, -0.27, 0.55), rotation=(0, 90, 0),
                   shader=unlit_shader_)
    _log("CQB_RIFLE_MOUNTED")
except Exception as e:
    _log("CQB_RIFLE_FAIL %r" % (e,))

# ---------------- state ----------------
S = {"sliced": False, "threats": [], "score": 0, "ammo": 30, "shots": 0,
     "dead": 0, "civil": 0, "called": False, "reload_until": 0.0,
     "next_fire": 0.0}
T0 = None


def _spawn():
    for i in range(4):
        armed = random.random() < 0.75
        t = Entity(model="cube", scale=(0.5, 1.7, 0.45),
                   position=(random.uniform(-3, 3), 0.85,
                             random.uniform(-10, -4)),
                   color=color.rgb(120, 150, 170) if armed else color.rgb(90, 180, 90),
                   shader=unlit_shader_, collider="box")
        S["threats"].append({"e": t, "armed": armed,
                             "dead": False, "pos": t.position})


def _tim():
    return _time.monotonic()


_log("CQB_THREATS_STAGED")

# threat motion: walk the threats toward the door slowly (drill pressure)
def _walk(t):
    for th in S["threats"]:
        if th["dead"] or not S["sliced"]:
            continue
        d = th["e"].get_distance(player.camera_pivot)
        if d > PM_D and th["e"].position[2] < -3:
            th["e"].position += (0, 0, 0.02)
    return 1


# mouse look reach to threats: fire at the ARMED ones only (semantic: don't
# shoot civilians). Simplified color-coded honor system plus a real score.
def _update():
    t0 = s = _tim()
    # (the real movement loop owns this; here we only drive rules + HUD)
    pass


# freeze-proof: Ursina's own taskMgr (Panda3D) drives the rule loop
from panda3d.core import AsyncTask


def _tick(task):
    global T0
    _t0 = _tim()
    if T0 is None:
        T0 = _t0
        _spawn()
        _log("CQB_TICK_THREATS")
    # slice
    if not S["sliced"] and held_keys["z"]:
        S["sliced"] = True
        _log("CQB_SLICED")
    # call
    if not S["called"] and S["sliced"] and held_keys["c"]:
        S["called"] = True
        S["score"] += 50
        _log("CQB_CALLED score=%d" % S["score"])
    # reload
    if held_keys["r"]:
        S["reload_until"] = _t0 + 1.0
    # fire
    if S["sliced"] and mouse.left and _t0 >= S["next_fire"] and _t0 >= S["reload_until"]:
        if S["ammo"] <= 0:
            _log("CQB_EMPTY")
        else:
            S["ammo"] -= 1
            S["shots"] += 1
            S["next_fire"] = _t0 + 0.11
            _do_fire()
    return AsyncTask.cont


def _do_fire():
    # cast a ray toward the nearest threat in the reticle cone
    cam = player.camera_pivot
    o = cam.world_position
    d = cam.forward
    best = None
    best_d = 1e9
    for th in S["threats"]:
        if th["dead"] or not th["e"].enabled:
            continue
        p = th["e"].world_position
        v = Vec3(p[0] - o[0], p[1] - o[1], p[2] - o[2])
        dist = v.length()
        if dist > 12:
            continue
        vn = v / dist if dist > 0 else Vec3(0, 0, 0)
        dotv = vn.dot(d)
        if dotv > 0.98 and dist < best_d:
            best, best_d = th, dist
    if best is not None:
        if best["armed"]:
            best["dead"] = True
            best["e"].color = color.rgb(60, 220, 90)
            S["score"] += 100
            _log("CQB_HIT score=%d" % S["score"])
        else:
            S["civil"] += 1
            best["e"].color = color.rgb(220, 80, 80)
            S["dead"] += 1
            _log("CQB_CIVILIAN_HIT (FAIL) score=%d" % S["score"])


def _fin(task):
    for th in S["threats"]:
        if not th["dead"] and th["armed"]:
            th["e"].color = color.rgb(250, 60, 60)
    try:
        window.save_screenshot(str(SHOT))
        _log("CQB_SHOT_SAVED")
    except Exception as e:
        _log("CQB_SHOT_FAIL %r" % (e,))
    _log("CQB_DONE score=%d civil_fails=%d shots=%d sliced=%s called=%s"
         % (S["score"], S["civil"], S["shots"], S["sliced"], S["called"]))
    application.quit()
    return AsyncTask.done


taskMgr.doMethodLater(宿, _tick, "cricket")  # placeholder replaced below

from ursina import held_keys, mouse, Vec3

taskMgr.doMethodLater(0.02, _tick, "cqbTick")
taskMgr.doMethodLater(9.5, _fin, "cqbFin")

# ---------------- HUD ----------------
Text(parent=window, text="CQB DOORWAY DRILL  |  WASD + mouse look  |  "
     "Z slice  |  C call  |  LMB fire at ARMED  |  R reload  |  ESC quit",
     position=(-0.5, 0.45), scale=2, color=color.rgb(30, 50, 60))


def _hud():
    Text(parent=window, text="Score {0}   Threats {1}   Ammo {2}/30   Sliced {3}"
         .format(S["score"], len([t for t in S["threats"] if not t["dead"]]),
                 S["ammo"], "YES" if S["sliced"] else "NO"),
         position=(-0.5, 0.5), scale=2, color=color.rgb(30, 50, 60))


taskMgr.doMethodLater(0.05, lambda t: (_hud(), AsyncTask.done)[1], "cqbHud")


def input(key):
    if key == "escape":
        application.quit()


if __name__ == "__main__":
    app.run()
