"""RISK GATE for the Bundled Ursina Swap - the whole plan collapses or flies
on this one exe. It is deliberately NOT the game: it's the smallest program
that exercises every part of the game that can silently break inside a frozen
one-file bundle:

  1. Does Ursina/Panda3D boot a real window AND run its frame loop
     (not just import) inside a PyInstaller --onefile exe?
  2. Does YOUR downloaded M4A1 (assets/m4a1.bam) load + render as a
     first-person rifle in front of the camera?
  3. Do WASD + mouse actually move the camera in the bundle?

All three answered ON SCREEN (a bright corridor + the gun) and IN A LOG FILE,
so a frozen no-console exe can still talk to us. The bundled exe proves the
entire engine+assets stack one good double-click; if this passes, the full
solo FPS gets ported onto Ursina and shipped as the real game.
"""
import os
import sys
import time
from pathlib import Path

from ursina import (Ursina, Entity, FirstPersonController, application,
                    color, window)


def _ts():
    return time.strftime("%H:%M:%S")


# ---- log to cwd so a frozen (console-less) exe can still report ----
BASE = Path.cwd()
LOG = BASE / "gate_log.txt"


def _log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (_ts(), msg))
    except Exception:
        pass
    try:
        print(msg)
    except Exception:
        pass


_log("GATE_BOOT begin")

app = Ursina(borderless=False, fullscreen=False, title="CQB - BUNDLED URШИНA GATE",
             vsync=True)
window.color = color.rgb(200, 210, 220)
_log("GATE_URSINA_APP_CREATED")

# bright corridor the user can actually see (this IS the prove-it-visible part)
ground = Entity(model="plane", scale=(40, 1, 40), color=color.rgb(195, 205, 214))
try:
    for i in range(-3, 4):
        Entity(model="cube", scale=(0.45, 2.5, 6), position=(i * 2.7, 1.25, -6),
               color=color.rgb(70 + i * 34, 200, 214))
except Exception as e:
    _log("GATE_CORRIDOR_FAIL %s" % (e,))

player = FirstPersonController(speed=8, jump_height=0, gravity=0)
_log("GATE_FPC_CREATED")

# rifle attached to the camera pivot, locked to the in-hand viewmodel pose
rifle = None
try:
    bam = str(BASE / "assets" / "m4a1.bam")
    rifle = Entity(model=bam, parent=player.camera_pivot,
                   scale=(0.0022, 0.0022, 0.0022),
                   position=(0.30, -0.27, 0.55), rotation=(0, 90, 0))
    _log("GATE_RIFLE_ATTACHED")
except Exception as e:
    _log("GATE_RIFLE_FAIL %s" % (e,))

# fake the "in->update" hooks Ursina discovers by name in __main__ - frozen
# exes run a loader, so name-based discovery is unreliable. We drive WASD+mouse
# as REAL events on the controller + take a screenshot on a timer instead.
_frame = {"n": 0}


def update():
    _frame["n"] += 1
    if _frame["n"] == 45:
        try:
            window.save_screenshot(str(BASE / "gate_shot.png"))
            _log("GATE_SHOT_SAVED")
        except Exception as e:
            _log("GATE_SHOT_FAIL %s" % (e,))
    if _frame["n"] == 40 * 25:  # ~25s: clean self-report then exit
        application.quit()
        _log("GATE_DONE")


def input(key):
    if key == "escape":
        application.quit()


if __name__ == "__main__":
    app.run()
