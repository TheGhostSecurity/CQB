"""
CQB Trainer - Pygame front end for cqb_rules_engine.py
------------------------------------------------------
A top-down, real-time tactical TRAINING GAME. Every decision you make is
scored by the rules engine (rewards for good drills, penalties for mistakes).

Run:  python cqb_game.py
"""
import math
import random
from collections import Counter
from dataclasses import dataclass

import pygame
from pygame.math import Vector2 as V2

from cqb_rules_engine import Engine, Action, Operator, Room, generate_rules

# ------------------------------------------------------------------ layout
W, H, MAP_W, FPS = 1100, 720, 780, 60
ROOM = pygame.Rect(60, 50, 660, 330)
CORR = pygame.Rect(60, 388, 660, 130)
DOOR_W = 76

GREEN, RED, YEL = (90, 220, 130), (240, 90, 90), (240, 210, 90)
WHITE, GREY, DIM = (235, 235, 240), (150, 155, 165), (95, 100, 112)
OP_COL = {"A": (80, 150, 255), "B": (90, 210, 120), "C": (240, 200, 70), "D": (190, 120, 240)}

LEVELS = [
    dict(name="Bedroom",    armed=1, unarmed=0, civ=0, fire=12.0),
    dict(name="Office",     armed=2, unarmed=0, civ=1, fire=10.0),
    dict(name="Kitchen",    armed=2, unarmed=1, civ=1, fire=9.0),
    dict(name="Warehouse",  armed=3, unarmed=1, civ=2, fire=8.0),
    dict(name="Final Room", armed=3, unarmed=2, civ=2, fire=7.0),
]


# ------------------------------------------------------------- helpers
def sector_of(x):
    third = ROOM.width / 3
    if x < ROOM.left + third:
        return "left"
    if x > ROOM.right - third:
        return "right"
    return "far"


def make_room(cfg):
    door_x = random.randint(ROOM.left + 150, ROOM.right - 210)
    kinds = ["armed"] * cfg["armed"] + ["unarmed"] * cfg["unarmed"] + ["civ"] * cfg["civ"]
    random.shuffle(kinds)
    third = ROOM.width / 3
    xr = {"left": (ROOM.left + 35, ROOM.left + third - 10),
          "far": (ROOM.left + third + 10, ROOM.right - third - 10),
          "right": (ROOM.right - third + 10, ROOM.right - 35)}
    order = random.sample(["left", "far", "right"], 3)
    threats = []
    for i, kind in enumerate(kinds):
        sec = order[i % 3]
        for _ in range(60):
            x = random.randint(int(xr[sec][0]), int(xr[sec][1]))
            y = random.randint(ROOM.top + 35, ROOM.bottom - 130)
            if all(math.hypot(x - t["pos"][0], y - t["pos"][1]) > 70 for t in threats):
                break
        threats.append(dict(id=f"T{i + 1}", sector=sec, armed=(kind == "armed"),
                            civilian=(kind == "civ"), pos=(x, y)))
    return door_x, Room(threats=threats)


def make_team():
    team = {"A": Operator("A", "point", "left", random.randint(14, 30)),
            "B": Operator("B", "second", "right", random.randint(14, 30)),
            "C": Operator("C", "third", "far", random.randint(14, 30)),
            "D": Operator("D", "rear", "rear", random.randint(14, 30))}
    if random.random() < 0.6:                       # someone is low on ammo
        team[random.choice("ABCD")].ammo = random.randint(4, 9)
    return team


@dataclass
class Rt:                                           # per-operator runtime state
    pos: V2
    target: V2
    status: str = "corridor"                        # corridor | door | inside
    call: str = ""
    seconds: float = 0.0
    sent_t: float = 0.0
    slot_dir: str = ""
    held: bool = False
    busy_until: float = 0.0


