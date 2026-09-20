import os, sys, math
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, r"C:\Users\ghost\Desktop\CQB")

import pygame

from solo import SoloGame


class FakeClock:
    def tick(self, fps=60):
        return 16.6

    def get_fps(self):
        return 600.0


s = SoloGame("normal")
s.clock = FakeClock()
s.px, s.pz = float(s.door_x), -2.0
s.do_slice()
s.do_call()
s.px, s.pz = float(s.door_x), 0.0
s.try_enter()
print("state after enter:", s.state, "entered:", s.entered)
print("threats:", len(s.room.threats))
for t in s.room.threats:
    print("  civ=%s armed=%s pos=%s pos3=%s" % (t["civilian"], t.get("armed"), t["pos"], t.get("pos3")))
print("player at", s.px, s.pz, "door", s.door_x)

found = None
# Walk across the room in a grid and sweep yaw/pitch so LOS is not the blocker.
for iy in range(0, 120, 4):
    ang = (iy / 118.0 - 0.5) * 2.4
    for step in range(0, 60):
        for ix in range(0, 60):
            s.px = float(s.door_x) + (ix / 59.0 - 0.5) * 300.0
            s.pz = -110 + step * 4.0
            for pch in (-0.5, -0.1, 0.1, 0.5):
                s.yaw = ang
                s.pitch = pch
                t = s.aim_target()
                if t and not t["civilian"]:
                    found = (s.px, s.pz, ang, pch, t)
                    break
            if found:
                break
        if found:
            break
    if found:
        break

print("found armed LOS threat at:", found)
if found:
    px, pz, yaw, pch, t = found
    s.yaw, s.pitch = yaw, pch
    pre = s.engine.score
    s.fire()
    print("score pre:", pre, "post:", s.engine.score, "state:", s.state)
else:
    print("NO armed target ever aimable -> LOS or cone problem")
s.running = False
