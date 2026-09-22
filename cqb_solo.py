"""CQB SOLO -- DOORWAY DRILL ON URINA (the swap you approved, shipped frozen).

The gate exe you double-clicked PROVED the engine renders YOUR M4A1 in-hand in
a one-file frozen exe. This is the real drill, written tiny on purpose, using
ONLY identifiers the frozen gate already proved alive, and driven entirely by
freeze-proof machinery:

    * movement  -> Ursina's own FirstPersonController (WASD+mouse; it bills
                   its own event handlers, so it works frozen)
    * fire/slice/call/reload -> read from ursina's held_keys dict + mouse
                   (these are populated by Ursina's real event loop, not by
                   name-discovery, so they're alive in a one-file exe)
    * timers/screenshot/quit -> Panda3D's taskMgr (AsyncTask), not module-name
                   update()/input() which die silently when frozen
    * all proof -> cqb_log.txt + cqb_shot.png written next to the exe

MISSION: you're the doorway man on a bright corridor. Threats are armed
civilians stood in the open AFTER you pie the door.

    WASD + mouse - move & look        Z - slice the pie (open the threat)
    C - call status on the radio      LMB - fire at ARM  threats
    R - reload                        mouse - look
    ESC - quit

DO NOT shoot a civilian (grey). Only armed threats (they're hostile). If you
drop a civilian, you fail the drill.
"""
import os, random, sys, time as _t
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
_boot = Path(os.getcwd()) if FROZEN else Path(__file__).resolve().parent
LOG = _boot / "cqb_log.txt"
SHOT = _boot / "cqb_shot.png"
BAM = (Path(getattr(sys, "_MEIPASS", "")) / "assets" / "m4a1.bam"
       if FROZEN else _boot / "assets" / "m4a1.bam")
ASSET = BAM if BAM.exists() else (_boot / "assets" / "m4a1.bam")

_t0 = _t.monotonic


def _log(m):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (_t.strftime("%H:%M:%S"), m))
    except Exception:
        pass


_log("CQB_BOOT frozen=%s bam=%s exists=%s" % (FROZEN, ASSET, ASSET.exists()))

from ursina import (Ursina, Entity, FirstPersonController, application, color,
                    window, Text, held_keys, mouse, unlit_shader)
from panda3d.core import AsyncTask

app = Ursina(borderless=False, fullscreen=False, title="CQB - SOLO DRILL")
window.color = color.rgb(226, 232, 238)
_log("CQB_WINDOW_OK")

ground = Entity(model="plane", scale=(60, 1, 60), color=color.rgb(205, 214, 222),
                texture="white_cube", collider="box")
for i in range(-2, 3):
    Entity(model="cube", scale=(0.6, 2.3, 5), position=(i * 3.1, 1.15, -6),
           color=color.rgb(70 + i * 38, 200, 214), shader=unlit_shader,
           collider="box")
_log("CQB_CORRIDOR_OK")

ply = FirstPersonController(speed=8, jump_height=0, gravity=0)
_log("CQB_PLAYER_OK")

rifle = Entity(model=str(ASSET), parent=ply.camera_pivot, scale=(0.0212, 0.0212, 0.0212),
               position=(0.32, -0.27, 0.56), rotation=(0, 90, 0), shader=unlit_shader)
_log("CQB_RIFLE_OK")

_sliced = {"v": False, "call": False, "ammo": 30, "score": 0, "shots": 0}

threats = []


def _spawn():
    for i in range(弱4):
        pass