# ------------------------------------------------------------------ game
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("CQB Trainer - Rules Engine Edition")
        self.screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        mono = "consolas,dejavusansmono,couriernew,monospace"
        self.f13 = pygame.font.SysFont(mono, 13)
        self.f16 = pygame.font.SysFont(mono, 16)
        self.f22 = pygame.font.SysFont(mono, 22, bold=True)
        self.f40 = pygame.font.SysFont(mono, 40, bold=True)
        self.running = True
        self.state = "title"
        self.diff = "normal"
        self.coach_on = True
        self.rules = generate_rules(self.diff)
        self.engine = None
        self.feed, self.floaters, self.shots = [], [], []
        self.run_bad = Counter()
        self.fail_reason = ""
        self.flash = 0.0

    # ------------------------------------------------------ run / level
    def start_run(self):
        self.rules = generate_rules(self.diff)
        self.engine, self.level = None, 0
        self.run_bad, self.feed, self.floaters = Counter(), [], []
        self.fail_reason = ""
        self.new_level()

    def new_level(self):
        self.cfg = LEVELS[self.level]
        self.door_x, self.room = make_room(self.cfg)
        self.team = make_team()
        if self.engine is None:
            self.engine = Engine(self.rules, self.team, self.room)
        else:
            self.engine.team, self.engine.room = self.team, self.room
        self.log_seen = len(self.engine.log)
        self.rt = {}
        for i, n in enumerate(self.team):
            p = V2(self.door_x + 50 + i * 46, CORR.top + 30)
            self.rt[n] = Rt(pos=V2(p), target=V2(p))
        self.selected, self.pending_call = None, ""
        self.t, self.first_press, self.last_press = 0.0, None, None
        self.contact, self.threat_t = False, self.cfg["fire"]
        self.down, self.shots, self.hits = [], [], 0
        self.room_bad = Counter()
        self.debrief = []
        self.say("Stack up. Slice the pie (Z), then send the point man (1).")
        self.state = "play"

    @property
    def doorway(self):
        return V2(self.door_x, ROOM.bottom - 8)

    def say(self, text, col=WHITE):
        self.msg_text, self.msg_col = text, col

    # ---------------------------------------------------------- queries
    def door_operator(self):
        return next((n for n, r in self.rt.items() if r.status == "door"), None)

    def inside_ops(self):
        return [n for n, r in self.rt.items() if r.status in ("door", "inside")]

    def threat_state(self, t):
        if self.room.sliced:
            return "id"
        ops = self.inside_ops()
        if not ops:
            return "hidden"
        tp = V2(t["pos"])
        return "id" if any(self.rt[o].pos.distance_to(tp) < 170 for o in ops) else "unknown"

    def own_clear(self, name):
        sec = self.team[name].sector
        return sec != "rear" and not any(t["sector"] == sec for t in self.room.threats)

    def flags_teammate(self, name, target):
        a, b = self.rt[name].pos, V2(target)
        ab = b - a
        L2 = ab.length_squared()
        if L2 == 0:
            return False
        for n, r in self.rt.items():
            if n == name or r.status not in ("door", "inside"):
                continue
            s = (r.pos - a).dot(ab) / L2
            if 0 < s < 1 and (a + ab * s).distance_to(r.pos) < 22:
                return True
        return False

    def slot_pos(self, direction, idx):
        if direction == "left":
            return V2(ROOM.left + 48 + idx * 40, ROOM.bottom - 58)
        if direction == "right":
            return V2(ROOM.right - 48 - idx * 40, ROOM.bottom - 58)
        return V2(self.door_x + [0, 42, -42, 84][idx % 4], ROOM.bottom - 100)

    # --------------------------------------------------------- scoring UI
    def flush(self, actor=""):
        eng = self.engine
        rows = eng.log[self.log_seen:]
        self.log_seen = len(eng.log)
        if not rows:
            return
        total = sum(r[4] for r in rows)
        self.feed.append((f"{rows[0][0]} {rows[0][1]}: {total:+d}", GREEN if total >= 0 else RED))
        pos = V2(self.rt[actor].pos) if actor in self.rt else V2(MAP_W // 2, ROOM.centery)
        self.floaters.append(dict(text=f"{total:+d}", pos=pos + V2(0, -26),
                                  col=GREEN if total >= 0 else RED, ttl=1.6))
        k = 0
        for r in rows:
            if r[3].strip() == "BAD":
                self.feed.append((f"  x {r[2]} {r[4]:+d}", RED))
                self.run_bad[r[2]] += 1
                self.room_bad[r[2]] += 1
                k += 1
                self.floaters.append(dict(text=f"{r[2]} {r[4]:+d}", pos=pos + V2(20, -26 + k * 16),
                                          col=RED, ttl=1.6))
                if r[2] == "Protect civilians":
                    self.fail_reason = "You fired on a civilian."
        self.feed = self.feed[-15:]
        if eng.failed and self.state == "play":
            self.fail_reason = self.fail_reason or "Score fell below the minimum."
            self.state = "over"

    # ------------------------------------------------------------ actions
    def do_slice(self):
        if self.room.sliced:
            return self.say("Room already sliced.", GREY)
        self.engine.step(Action("A", "slice_pie"))
        self.say("Pie sliced - contacts identified. Now call out (X) and send the stack.", GREEN)

    def do_call(self):
        self.pending_call = "Entering!"
        self.say("CALL READY - it is spoken on your next entry or reload.", YEL)

    def send(self, idx):
        name = list(self.team)[idx]
        r = self.rt[name]
        if r.status != "corridor":
            return self.say(f"{name} is already in the room.", GREY)
        if self.door_operator():
            return self.say("Doorway is blocked - move the operator off it (arrow keys)!", RED)
        now = self.t
        seconds = 0.0 if self.last_press is None else now - self.last_press
        if self.first_press is None:
            self.first_press, self.contact, self.threat_t = now, True, self.cfg["fire"]
        self.last_press = now
        r.status, r.target, r.sent_t = "door", V2(self.doorway), now
        r.seconds, r.call, self.pending_call = seconds, self.pending_call, ""
        self.selected = name
        self.say(f"{name} is at the door - MOVE OFF THE FATAL FUNNEL (arrow keys)!", YEL)

    def leave_door(self, direction):
        n = self.door_operator()
        if not n:
            return
        r = self.rt[n]
        steps = 1 if self.t - r.sent_t <= 1.8 else 3
        idx = sum(1 for o in self.rt.values() if o.status == "inside" and o.slot_dir == direction)
        r.slot_dir, r.target, r.status = direction, self.slot_pos(direction, idx), "inside"
        self.engine.step(Action(n, "enter", {"call": r.call, "seconds": r.seconds,
                                             "steps_in_doorway": steps}))
        self.flush(n)
        self.selected = n
        self.say(f"{n} is in. Click a contact to engage with the selected operator.")

    def engage(self, t):
        sel = self.selected
        if not sel or self.rt[sel].status != "inside":
            return self.say("Select an operator that is inside the room first.", GREY)
        r, op = self.rt[sel], self.team[sel]
        if self.t < r.busy_until:
            return self.say(f"{sel} is reloading...", GREY)
        lethal = t["armed"] or t["civilian"]
        if lethal and op.ammo < 3:
            return self.say(f"{sel} is out of ammo - reload (L)!", RED)
        data = dict(target=t["id"], sector=t["sector"], own_sector_clear=self.own_clear(sel),
                    muzzle_on_teammate=self.flags_teammate(sel, t["pos"]),
                    rounds=3 if lethal else 0)
        kind = "civ" if t["civilian"] else ("armed" if t["armed"] else "unarmed")
        self.down.append((V2(t["pos"]), kind))
        if lethal:
            self.shots.append([V2(r.pos), V2(t["pos"]), 0.12])
        self.engine.step(Action(sel, "engage", data))
        if not t["civilian"]:
            self.say("Armed threat neutralized." if t["armed"] else "Suspect secured.", GREEN)
        self.flush(sel)

    def do_reload(self):
        sel = self.selected
        if not sel:
            return self.say("Select an operator first (click one, or TAB).", GREY)
        self.engine.step(Action(sel, "reload", {"call": self.pending_call}))
        self.rt[sel].busy_until = self.t + 1.5
        self.pending_call = ""
        self.flush(sel)
        self.say(f"{sel} reloads.", WHITE)

    def do_hold(self):
        sel = self.selected
        if sel != "D" or self.rt["D"].status != "inside":
            return self.say("Only D (rear security), once inside, holds the rear.", GREY)
        if self.rt["D"].held:
            return self.say("D is already covering the rear.", GREY)
        self.rt["D"].held = True
        self.engine.step(Action("D", "hold", {"facing_back": True}))
        self.flush("D")
        self.say("D is covering the rear.", GREEN)

    # ------------------------------------------------------------- input
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.KEYDOWN:
            self.on_key(e.key)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.on_click(V2(e.pos))

    def on_key(self, k):
        if self.state == "title":
            if k in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.diff = {pygame.K_1: "easy", pygame.K_2: "normal", pygame.K_3: "hard"}[k]
                self.rules = generate_rules(self.diff)
            elif k in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_run()
            elif k == pygame.K_ESCAPE:
                self.running = False
        elif self.state == "debrief":
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.level += 1
                if self.level >= len(LEVELS):
                    self.state = "win"
                else:
                    self.new_level()
        elif self.state in ("over", "win"):
            if k == pygame.K_r:
                self.start_run()
            elif k in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.state = "title"
        elif self.state == "play":
            if k == pygame.K_ESCAPE:
                self.state = "title"
            elif k == pygame.K_z:
                self.do_slice()
            elif k == pygame.K_x:
                self.do_call()
            elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                self.send(k - pygame.K_1)
            elif k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP):
                self.leave_door({pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
                                 pygame.K_UP: "center"}[k])
            elif k == pygame.K_l:
                self.do_reload()
            elif k == pygame.K_h:
                self.do_hold()
            elif k == pygame.K_TAB:
                names = list(self.rt)
                cur = names.index(self.selected) if self.selected in names else -1
                self.selected = names[(cur + 1) % len(names)]
            elif k == pygame.K_F1:
                self.coach_on = not self.coach_on

    def on_click(self, p):
        if self.state != "play":
            return
        for n, r in self.rt.items():
            if r.pos.distance_to(p) <= 20:
                self.selected = n
                return
        for t in list(self.room.threats):
            if self.threat_state(t) != "hidden" and V2(t["pos"]).distance_to(p) <= 22:
                self.engage(t)
                return

    # ------------------------------------------------------------ update
    def update(self, dt):
        for f in self.floaters:
            f["ttl"] -= dt
            f["pos"].y -= 22 * dt
        self.floaters = [f for f in self.floaters if f["ttl"] > 0]
        self.flash = max(0.0, self.flash - dt)
        if self.state != "play":
            return
        self.t += dt
        for r in self.rt.values():
            d = r.target - r.pos
            if d.length() > 1:
                r.pos += d.normalize() * min(d.length(), 280 * dt)
        for s in self.shots:
            s[2] -= dt
        self.shots = [s for s in self.shots if s[2] > 0]

        hostiles = [t for t in self.room.threats if not t["civilian"]]
        if self.contact and hostiles:
            if any(t["armed"] for t in hostiles):
                self.threat_t -= dt
                if self.threat_t <= 0:
                    victims = self.inside_ops()
                    if victims:
                        v = random.choice(victims)
                        self.engine.adjust(v, "Hit taken", -30)
                        self.hits += 1
                        self.flash = 0.35
                        self.say(f"{v} took a hit! Neutralize armed threats faster.", RED)
                        self.flush(v)
                    self.threat_t = 4.5
        elif self.contact and not hostiles and self.state == "play":
            self.finish_room()

    def finish_room(self):
        eng = self.engine
        if self.rt["D"].status == "inside" and not self.rt["D"].held:
            eng.step(Action("D", "hold", {"facing_back": False}))
            self.flush("D")
        missing = [n for n, r in self.rt.items() if r.status == "corridor"]
        if missing and self.state == "play":
            eng.adjust("Team", "Full stack expected", -10 * len(missing))
            self.flush()
        if self.state != "play":
            return
        elapsed = self.t - (self.first_press or 0)
        par = 32 - 2 * self.level
        bonus = 25 + max(0, int(par - elapsed)) * 2
        eng.adjust("Team", "Room cleared", bonus)
        self.flush()
        if self.state != "play":
            return
        self.debrief = [f"Time: {elapsed:4.1f}s (par {par}s)   Hits taken: {self.hits}",
                        f"Room bonus: +{bonus}   Score: {eng.score}"]
        self.state = "debrief"

    # -------------------------------------------------------------- coach
    def coach(self):
        if not self.coach_on or self.state != "play":
            return ""
        d = self.door_operator()
        if d:
            return f"{d} is in the fatal funnel - press an arrow key NOW."
        entered = len(self.room.entered)
        names = list(self.team)
        if entered == 0 and not self.room.sliced:
            return "Slice the pie before anyone enters (Z)."
        if entered < 4:
            nxt = names[entered]
            if self.team[nxt].ammo < 10:
                return f"{nxt} is low on ammo: select {nxt}, call (X) and reload (L) before entry."
            return f"Next in stack: {nxt} (key {entered + 1}). Call out first (X), keep the 4s tempo."
        return ""

    def coach_late(self):
        if not self.coach_on or self.state != "play":
            return ""
        if any(not t["civilian"] for t in self.room.threats) and self.inside_ops():
            extra = " D: select D and press H to hold the rear." if (
                self.rt["D"].status == "inside" and not self.rt["D"].held) else ""
            return ("Armed threats first, then secure suspects. Stay in your sector, keep your "
                    "line of fire clear of teammates, never shoot civilians (C)." + extra)
        return ""

    # ------------------------------------------------------------- drawing
    def text(self, font, s, pos, col=WHITE, center=False):
        surf = font.render(s, True, col)
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        self.screen.blit(surf, rect)
        return rect

    def wrap(self, font, s, width):
        lines, cur = [], ""
        for w in s.split():
            test = (cur + " " + w).strip()
            if font.size(test)[0] <= width:
                cur = test
            else:
                lines.append(cur)
                cur = w
        return lines + ([cur] if cur else [])

    def bar(self, x, y, w, h, frac, col, label):
        pygame.draw.rect(self.screen, (40, 43, 52), (x, y, w, h))
        pygame.draw.rect(self.screen, col, (x, y, int(w * max(0, min(1, frac))), h))
        pygame.draw.rect(self.screen, GREY, (x, y, w, h), 1)
        self.text(self.f13, label, (x + 4, y + 1), WHITE)

    def draw(self):
        s = self.screen
        s.fill((18, 20, 26))
        if self.state == "title":
            self.draw_title()
        else:
            self.draw_map()
            self.draw_panel()
            self.draw_bottom()
            if self.state == "debrief":
                self.draw_debrief()
            elif self.state == "over":
                self.draw_end(False)
            elif self.state == "win":
                self.draw_end(True)
        pygame.display.flip()

    def draw_map(self):
        s = self.screen
        pygame.draw.rect(s, (58, 62, 74), ROOM)
        for x in range(ROOM.left, ROOM.right, 40):
            pygame.draw.line(s, (64, 68, 80), (x, ROOM.top), (x, ROOM.bottom))
        for y in range(ROOM.top, ROOM.bottom, 40):
            pygame.draw.line(s, (64, 68, 80), (ROOM.left, y), (ROOM.right, y))
        third = ROOM.width / 3
        for i, nm in enumerate(("LEFT", "FAR", "RIGHT")):
            self.text(self.f13, f"{nm} SECTOR", (ROOM.left + third * (i + .5), ROOM.top + 12), DIM, True)
            if i:
                for yy in range(ROOM.top, ROOM.bottom, 14):
                    pygame.draw.line(s, DIM, (ROOM.left + third * i, yy), (ROOM.left + third * i, yy + 6))
        pygame.draw.rect(s, (40, 43, 52), CORR)
        wall, hw = (200, 205, 215), DOOR_W // 2
        for a, b in [((ROOM.left, ROOM.top), (ROOM.right, ROOM.top)),
                     ((ROOM.left, ROOM.top), (ROOM.left, ROOM.bottom)),
                     ((ROOM.right, ROOM.top), (ROOM.right, ROOM.bottom)),
                     ((ROOM.left, ROOM.bottom), (self.door_x - hw, ROOM.bottom)),
                     ((self.door_x + hw, ROOM.bottom), (ROOM.right, ROOM.bottom)),
                     ((CORR.left, CORR.top), (CORR.left, CORR.bottom)),
                     ((CORR.right, CORR.top), (CORR.right, CORR.bottom)),
                     ((CORR.left, CORR.bottom), (CORR.right, CORR.bottom))]:
            pygame.draw.line(s, wall, a, b, 6)
        pygame.draw.line(s, (120, 200, 255), (self.door_x - hw, ROOM.bottom), (self.door_x + hw, ROOM.bottom), 2)
        self.text(self.f13, "DOOR", (self.door_x, ROOM.bottom + 10), (120, 200, 255), True)

        if not self.room.sliced and not self.inside_ops():
            fog = pygame.Surface(ROOM.size, pygame.SRCALPHA)
            fog.fill((10, 10, 14, 225))
            s.blit(fog, ROOM.topleft)
            self.text(self.f22, "UNKNOWN - SLICE THE PIE (Z)", ROOM.center, GREY, True)

        for pos, kind in self.down:
            c = {"armed": (110, 60, 60), "unarmed": (110, 85, 50), "civ": (200, 40, 40)}[kind]
            pygame.draw.line(s, c, pos + V2(-9, -9), pos + V2(9, 9), 4)
            pygame.draw.line(s, c, pos + V2(-9, 9), pos + V2(9, -9), 4)
        for t in self.room.threats:
            st = self.threat_state(t)
            if st == "hidden":
                continue
            p = V2(t["pos"])
            if st == "unknown":
                col, ch = (120, 125, 135), "?"
            elif t["civilian"]:
                col, ch = (80, 140, 255), "C"
            elif t["armed"]:
                col, ch = (235, 70, 70), "H"
            else:
                col, ch = (240, 160, 60), "U"
            pygame.draw.circle(s, col, p, 16)
            pygame.draw.circle(s, (15, 15, 20), p, 16, 2)
            self.text(self.f16, ch, p, (15, 15, 20), True)
            if st == "id" and t["armed"] and not t["civilian"]:
                pygame.draw.line(s, (255, 200, 200), p + V2(12, 0), p + V2(26, -6), 3)

        for n, r in self.rt.items():
            pygame.draw.circle(s, OP_COL[n], r.pos, 15)
            pygame.draw.circle(s, (15, 15, 20), r.pos, 15, 2)
            self.text(self.f16, n, r.pos, (15, 15, 20), True)
            if n == self.selected:
                pygame.draw.circle(s, WHITE, r.pos, 21, 2)
            ammo = self.team[n].ammo
            self.text(self.f13, f"{ammo}", r.pos + V2(0, 26), RED if ammo < 10 else GREY, True)
            if r.held:
                self.text(self.f13, "REAR", r.pos + V2(0, -26), OP_COL[n], True)
        if self.door_operator():
            d = self.rt[self.door_operator()]
            pygame.draw.circle(s, RED, self.doorway, 34 + int(4 * math.sin(self.t * 12)), 2)
            self.text(self.f16, "MOVE!", self.doorway + V2(0, -44), RED, True)

        sel = self.selected
        mp = V2(pygame.mouse.get_pos())
        if self.state == "play" and sel and self.rt[sel].status == "inside" and ROOM.collidepoint(mp):
            bad = self.flags_teammate(sel, mp)
            pygame.draw.line(s, RED if bad else (200, 230, 255), self.rt[sel].pos, mp, 1)
            if bad:
                self.text(self.f13, "FLAGGING TEAMMATE", mp + V2(0, -18), RED, True)
        for a, b, _ in self.shots:
            pygame.draw.line(s, (255, 240, 150), a, b, 3)
        for f in self.floaters:
            self.text(self.f16, f["text"], f["pos"], f["col"])
        if self.flash > 0:
            v = pygame.Surface((MAP_W, H), pygame.SRCALPHA)
            v.fill((255, 0, 0, int(110 * self.flash / 0.35)))
            s.blit(v, (0, 0))

    def draw_panel(self):
        s = self.screen
        x0 = MAP_W + 14
        pygame.draw.rect(s, (24, 26, 34), (MAP_W, 0, W - MAP_W, H))
        pygame.draw.line(s, DIM, (MAP_W, 0), (MAP_W, H))
        self.text(self.f22, "CQB TRAINER", (x0, 12), WHITE)
        self.text(self.f16, f"Room {min(self.level + 1, len(LEVELS))}/{len(LEVELS)}: {self.cfg['name']}  [{self.diff}]", (x0, 40), GREY)
        eng = self.engine
        self.text(self.f40, f"{eng.score}", (x0, 62), GREEN if eng.score >= 100 else (YEL if eng.score >= 60 else RED))
        mult = min(1 + eng.streak // 5, 2)
        self.text(self.f16, f"streak {eng.streak}  x{mult}", (x0 + 130, 78), YEL if mult > 1 else GREY)
        self.text(self.f13, f"fail below {eng.fail_below}", (x0 + 130, 98), DIM)

        w = W - MAP_W - 28
        if self.last_press is not None and any(r.status == "corridor" for r in self.rt.values()):
            left = 4.0 - (self.t - self.last_press)
            self.bar(x0, 122, w, 16, left / 4, GREEN if left > 1.5 else RED, "ENTRY TEMPO (4s)")
        else:
            self.bar(x0, 122, w, 16, 0, DIM, "ENTRY TEMPO")
        if self.contact and any(t["armed"] for t in self.room.threats):
            self.bar(x0, 146, w, 16, self.threat_t / (self.cfg["fire"] if self.threat_t > 4.5 else 4.5), RED,
                     "ARMED THREAT CLOCK")
        else:
            self.bar(x0, 146, w, 16, 0, DIM, "THREAT CLOCK")
        self.text(self.f13, f"CALL: {'READY' if self.pending_call else '-'}", (x0, 168),
                  YEL if self.pending_call else DIM)

        self.text(self.f16, "TEAM", (x0, 190), GREY)
        for i, (n, op) in enumerate(self.team.items()):
            y = 210 + i * 42
            r = self.rt[n]
            pygame.draw.circle(s, OP_COL[n], (x0 + 12, y + 14), 12)
            self.text(self.f16, n, (x0 + 12, y + 14), (15, 15, 20), True)
            if n == self.selected:
                pygame.draw.circle(s, WHITE, (x0 + 12, y + 14), 16, 2)
            self.text(self.f13, f"{op.role:<6} sector:{op.sector}", (x0 + 34, y))
            self.bar(x0 + 34, y + 17, 110, 12, op.ammo / 30, RED if op.ammo < 10 else (90, 150, 220), f"{op.ammo}")
            st = {"corridor": "STACK", "door": "DOOR", "inside": "IN"}[r.status]
            if r.held:
                st = "REAR"
            self.text(self.f13, st, (x0 + 156, y + 17), GREY)

        self.text(self.f16, "RULE FEED", (x0, 384), GREY)
        for i, (line, col) in enumerate(self.feed[-13:]):
            self.text(self.f13, line[:38], (x0, 406 + i * 15), col)
        for i, line in enumerate(["Z slice  X call  1-4 send A-D", "Arrows: leave the doorway",
                                  "Click: select / engage  L reload", "H: D holds rear  TAB cycle",
                                  "F1 coach on/off  ESC menu"]):
            self.text(self.f13, line, (x0, 626 + i * 16), DIM)

    def draw_bottom(self):
        y = CORR.bottom + 14
        for i, (ch, col, lab) in enumerate([("H", (235, 70, 70), "armed hostile (neutralize first)"),
                                            ("U", (240, 160, 60), "unarmed suspect (secure)"),
                                            ("C", (80, 140, 255), "civilian - NEVER fire"),
                                            ("?", (120, 125, 135), "unidentified contact")]):
            x = 70 + (i % 2) * 330
            yy = y + (i // 2) * 24
            pygame.draw.circle(self.screen, col, (x, yy + 8), 9)
            self.text(self.f13, ch, (x, yy + 8), (15, 15, 20), True)
            self.text(self.f13, lab, (x + 16, yy + 1), GREY)
        yy = y + 58
        for line in self.wrap(self.f16, self.coach(), MAP_W - 100)[:2]:
            self.text(self.f16, line, (70, yy), (150, 200, 255))
            yy += 20
        for line in self.wrap(self.f13, self.coach_late(), MAP_W - 100)[:3]:
            self.text(self.f13, line, (70, yy), (150, 200, 255))
            yy += 16
        lines = self.wrap(self.f22, self.msg_text, MAP_W - 110)[:2]
        for i, line in enumerate(lines):
            self.text(self.f22, line, (70, H - 30 - 26 * (len(lines) - 1 - i)), self.msg_col)

    def overlay(self, alpha=190):
        v = pygame.Surface((W, H), pygame.SRCALPHA)
        v.fill((8, 9, 12, alpha))
        self.screen.blit(v, (0, 0))

    def draw_debrief(self):
        self.overlay()
        cx = MAP_W // 2
        self.text(self.f40, "ROOM CLEARED", (cx, 120), GREEN, True)
        for i, line in enumerate(self.debrief):
            self.text(self.f16, line, (cx, 190 + i * 24), WHITE, True)
        self.text(self.f22, "Mistakes this room", (cx, 270), YEL, True)
        if not self.room_bad:
            self.text(self.f16, "None - textbook entry!", (cx, 305), GREEN, True)
        for i, (k, v) in enumerate(self.room_bad.most_common(6)):
            self.text(self.f16, f"{k}  x{v}", (cx, 305 + i * 24), RED, True)
        self.text(self.f16, "ENTER - next room", (cx, 520), GREY, True)

    def draw_end(self, win):
        self.overlay(215)
        cx = MAP_W // 2
        if win:
            sc = self.engine.score
            grade = "S" if sc >= 2800 else "A" if sc >= 2000 else "B" if sc >= 1200 else "C"
            self.text(self.f40, "MISSION COMPLETE", (cx, 110), GREEN, True)
            self.text(self.f40, f"GRADE {grade}", (cx, 170), YEL, True)
            self.text(self.f22, f"Final score: {sc}", (cx, 225), WHITE, True)
        else:
            self.text(self.f40, "MISSION FAILED", (cx, 110), RED, True)
            self.text(self.f22, self.fail_reason, (cx, 170), WHITE, True)
            self.text(self.f16, f"Score: {self.engine.score}", (cx, 205), GREY, True)
        self.text(self.f22, "Your most common mistakes", (cx, 270), YEL, True)
        if not self.run_bad:
            self.text(self.f16, "None!", (cx, 305), GREEN, True)
        for i, (k, v) in enumerate(self.run_bad.most_common(6)):
            rule = next((r for r in self.rules if r.name == k), None)
            tip = f" - {rule.description}" if rule else ""
            self.text(self.f13, f"{k} x{v}{tip}", (cx, 305 + i * 24), RED, True)
        self.text(self.f16, "R - retry    ENTER - menu", (cx, 520), GREY, True)

    def draw_title(self):
        self.text(self.f40, "CQB TRAINER", (W // 2, 50), WHITE, True)
        self.text(self.f16, "A tactical training game scored by a Python rules engine", (W // 2, 90), GREY, True)
        x = 80
        for i, d in enumerate(("easy", "normal", "hard")):
            on = d == self.diff
            self.text(self.f22, f"[{i + 1}] {d.upper()}", (x + i * 190, 130), YEL if on else DIM)
        self.text(self.f16, "RULES  (reward / penalty)", (80, 185), GREY)
        for i, r in enumerate(self.rules):
            tag = "  FATAL" if r.fatal else ""
            self.text(self.f16, f"{r.id} {r.name:<22} +{r.reward:<3} -{r.penalty}{tag}", (80, 212 + i * 24),
                      RED if r.fatal else WHITE)
        howto = ["HOW TO PLAY",
                 "1. Slice the pie (Z) to see the room.",
                 "2. Call out (X), then send operators",
                 "   IN ORDER with 1,2,3,4 (A,B,C,D).",
                 "3. Move each one off the doorway with",
                 "   the arrow keys - fast!",
                 "4. Click an operator to select, click a",
                 "   contact to engage. Armed first.",
                 "5. Stay in your sector, never flag a",
                 "   teammate, never shoot civilians.",
                 "6. D holds the rear (select D, press H).",
                 "7. Reload low-ammo operators BEFORE entry.",
                 "",
                 "Armed threats fire on a clock - be quick!"]
        for i, line in enumerate(howto):
            self.text(self.f16, line, (600, 185 + i * 24), YEL if i == 0 else WHITE)
        self.text(self.f22, "ENTER - start     ESC - quit", (W // 2, 640), GREEN, True)


def main():
    g = Game()
    while g.running:
        dt = min(g.clock.tick(FPS) / 1000, 0.05)
        for e in pygame.event.get():
            g.handle_event(e)
        g.update(dt)
        g.draw()
    pygame.quit()


if __name__ == "__main__":
    main()
