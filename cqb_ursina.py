"""CQB - SOLO DOORWAY DRILL (URSINA COPY, FROZEN-PROOF).

Engine swap is GO (you held YOUR M4A1 in a real frozen exe and said it with
your own eyes). This is the actual drill rebuilt on that engine: bright
corridor, WASD + mouse, slice the pie (Z) -> call (C) -> step through ->
fire ONLY armed threats (LMB) -> reload (R) -> survive. Civilians must never
be shot. Score + lives + 12s auto-proof (screenshot + log next to the exe),
Escape quits.

Everything here uses identifiers the frozen gate already proved alive:
  * FirstPersonController  (WASD+mouse are bound inside ITS OWN class, so a
    frozen bundle keeps them)
  * held_keys dict         (ursina fill-literally-dict-keys, discovery-proof)
  * taskMgr.doMethodLater  (Panda3D real scheduler: freeze-proof timers)
  * window.save_screenshot (frozen-proof proof that the exe can SEE)
Nothing name-discovered, nothing that dies when __main__ is the bootloader.
"""
import os
import random
import sys
import time as _t
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    WORK = Path(os.getcwd())
    MEI = Path(getattr(sys, "_MEIPASS", "")) if hasattr(sys, "_MEIPASS") else Path()
    BASE = MEI if (MEI / "assets" / "m4a1.bam").exists() else WORK
    LOG = WORK / "cqb_log.txt"
    SHOT = WORK / "cqb_shot.png"
else:
    her