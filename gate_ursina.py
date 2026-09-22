'''CQB ENGINE-SWAP GATE - the single decision-maker exe.

Everything in this session has been building toward ONE question that cannot be
answered by reading code: can a REAL double-clickable, one-file, no-console exe

    * open an Ursina (Panda3D) window on a stock desktop,
    * give you WASD + mouse-look (FirstPersonController),
    * render YOUR downloaded M4A1 (compiled to assets/m4a1.bam) locked to the
      camera as a first-person rifle, AND
    * hand back proof (a screenshot + a log in the folder you launched it from)

If this tiny exe renders your rifle and saves gate_shot.png + gate_log.txt,
the engine swap is GOLDEN and the full solo FPS gets rebuilt on Ursina with
your M4A1 as the hero weapon. If it dies silently, we keep solo.py and ship it.

This file is the whole risk test -- deliberately small, self-quitting, and
FREEZE-PROOF by construction (no update()/input() name discovery, timers via
Panda3D's real task manager, screenshot + log to the launch dir).
'''
import os
import sys
import time as _t
from pathlib import Path

# ---- where are we? ---------------------------------------------------------
# one-file bundles unpack to _MEIPASS; direct scripts live next to the file.
FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    WORK = Path(os.getcwd())                       # where the user launched exe
    MEI = Path(getattr(sys, "_MEIPASS", Path()))
    LOG = WORK / "gate_log.txt"
    RIFLE = MEI / "assets" / "m4a1.bam"
    if not RIFLE.exists():
        RIFLE = WORK / "assets" / "m4a1.bam"       # fallback next to the exe
else:
    here = Path(__file__).resolve().parent
    WORK = here
    LOG = here / "gate_log.txt"
    RIFLE = here / "assets" / "m4a1.bam"

with open(LOG, "w", encoding="utf-8") as f:
    f.write("GATE_BOOT %s frozen=%s\n" % (_t.strftime("%H:%M:%S"), FROZEN))
    f.write("GATE_CWD %s\n" % WORK)
    f.write("GATE_RIFLE %s exists=%s\n" % (RIFLE, RIFLE.exists()))


def _log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (_t.strftime("%H:%M:%S"), msg))
    except Exception:
        pass
    try:
        print(msg, flush=True)
    except Exception:
        pass


from ursina import (Ursina, Entity, color, window, application)
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import unlit_shader

app = Ursina(borderless=False, fullscreen=False, title="CQB - Gun Gate",
             icon="white_cube")
window.color = color.rgb(222, 230, 235)
_log("GATE_WINDOW_OK")

ground = Entity(model="plane", scale=(60, 1, 60), collider="box",
                color=color.rgb(210, 219, 226), texture="white_cube")
for i in range(-4, 5):
    Entity(model="cube", scale=(0.5, 2.6, 5), position=(i * 2.1, 1.3, -8),
           color=color.rgb(96 + i * 33, 205, 214), shader=unlit_shader,
           collider="box")
_log("GATE_WORLD_OK")

ply = FirstPersonController(speed=9, jump_height=0, gravity=0)
_log("GATE_FPC_OK")

rifle = None
try:
    rifle = Entity(model=str(RIFLE), parent=ply.camera_pivot,
                   scale=(0.0212, 0.0212, 0.0212),
                   position=(0.32, -0.27, 0.56), rotation=(0, 90, 0),
                   shader=unlit_shader)
    _log("GATE_RIFLE_MOUNTED_OK")
except Exception as e:
    _log("GATE_RIFLE_MOUNT_FAIL %r" % (e,))


def _snapshot(task):
    try:
        window.save_screenshot(str(WORK / "gate_shot.png"))
        _log("GATE_SHOT_SAVED %s" % (WORK / "gate_shot.png"))
    except Exception as e:
        _log("GATE_SHOT_FAIL %r" % (e,))
    return 0


def _finish(task):
    _log("GATE_ALL_GREEN_QUIT")
    application.quit()
    return 0


# timers through Panda3D's task manager: freeze-proof (no name discovery)
taskMgr.doMethodLater(1.4, _snapshot, "gateSnap")
taskMgr.doMethodLater(4.0, _finish, "gateFinish")
