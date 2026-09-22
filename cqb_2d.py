'''CQB 2D - THE SIMPLE DOORWAY DRILL (raw pygame, the layer your FIRST frozen
exe already proved --- no ursina, no panda, no .bam, no name discovery).

Ported straight from solo.py's proven 2D drill onto a bright top-down doorway:
   WASD move | mouse aim | Z slice-the-pie | C call | LMB fire at RED (armed)
   targets only | R reload | ESC quit | NO auto-cancel (you drive it).
3 civilians (GREEN - never shoot) + 5 armed (RED). Shoot a civilian = drill
FAIL, score 0. +100 / armed kill. Reload-at will auto-reload on R.

Prove = proof_2d.png + cqb2d_log.txt written NEXT to whereever you launch.
Frozen-proof by construction (same rule that froze your 19.5MB exe): timers
via pygame.time.get_ticks (real clock, no discovery), screenshot via
pygame.image.save to the folder it launched from.
'''
import os
import sys
import time as _t
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    WORK = Path(os.getcwd())          # where the user double-clicked the exe
    LOG = WORK / "cqb2d_log.txt"
    SHOT = WORK / "proof_2d.png"
else:
    here = Path(__file__).resolve().parent
    WORK = here
    LOG = here / "cqb2d_log.txt"
    SHOT = here / "proof_2d.png"

with open(LOG, "w", encoding="utf-8") as f:
    f.write("CQB2D_BOOT %s frozen=%s\n" % (_t.strftime("%H:%M:%S"), FROZEN))
    f.write("CQB2D_WORK %s\n" % WORK)


def _log(m):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (_t.strftime("%H:%M:%S"), m))
    except Exception:
        pass


import pygame

pygame.init()
SCREEN = pygame.display.set_mode((1280, 720))
pygame.display.set_caption("CQB - 2D DOORWAY DRILL")
FONT = pygame.font.SysFont(None, 32)
_log("CQB2D_WINDOW_OK")

WHITE = (240, 246, 248)
GROUND = (212, 220, 226)
RED = (200, 55, 55)
GREEN = (70, 190, 90)
DARK = (40, 46, 54)

S = {"sliced": False, "called": False, "score": 0, "ammo": 30,
     "reload_at": 0, "fail": False, "targets": [], "armed": 0, "civ": 0}
for i in range(8):
    x = 200 + (i % 4) * 90 + 45
    y = 130 + (i // 4) * 380
    armed = i < 5
    S["targets"].append({"x": x, "y": y, "armed": armed, "dead": False,
                         "w": 46, "h": 70})
    S["armed" if armed else "civ"] += 1
_log("CQB2D_TARGETS armed=%d civ=%d" % (S["armed"], S["civ"]))

ply = {"x": 640, "y": 660, "dx": 0, "dy": 0}
last = _t.monotonic()

running = True
while running:
    dt = _t.monotonic() - last
    last = _t.monotonic()
    now = pygame.time.get_ticks()

    for e in pygame.event.get():
        if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN
                                     and e.key == pygame.K_ESCAPE):
            running = False

    keys = pygame.key.get_pressed()
    sp = 340 * dt
    if keys[pygame.K_w]:
        ply["y"] -= sp
    if keys[pygame.K_s]:
        ply["y"] += sp
    if keys[pygame.K_a]:
        ply["x"] -= sp
    if keys[pygame.K_d]:
        ply["x"] += sp
    ply["x"] = max(20, min(1260, ply["x"]))
    ply["y"] = max(20, min(700, ply["y"]))

    if keys[pygame.K_z]:
        S["sliced"] = True
    if keys[pygame.K_c] and S["sliced"] and not S["called"]:
        S["called"] = True
        S["score"] += 50
        _log("CQB2D_CALL score=%d" % S["score"])
    if keys[pygame.K_r] and now > S["reload_at"]:
        S["ammo"] = 30
        S["reload_at"] = now + 900
        _log("CQB2D_RELOAD ammo=%d" % S["ammo"])

    mx, my = pygame.mouse.get_pos()
    fire = pygame.mouse.get_pressed()[0] and S["sliced"] and S["ammo"] > 0
    if fire and not S["fail"]:
        S["ammo"] -= 1
        hit = None
        bestd = 9999
        for t in S["targets"]:
            if t["dead"]:
                continue
            cx, cy = t["x"] + t["w"] / 2, t["y"] + t["h"] / 2
            d = (cx - mx) ** 2 + (cy - my) ** 2
            if d < 40000 and d < bestd:
                bestd = d
                hit = t
        if hit:
            if hit["armed"]:
                hit["dead"] = True
                S["score"] += 100
                _log("CQB2D_HIT_ARMED score=%d" % S["score"])
            else:
                S["fail"] = True
                _log("CQB2D_CIV_HIT FAIL")

    SCREEN.fill(GROUND)
    for i in range(8):
        t = S["targets"][i]
        col = (150, 156, 162) if t["dead"] else (RED if t["armed"] else GREEN)
        if i < 4:
            Entity2D_NONE = None
        pygame.draw.rect(SCREEN, col, (int(t["x"]), int(t["y"]),
                                       int(t["w"]), int(t["h"])))
        pygame.draw.rect(SCREEN, DARK, (int(t["x"]) - 2, int(t["y"]) - 2,
                                        int(t["w"]) + 4, int(t["h"]) + 4), 2)

    pygame.draw.circle(SCREEN, (30, 60, 120), (int(ply["x"]), int(ply["y"])), 16)
    pygame.draw.line(SCREEN, (240, 60, 60), (ply["x"], ply["y"]), (mx, my), 4)

    status = "SCORE:%d  AMMO:%d  %s" % (
        S["score"], S["ammo"],
        "FAIL - civilian hit" if S["fail"] else
        ("slice=Z call=C fire=LMB(RED) reload=R   sliced:%s called:%s"
         % ("Y" if S["sliced"] else "N", "Y" if S["called"] else "N")))
    SCREEN.blit(FONT.render(status, True, DARK), (16, 12))

    pygame.display.flip()

pygame.image.save(SCREEN, str(SHOT))
_log("CQB2D_SHOT %s" % SHOT)
pygame.quit()
