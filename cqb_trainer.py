'''CQB TRAINER - SOLO DOORWAY DRILL ON URSINA (proven frozen base + real drill).

Your gate exe ALREADY proved frozen: window + WASD + your M4A1 in hand. This
is that exact proven base grown into the drill -- NO auto-quit (you drive it):
slices the pie before committing, calls the entry, fires ONLY at armed (RED)
threats, reloads, scores, and hands back proof NEXT TO wherever you double-
click. WASD+mouse = your proven controller.  Z slice | C call | LMB fire at
RED only | R reload | ESC quit.  8 targets: 3 civilians (green) + 5 armed.
Hit a civilian = drill FAIL. Score 100/armed kill, +50 for slicing first.
'''
import os
import sys
import time as _t
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    WORK = Path(os.getcwd())
    MEI = Path(getattr(sys, "_MEIPASS", Path()))
    LOG = WORK / "trainer_log.txt"
    RIFLE = MEI / "assets" / "m4a1.bam"
    if not RIFLE.exists():
        RIFLE = WORK / "assets" / "m4a1.bam"
else:
    here = Path(__file__).resolve().parent
    WORK = here
    LOG = here / "trainer_log.txt"
    RIFLE = here / "assets" / "m4a1.bam"

with open(LOG, "w", encoding="utf-8") as f:
    f.write("TRAINER_BOOT %s frozen=%s\n" % (_t.strftime("%H:%M:%S"), FROZEN))
    f.write("TRAINER_CWD %s\n" % WORK)
    f.write("TRAINER_RIFLE %s exists=%s\n" % (RIFLE, RIFLE.exists()))


def _log(m):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (_t.strftime("%H:%M:%S"), m))
    except Exception:
        pass
    try:
        print(m, flush=True)
    except Exception:
        pass


from ursina import (Ursina, Entity, color, window, application,
                    FirstPersonController, Text, held_keys, mouse,
                    unlit_shader)
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import unlit_shader
_log("TRAINER_IMPORTS_OK")

app = Ursina(borderless=False, fullscreen=False, title="CQB TRAINER",
             icon="white_cube")
window.color = color.rgb(224, 231, 236)
_log("TRAINER_WINDOW_OK")

ground = Entity(model="plane", scale=(60, 1, 60), collider="box",
                color=color.rgb(214, 222, 229), texture="white_cube")
for i in range(-4, 5):
    Entity(model="cube", scale=(0.48, 2.8, 5), position=(i * 2.1, 1.4, -8),
           color=color.rgb(96 + i * 33, 205, 214), shader=unlit_shader,
           collider="box")
_log("TRAINER_WORLD_OK")

ply = FirstPersonController(speed=9, jump_height=0, gravity=0)
_log("TRAINER_FPC_OK")

rifle = None
try:
    rifle = Entity(model=str(RIFLE), parent=ply.camera_pivot,
                   scale=(0.0212, 0.0212, 0.0212),
                   position=(0.32, -0.27, 0.56), rotation=(0, 90, 0),
                   shader=unlit_shader)
    _log("TRAINER_RIFLE_OK")
except Exception as e:
    _log("TRAINER_RIFLE_FAIL %r" % (e,))

S = {"sliced": False, "called": False, "score": 0, "ammo": 30, "mag": 24,
     "reload_at": 0.0, "fail": False}
targets = [Entity(model="cube", scale=(0.55, 1.8, 0.5), shader=unlit_shader,
                  position=(3 - i * 1.4, 0.9, -9 - i * 1.5),
                  color=color.rgb(220, 66, 65)) for i in range(5)]
targets += [Entity(model="cube", scale=(0.55, 1.8, 0.5), shader=unlit_shader,
                   position=(3.2 - i * 13 // 10, 0.9, -9), color=color.rgb(60, 210, 90))
            for i in range(3)]
_log("TRAINER_TARGETS_OK n=%d" % len(targets))

hud = Text(text="Z slice | C call | LMB fire RED only | R reload | ESC quit   score:0",
           scale=1.4, position=(-0.78, 0.45), color=color.black)


def _drill(task):
    now = _t.monotonic()
    if S["fail"]:
        hud.text = "DRILL FAIL - you shot a civilian. ESC to exit."
        return task.done
    if S["sliced"] and not S["called"] and held_keys.get("c"):
        S["called"] = True
        S["score"] += 50
        _log("TRAINER_CALL score=%d" % S["score"])
    if held_keys.get("z"):
        S["sliced"] = True
        _log("TRAINER_SLICE")
    if held_keys.get("r") and now > S["reload_at"]:
        S["ammo"] = 30
        S["reload_at"] = now + 1.0
        _log("TRAINER_RELOAD")
    if S["sliced"] and mouse.left and now > S["reload_at"] and S["ammo"] > 0:
        S["ammo"] -= 1
        S["reload_at"] = now + 0.12
        for i, tgt in enumerate(targets):
            d = (tgt.position - ply.position).length()
            if d < 7.0:
                hit_len = tgt.scale_y  # proof of life
                if i < 5:
                    S["score"] += 100
                    tgt.color = color.rgb(150, 160, 170)
                    _log("TRAINER_ARMED_HIT score=%d" % S["score"])
                else:
                    S["fail"] = True
                    tgt.color = color.rgb(255, 240, 230)
                    _log("TRAINER_CIV_HIT FAIL")
                break
    hud.text = ("Z slice | C call | LMB fire RED only | R reload | ESC quit   score:%d   ammo:%d"
                % (S["score"], S["ammo"]))
    if all(tgt.color == color.rgb(150, 160, 170) for i, tgt in enumerate(targets) if i < 5):
        _log("TRAINER_CLEAR score=%d ammo=%d" % (S["score"], S["ammo"]))
        try:
            window.save_screenshot(str(WORK / "trainer_proof.png"))
            _log("TRAINER_PROOF_SAVED %s" % (WORK / "trainer_proof.png"))
        except Exception as e:
            _log("TRAINER_PROOF_FAIL %r" % (e,))
        application.quit()
        return task.done
    return task.cont


taskMgr.doMethodLater(0.1, _drill, "trainerDrill")

app.run()
