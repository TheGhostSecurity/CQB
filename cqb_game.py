
import array
import math
import random
from collections import Counter
from dataclasses import dataclass

import pygame
from pygame.math import Vector2 as V2

from controls import Pad
from cqb_rules_engine import Engine, Action, Operator, Room, generate_rules

# ================================================================== constants
W, H, MAP_W, FPS = 1100, 720, 780, 60
ROOM = pygame.Rect(60, 50, 660, 330)
CORR = pygame.Rect(60, 388, 660, 130)
DOOR_W = 76

GREEN, RED, YEL = (96, 226, 140), (246, 88, 96), (255, 206, 84)
WHITE, GREY, DIM = (238, 240, 246), (150, 158, 172), (88, 96, 112)
CYAN, ORANGE = (90, 210, 255), (255, 150, 60)
OP_COL = {"A": (74, 148, 255), "B": (84, 220, 124), "C": (255, 206, 70), "D": (194, 118, 250)}

LEVELS = [
    dict(name="Bedroom",    armed=1, unarmed=0, civ=0, fire=12.0),
    dict(name="Office",     armed=2, unarmed=0, civ=1, fire=10.0),
    dict(name="Kitchen",    armed=2, unarmed=1, civ=1, fire=9.0),
    dict(name="Warehouse",  armed=3, unarmed=1, civ=2, fire=8.0),
    dict(name="Final Room", armed=3, unarmed=2, civ=2, fire=7.0),
]
THEMES = {
    "Bedroom":    dict(kind="wood",     c1=(122, 88, 60),   c2=(104, 74, 50),   prop=(150, 60, 66)),
    "Office":     dict(kind="carpet",   c1=(70, 82, 100),   c2=(60, 70, 88),    prop=(120, 128, 142)),
    "Kitchen":    dict(kind="tile",     c1=(206, 208, 212), c2=(138, 142, 150), prop=(170, 174, 182)),
    "Warehouse":  dict(kind="concrete", c1=(96, 96, 98),    c2=(80, 80, 82),    prop=(176, 128, 64)),
    "Final Room": dict(kind="grate",    c1=(50, 52, 62),    c2=(38, 40, 48),    prop=(70, 36, 42)),
}


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


# ===================================================================== audio
RATE = 22050
TAU = 6.2832


def _norm(buf, peak=0.9):
    m = max(1e-9, max(abs(x) for x in buf))
    return [x / m * peak for x in buf]


def _mix(*layers):
    n = max(int(o * RATE) + len(s) for o, s in layers)
    out = [0.0] * n
    for o, s in layers:
        k = int(o * RATE)
        for i, v in enumerate(s):
            out[k + i] += v
    return out


def _shot(punch=70.0, k=0.35, dur=0.4):
    out, lp = [], 0.0
    for i in range(int(dur * RATE)):
        t = i / RATE
        nz = random.uniform(-1, 1)
        lp += (nz - lp) * k
        out.append(0.55 * nz * math.exp(-t * 110) + 0.8 * lp * math.exp(-t * 12)
                   + 0.9 * math.sin(TAU * (punch - 35 * t) * t) * math.exp(-t * 20))
    return _norm(out)


def _burst(punch, k):
    return _norm(_mix((0, _shot(punch, k)), (0.085, _shot(punch, k)), (0.17, _shot(punch, k, 0.5))))


def _hit():
    out, lp = [], 0.0
    for i in range(int(0.4 * RATE)):
        t = i / RATE
        lp += (random.uniform(-1, 1) - lp) * 0.08
        out.append(lp * math.exp(-t * 18) * 1.2 + math.sin(TAU * 55 * t) * math.exp(-t * 10))
    return _norm(out)


def _click(f=2600, dur=0.03, vol=1.0):
    return [(random.uniform(-1, 1) * 0.6 + math.sin(TAU * f * i / RATE) * 0.4)
            * math.exp(-i / RATE * 180) * vol for i in range(int(dur * RATE))]


def _reload():
    return _norm(_mix((0, _click(1800)), (0.16, _click(900, 0.05)), (0.42, _click(2400, 0.035, 1.2))))


def _radio():
    out = []
    for i in range(int(0.2 * RATE)):
        t = i / RATE
        env = min(1, t * 60) * (1 if t < 0.14 else max(0, (0.2 - t) / 0.06))
        f = 1200 if t < 0.07 else 1500
        out.append(env * (0.35 * math.sin(TAU * f * t) + 0.25 * random.uniform(-1, 1)))
    return _norm(out, 0.6)


def _door():
    out, lp = [], 0.0
    n = int(0.55 * RATE)
    for i in range(n):
        t = i / RATE
        f = 85 + 15 * math.sin(t * 22)
        saw = ((t * f) % 1) * 2 - 1
        lp += (random.uniform(-1, 1) - lp) * 0.05
        env = math.sin(3.1416 * t / 0.55) ** 0.7
        out.append(env * (0.25 * saw + 0.9 * lp))
    return _norm(out, 0.7)


def _whoosh():
    out, lp = [], 0.0
    n = int(0.55 * RATE)
    for i in range(n):
        t = i / RATE
        lp += (random.uniform(-1, 1) - lp) * (0.03 + 0.5 * t / 0.55)
        out.append(lp * math.sin(3.1416 * t / 0.55))
    return _norm(out, 0.6)


def _notes(freqs, dur, step, decay):
    layers = [(j * step, [math.sin(TAU * f * i / RATE) * math.exp(-i / RATE * decay)
                          for i in range(int(dur * RATE))]) for j, f in enumerate(freqs)]
    return _norm(_mix(*layers), 0.8)


def _bad():
    out = []
    for i in range(int(0.3 * RATE)):
        t = i / RATE
        sq = (1 if (t * 130) % 1 < .5 else -1) + (1 if (t * 98) % 1 < .5 else -1)
        out.append(sq * 0.3 * math.exp(-t * 7))
    return _norm(out, 0.7)


def _fatal():
    out, ph, lp = [], 0.0, 0.0
    for i in range(int(1.3 * RATE)):
        t = i / RATE
        ph += (40 + 220 * math.exp(-t * 1.6)) / RATE
        lp += (random.uniform(-1, 1) - lp) * 0.1
        out.append(((ph % 1) * 2 - 1) * 0.6 * math.exp(-t * 1.5) + lp * 0.3 * math.exp(-t * 3))
    return _norm(out)


def _tick():
    return [math.sin(TAU * 1400 * i / RATE) * math.exp(-i / RATE * 60) for i in range(int(0.06 * RATE))]


def _heart():
    th = [math.sin(TAU * 60 * i / RATE) * math.exp(-i / RATE * 22) for i in range(int(0.25 * RATE))]
    return _norm(_mix((0, th), (0.2, [x * 0.8 for x in th])))


def _zip():
    out, lp = [], 0.0
    n = int(0.25 * RATE)
    for i in range(n):
        nz = random.uniform(-1, 1)
        lp += (nz - lp) * 0.2
        out.append((nz - lp) * math.sin(3.1416 * i / n))
    return _norm(out, 0.5)


def _combo():
    out, ph = [], 0.0
    n = int(0.3 * RATE)
    for i in range(n):
        t = i / RATE
        ph += (600 + 2000 * t) / RATE
        out.append(math.sin(TAU * ph) * math.sin(3.1416 * i / n))
    return _norm(out, 0.6)


def _drone():
    n = 4 * RATE
    out = []
    for i in range(n):
        t = i / RATE
        lfo = 0.6 + 0.4 * math.sin(TAU * 0.5 * t)
        out.append(lfo * (math.sin(TAU * 55 * t) + 0.5 * math.sin(TAU * 82.5 * t)
                          + 0.25 * math.sin(TAU * 110 * t)))
    return _norm(out, 0.5)


class Sfx:
    def __init__(self):
        self.ok, self.muted, self.snd, self.drone_ch = False, False, {}, None
        try:
            pygame.mixer.quit()
            pygame.mixer.init(RATE, -16, 1, 512, allowedchanges=0)
            pygame.mixer.set_num_channels(20)
            self.ch = pygame.mixer.get_init()[2]
            self.build()
            self.ok = True
        except Exception:
            self.ok = False

    def _snd(self, samples, vol=1.0):
        ints = array.array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in samples))
        if self.ch == 2:
            st = array.array("h")
            for v in ints:
                st.extend((v, v))
            ints = st
        s = pygame.mixer.Sound(buffer=ints.tobytes())
        s.set_volume(vol)
        return s

    def build(self):
        S = self._snd
        self.snd = {
            "shot": [S(_shot(70, 0.35), .55), S(_shot(64, 0.3), .55)],
            "burst": [S(_burst(70, 0.35), .6), S(_burst(62, 0.28), .6)],
            "enemy": [S(_shot(50, 0.18), .5), S(_shot(46, 0.22), .5)],
            "hit": [S(_hit(), .7)], "reload": [S(_reload(), .5)], "radio": [S(_radio(), .35)],
            "door": [S(_door(), .5)], "whoosh": [S(_whoosh(), .4)],
            "chime": [S(_notes([880, 1320], .25, .06, 12), .22)],
            "bad": [S(_bad(), .38)], "fatal": [S(_fatal(), .7)], "tick": [S(_tick(), .3)],
            "heart": [S(_heart(), .6)], "zip": [S(_zip(), .4)], "combo": [S(_combo(), .35)],
            "win": [S(_notes([523, 659, 784, 1047], .5, .13, 5), .45)],
            "lose": [S(_notes([392, 330, 262, 196], .5, .18, 5), .45)],
            "click": [S(_click(2000, .03), .4)],
        }
        self.drone = S(_drone(), .16)

    def play(self, name):
        if self.ok and not self.muted:
            random.choice(self.snd[name]).play()

    def drone_on(self):
        if self.ok and self.drone_ch is None:
            self.drone_ch = self.drone.play(-1)
        if self.drone_ch is not None:
            self.drone_ch.set_volume(0 if self.muted else 1)

    def drone_off(self):
        if self.ok and self.drone_ch is not None:
            self.drone_ch.stop()
            self.drone_ch = None

    def toggle(self):
        self.muted = not self.muted
        if self.drone_ch is not None:
            self.drone_ch.set_volume(0 if self.muted else 1)
        if self.muted:
            pygame.mixer.stop() if self.ok else None
            self.drone_ch = None


# ============================================================== procedural art
def make_glow(R, peak):
    half = pygame.Surface((R, R), pygame.SRCALPHA)
    c = R // 2
    for r in range(c, 0, -2):
        pygame.draw.circle(half, (0, 0, 0, int(peak * (1 - r / c) ** 1.3)), (c, c), r)
    return pygame.transform.smoothscale(half, (R * 2, R * 2))


def make_cone(R, half_deg, peak):
    half = pygame.Surface((R, R), pygame.SRCALPHA)
    c = R // 2
    for hd, pk in ((half_deg * 1.7, peak * 0.42), (half_deg, peak)):
        for r in range(c, 0, -2):
            a = int(pk * (1 - r / c) ** 0.8)
            pts = [(c, c)] + [(c + r * math.cos(math.radians(d)), c + r * math.sin(math.radians(d)))
                              for d in range(-int(hd), int(hd) + 1, 4)]
            pygame.draw.polygon(half, (0, 0, 0, a), pts)
    return pygame.transform.smoothscale(half, (R * 2, R * 2))


def make_halo(col, r=30, peak=110):
    s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    for i in range(r, 0, -2):
        pygame.draw.circle(s, (*col, int(peak * (1 - i / r) ** 1.2)), (r, r), i)
    return s


def build_vignette():
    small = pygame.Surface((110, 72), pygame.SRCALPHA)
    cx, cy = 55, 36
    for y in range(72):
        for x in range(110):
            d = math.hypot((x - cx) / cx, (y - cy) / cy)
            small.set_at((x, y), (0, 0, 0, int(max(0, min(1, (d - 0.55) / 0.75)) ** 1.6 * 200)))
    return pygame.transform.smoothscale(small, (W, H))


def build_scanlines():
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(0, H, 3):
        pygame.draw.line(s, (0, 0, 0, 38), (0, y), (W, y))
    return s


def build_floor(theme, size, rng):
    w, h = size
    s = pygame.Surface(size)
    c1, c2, kind = theme["c1"], theme["c2"], theme["kind"]
    s.fill(c1)
    if kind == "wood":
        y = 0
        while y < h:
            pygame.draw.rect(s, shade(c1, rng.uniform(.9, 1.1)), (0, y, w, 22))
            pygame.draw.line(s, shade(c2, .6), (0, y), (w, y))
            x = rng.randint(0, 120)
            while x < w:
                pygame.draw.line(s, shade(c2, .65), (x, y), (x, y + 22))
                x += rng.randint(110, 220)
            y += 22
    elif kind == "carpet":
        for _ in range(2600):
            s.set_at((rng.randrange(w), rng.randrange(h)), shade(c1, rng.uniform(.8, 1.2)))
        for gx in range(0, w, 66):
            pygame.draw.line(s, shade(c2, .8), (gx, 0), (gx, h))
        for gy in range(0, h, 66):
            pygame.draw.line(s, shade(c2, .8), (0, gy), (w, gy))
    elif kind == "tile":
        for gx in range(0, w, 44):
            for gy in range(0, h, 44):
                pygame.draw.rect(s, c1 if (gx // 44 + gy // 44) % 2 == 0 else c2, (gx, gy, 44, 44))
        for gx in range(0, w, 44):
            pygame.draw.line(s, (96, 100, 108), (gx, 0), (gx, h))
        for gy in range(0, h, 44):
            pygame.draw.line(s, (96, 100, 108), (0, gy), (w, gy))
    elif kind == "concrete":
        for _ in range(3000):
            s.set_at((rng.randrange(w), rng.randrange(h)), shade(c1, rng.uniform(.8, 1.15)))
        for gx in range(0, w, 110):
            pygame.draw.line(s, shade(c2, .7), (gx, 0), (gx, h), 2)
        for x in range(0, w, 26):
            pygame.draw.line(s, (200, 170, 40), (x, h - 118), (x + 14, h - 118), 3)
    else:
        s.fill(c2)
        for gx in range(0, w, 18):
            pygame.draw.line(s, (66, 70, 84), (gx, 0), (gx, h))
        for gy in range(0, h, 18):
            pygame.draw.line(s, (66, 70, 84), (0, gy), (w, gy))
        for x in range(0, w, 40):
            pygame.draw.polygon(s, (120, 30, 36), [(x, h), (x + 14, h), (x + 28, h - 12), (x + 14, h - 12)])
    return s


def build_corridor(rng):
    s = pygame.Surface(CORR.size)
    s.fill((48, 52, 62))
    for gx in range(0, CORR.width, 60):
        pygame.draw.line(s, (38, 42, 50), (gx, 0), (gx, CORR.height), 2)
    for gy in range(0, CORR.height, 60):
        pygame.draw.line(s, (38, 42, 50), (0, gy), (CORR.width, gy), 2)
    for _ in range(1500):
        s.set_at((rng.randrange(CORR.width), rng.randrange(CORR.height)), shade((48, 52, 62), rng.uniform(.8, 1.2)))
    for x in range(0, CORR.width, 30):
        pygame.draw.line(s, (200, 170, 40), (x, CORR.height - 10), (x + 16, CORR.height - 10), 3)
    dim = pygame.Surface(CORR.size, pygame.SRCALPHA)
    dim.fill((4, 6, 13, 70))
    s.blit(dim, (0, 0))
    return s


def make_decor(door_x, threats, rng):
    props, tries = [], 0
    while len(props) < rng.randint(4, 6) and tries < 300:
        tries += 1
        w, h = rng.choice([44, 56, 70, 90]), rng.choice([30, 40, 54])
        if rng.random() < .5:
            w, h = h, w
        r = pygame.Rect(rng.randint(ROOM.left + 16, ROOM.right - 16 - w),
                        rng.randint(ROOM.top + 22, ROOM.bottom - 125 - h), w, h)
        if any(r.inflate(64, 64).collidepoint(t["pos"]) for t in threats):
            continue
        if any(r.inflate(14, 14).colliderect(p) for p in props):
            continue
        props.append(r)
    return props


def draw_prop(surf, r, theme, rng):
    kind, col = theme["kind"], theme["prop"]
    sh = pygame.Surface((r.w + 14, r.h + 14), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 95), (0, 0, r.w + 6, r.h + 6), border_radius=6)
    surf.blit(sh, (r.x - ROOM.x + 4, r.y - ROOM.y + 6))
    rr = r.move(-ROOM.x, -ROOM.y)
    pygame.draw.rect(surf, shade(col, .7), rr, border_radius=5)
    pygame.draw.rect(surf, col, rr.inflate(-6, -6), border_radius=4)
    pygame.draw.rect(surf, shade(col, 1.25), rr.inflate(-6, -6), 1, border_radius=4)
    if kind == "wood":                                                   # bed
        pygame.draw.rect(surf, (235, 232, 224), (rr.x + 5, rr.y + 5, min(24, rr.w - 10), rr.h - 10), border_radius=4)
    elif kind == "carpet":                                               # desk + monitor
        pygame.draw.rect(surf, (22, 26, 34), (rr.centerx - 10, rr.y + 6, 20, 9))
        pygame.draw.rect(surf, (90, 200, 240), (rr.centerx - 8, rr.y + 8, 16, 5))
    elif kind == "tile":                                                 # counter + sink
        pygame.draw.circle(surf, (70, 76, 86), rr.center, min(rr.w, rr.h) // 4)
    elif kind == "concrete":                                             # crate
        pygame.draw.line(surf, shade(col, .55), rr.topleft, rr.bottomright, 3)
        pygame.draw.line(surf, shade(col, .55), rr.topright, rr.bottomleft, 3)
    else:                                                                # server rack
        for i in range(0, rr.h - 8, 9):
            pygame.draw.circle(surf, GREEN if rng.random() < .6 else RED, (rr.x + 9, rr.y + 8 + i), 2)


# ================================================================ world logic
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
                            civilian=(kind == "civ"), pos=(x, y), ang=math.pi / 2,
                            phase=random.random() * 6.28))
    return door_x, Room(threats=threats)


def make_team():
    team = {"A": Operator("A", "point", "left", random.randint(14, 30)),
            "B": Operator("B", "second", "right", random.randint(14, 30)),
            "C": Operator("C", "third", "far", random.randint(14, 30)),
            "D": Operator("D", "rear", "rear", random.randint(14, 30))}
    if random.random() < 0.6:
        team[random.choice("ABCD")].ammo = random.randint(4, 9)
    return team


@dataclass
class Rt:
    pos: V2
    target: V2
    status: str = "corridor"
    call: str = ""
    seconds: float = 0.0
    sent_t: float = 0.0
    slot_dir: str = ""
    held: bool = False
    busy_until: float = 0.0
    ang: float = -math.pi / 2
    recoil: float = 0.0


def angle_diff(a, b):
    return (b - a + math.pi) % (2 * math.pi) - math.pi


# ==================================================================== the game
class Game:
    def __init__(self):
        pygame.quit()
        pygame.init()
        self.sfx = Sfx()
        pygame.display.set_caption("CQB Trainer - Rules Engine Edition")
        pygame.display.quit()
        self.screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
        self.surf = self.screen
        self.clock = pygame.time.Clock()
        mono = "consolas,dejavusansmono,couriernew,monospace"
        self.f13 = pygame.font.SysFont(mono, 13)
        self.f16 = pygame.font.SysFont(mono, 16)
        self.f22 = pygame.font.SysFont(mono, 22, bold=True)
        self.f40 = pygame.font.SysFont(mono, 40, bold=True)
        self.f64 = pygame.font.SysFont(mono, 64, bold=True)
        self.running, self.state, self.diff = True, "title", "normal"
        self.coach_on, self.scan_on = True, True
        self.rules = generate_rules(self.diff)
        self.engine = None
        self.feed, self.floaters, self.tracers, self.flashes, self.parts = [], [], [], [], []
        self.run_bad, self.fail_reason = Counter(), ""
        self.trauma, self.freeze, self.tt, self.dt = 0.0, 0.0, 0.0, 1 / 60
        self.fx_flash = (RED, 0.0, 0.3)
        self.banner = ("", 0.0)
        self.disp_score, self.score_delta, self.delta_t = 100.0, 0, 0.0
        self.dark_a, self.door_open, self.slice_t = 236.0, 0.0, 0.0
        self.last_mult, self.last_sec = 1, 99
        self.cone_cache = {}
        self.pad = Pad()
        self.pad_st = {}
        self.go_solo = False
        self.build_assets()
        self.start_stub()

    def start_stub(self):
        self.cfg = LEVELS[0]
        self.door_x, self.room = 400, Room(threats=[])
        self.team = make_team()
        self.rt = {}
        self.selected, self.pending_call = None, ""
        self.t, self.first_press, self.last_press = 0.0, None, None
        self.contact, self.threat_t, self.hits = False, 12.0, 0
        self.down, self.props, self.room_bad = [], [], Counter()
        self.debrief, self.msg_text, self.msg_col = [], "", WHITE
        self.floor_tex = pygame.Surface(ROOM.size)

    def build_assets(self):
        self.world = pygame.Surface((MAP_W, H))
        self.dark = pygame.Surface(ROOM.size, pygame.SRCALPHA)
        self.vig = build_vignette().convert_alpha()
        self.scan = build_scanlines().convert_alpha()
        self.glow_s, self.glow_m, self.glow_l = make_glow(60, 200), make_glow(120, 200), make_glow(200, 220)
        self.cone_base = make_cone(190, 22, 235)
        self.wedge_base = make_cone(260, 30, 200)
        self.shadow = pygame.Surface((34, 26), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow, (0, 0, 0, 100), (0, 0, 34, 26))
        self.corr_tex = build_corridor(random.Random(7))
        self.halos = {}
        self.panel_bg = pygame.Surface((W - MAP_W, H))
        for y in range(H):
            f = y / H
            pygame.draw.line(self.panel_bg, tuple(int(a + (b - a) * f) for a, b in zip((30, 34, 48), (13, 15, 22))),
                             (0, y), (W, y))

    # ---------------------------------------------------------- run / level
    def start_run(self):
        self.rules = generate_rules(self.diff)
        self.engine, self.level = None, 0
        self.run_bad, self.feed, self.floaters = Counter(), [], []
        self.fail_reason = ""
        self.disp_score, self.last_mult = 100.0, 1
        self.sfx.drone_on()
        self.new_level()

    def new_level(self):
        self.cfg = LEVELS[self.level]
        self.theme = THEMES[self.cfg["name"]]
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
        rng = random.Random(self.level * 31 + random.randint(0, 999))
        self.floor_tex = build_floor(self.theme, ROOM.size, rng)
        self.props = make_decor(self.door_x, self.room.threats, rng)
        for p in self.props:
            draw_prop(self.floor_tex, p, self.theme, rng)
        self.selected, self.pending_call = None, ""
        self.t, self.first_press, self.last_press = 0.0, None, None
        self.contact, self.threat_t = False, self.cfg["fire"]
        self.down, self.hits = [], 0
        self.tracers, self.flashes, self.parts = [], [], []
        self.room_bad, self.debrief = Counter(), []
        self.dark_a, self.door_open, self.slice_t, self.last_sec = 236.0, 0.0, 0.0, 99
        self.say("Stack up. Slice the pie (Z), then send the point man (1).")
        self.state = "play"

    @property
    def doorway(self):
        return V2(self.door_x, ROOM.bottom - 8)

    def say(self, text, col=WHITE):
        self.msg_text, self.msg_col = text, col

    # -------------------------------------------------------------- queries
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

    # ------------------------------------------------------------- effects
    def burst(self, pos, n, kind, col=None, speed=(60, 220), life=(.25, .6)):
        for _ in range(n):
            a = random.uniform(0, 6.283)
            v = V2(math.cos(a), math.sin(a)) * random.uniform(*speed)
            self.parts.append(dict(pos=V2(pos), vel=v, life=random.uniform(*life), max=0.6, kind=kind,
                                   col=col or (255, 200, 90), size=random.uniform(2, 5)))
        self.parts = self.parts[-260:]

    def shoot_fx(self, a, b, enemy=False):
        col = (255, 150, 90) if enemy else (255, 240, 170)
        self.tracers.append(dict(a=V2(a), b=V2(b), life=0.14, col=col))
        self.flashes.append(dict(pos=V2(a), life=0.09))
        self.burst(b, 8, "spark")
        self.burst(b, 4, "dust", (170, 165, 155), (20, 70), (.4, .9))
        d = (V2(b) - V2(a))
        if d.length() > 0:
            side = V2(-d.y, d.x).normalize()
            for _ in range(2):
                self.parts.append(dict(pos=V2(a), vel=side * random.uniform(50, 110) + V2(0, -30), life=.7, max=.7,
                                       kind="casing", col=(230, 190, 80), size=3))
        self.trauma = min(1.0, self.trauma + (0.5 if enemy else 0.32))

    def flash(self, col, dur=0.3):
        self.fx_flash = (col, dur, dur)

    def popup(self, text, pos, col, big=False, dy=0):
        self.floaters.append(dict(text=text, pos=V2(pos) + V2(0, dy), col=col, ttl=1.5, big=big))

    # ------------------------------------------------------------- scoring
    def flush(self, actor=""):
        eng = self.engine
        rows = eng.log[self.log_seen:]
        self.log_seen = len(eng.log)
        if not rows:
            return
        total = sum(r[4] for r in rows)
        self.feed.append((f"{rows[0][0]} {rows[0][1]}: {total:+d}", GREEN if total >= 0 else RED))
        pos = V2(self.rt[actor].pos) if actor in self.rt else V2(MAP_W // 2, ROOM.centery)
        self.popup(f"{total:+d}", pos + V2(0, -26), GREEN if total >= 0 else RED, big=True)
        self.score_delta, self.delta_t = total, 1.4
        k, any_bad = 0, False
        for r in rows:
            if r[3].strip() == "BAD":
                any_bad = True
                self.feed.append((f"  x {r[2]} {r[4]:+d}", RED))
                self.run_bad[r[2]] += 1
                self.room_bad[r[2]] += 1
                k += 1
                self.popup(f"{r[2]} {r[4]:+d}", pos + V2(22, -26), RED, dy=k * 17)
                if r[2] == "Protect civilians":
                    self.fail_reason = "You fired on a civilian."
        self.feed = self.feed[-15:]
        if any_bad:
            self.sfx.play("bad")
            self.flash(RED, 0.22)
            self.trauma = min(1.0, self.trauma + 0.2)
        elif total > 0:
            self.sfx.play("chime")
        mult = min(1 + eng.streak // 5, 2)
        if mult > self.last_mult:
            self.banner = ("COMBO x2", 1.5)
            self.sfx.play("combo")
        self.last_mult = mult
        if eng.failed and self.state == "play":
            self.fail_reason = self.fail_reason or "Score fell below the minimum."
            self.state = "over"
            self.sfx.drone_off()
            self.sfx.play("fatal" if "civilian" in self.fail_reason else "lose")
            self.flash(RED, 0.6)
            self.trauma = 1.0

    # -------------------------------------------------------------- actions
    def do_slice(self):
        if self.room.sliced:
            return self.say("Room already sliced.", GREY)
        self.engine.step(Action("A", "slice_pie"))
        self.slice_t = 0.9
        self.sfx.play("whoosh")
        self.say("Pie sliced - contacts identified. Now call out (X) and send the stack.", GREEN)

    def do_call(self):
        self.pending_call = "Entering!"
        self.sfx.play("radio")
        self.say("CALL READY - spoken on your next entry or reload.", YEL)

    def send(self, idx):
        name = list(self.team)[idx]
        r = self.rt[name]
        if r.status != "corridor":
            return self.say(f"{name} is already in the room.", GREY)
        if self.door_operator():
            self.sfx.play("bad")
            return self.say("Doorway is blocked - move the operator off it (arrow keys)!", RED)
        now = self.t
        seconds = 0.0 if self.last_press is None else now - self.last_press
        if self.first_press is None:
            self.first_press, self.contact, self.threat_t = now, True, self.cfg["fire"]
            self.sfx.play("door")
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
            self.sfx.play("click")
            return self.say(f"{sel} is out of ammo - reload (L)!", RED)
        data = dict(target=t["id"], sector=t["sector"], own_sector_clear=self.own_clear(sel),
                    muzzle_on_teammate=self.flags_teammate(sel, t["pos"]), rounds=3 if lethal else 0)
        kind = "civ" if t["civilian"] else ("armed" if t["armed"] else "unarmed")
        tp = V2(t["pos"])
        self.down.append(dict(pos=tp, kind=kind, ang=t["ang"], t0=self.t))
        r.ang = math.atan2(tp.y - r.pos.y, tp.x - r.pos.x)
        if lethal:
            r.recoil = 7
            self.shoot_fx(r.pos + V2(math.cos(r.ang), math.sin(r.ang)) * 30, tp)
            self.sfx.play("burst")
            self.freeze = 0.07
        else:
            self.burst(tp, 6, "dust", (200, 200, 210), (20, 60), (.3, .6))
            self.sfx.play("zip")
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
        self.sfx.play("reload")
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
        self.sfx.play("click")
        self.flush("D")
        self.say("D is covering the rear.", GREEN)

    # ---------------------------------------------------------------- input
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.KEYDOWN:
            self.on_key(e.key)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.on_click(V2(e.pos))

    def on_key(self, k):
        if k == pygame.K_m:
            self.sfx.toggle()
            if not self.sfx.muted and self.state in ("play", "debrief"):
                self.sfx.drone_on()
            return
        if k == pygame.K_F2:
            self.scan_on = not self.scan_on
            return
        if self.state == "title":
            if k in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.diff = {pygame.K_1: "easy", pygame.K_2: "normal", pygame.K_3: "hard"}[k]
                self.rules = generate_rules(self.diff)
                self.sfx.play("click")
            elif k in (pygame.K_RETURN, pygame.K_SPACE):
                self.sfx.play("radio")
                self.start_run()
            elif k == pygame.K_s:
                self.go_solo = True
                self.running = False
                self.sfx.play("radio")
            elif k == pygame.K_ESCAPE:
                self.running = False
        elif self.state == "debrief":
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.level += 1
                if self.level >= len(LEVELS):
                    self.state = "win"
                    self.sfx.drone_off()
                    self.sfx.play("win")
                else:
                    self.new_level()
        elif self.state in ("over", "win"):
            if k == pygame.K_r:
                self.start_run()
            elif k in (pygame.K_RETURN, pygame.K_ESCAPE):
                self.state = "title"
                self.sfx.drone_off()
        elif self.state == "play":
            if k == pygame.K_ESCAPE:
                self.state = "title"
                self.sfx.drone_off()
            elif k == pygame.K_z:
                self.do_slice()
            elif k == pygame.K_x:
                self.do_call()
            elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                self.send(k - pygame.K_1)
            elif k in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP):
                self.leave_door({pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "center"}[k])
            elif k == pygame.K_l:
                self.do_reload()
            elif k == pygame.K_h:
                self.do_hold()
            elif k == pygame.K_TAB:
                names = list(self.rt)
                cur = names.index(self.selected) if self.selected in names else -1
                self.selected = names[(cur + 1) % len(names)]
                self.sfx.play("click")
            elif k == pygame.K_F1:
                self.coach_on = not self.coach_on

    def on_click(self, p):
        if self.state != "play":
            return
        for n, r in self.rt.items():
            if r.pos.distance_to(p) <= 20:
                self.selected = n
                self.sfx.play("click")
                return
        for t in list(self.room.threats):
            if self.threat_state(t) != "hidden" and V2(t["pos"]).distance_to(p) <= 22:
                self.engage(t)
                return

    # --------------------------------------------------------- gamepad (team)
    def poll_pad(self):
        if not self.pad.present or self.state != "play":
            return
        p, st = self.pad, self.pad_st
        if p.btn_tap("LB", st):
            self.do_slice()
        if p.btn_tap("X", st):
            self.do_call()
        if p.btn_tap("A", st):
            for i, n in enumerate(self.team):
                if self.rt[n].status == "corridor":
                    self.send(i)
                    break
        if p.btn_tap("Y", st):
            if self.rt["D"].status == "inside":
                self.selected = "D"
                self.do_hold()
        if p.btn_tap("B", st):
            if self.selected:
                self.do_reload()
        hat = self.pad.hat()
        if hat is not None:
            dx, dy = hat
            self.last_hat = dx
            if dx == -1:
                self.leave_door("left")
            elif dx == 1:
                self.leave_door("right")
            elif dy == 1:
                self.leave_door("center")
        if p.btn_tap("START", st):
            self.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))

    # --------------------------------------------------------------- update
    def update(self, dt):
        self.dt = dt
        self.tt += dt
        self.trauma = max(0.0, self.trauma - dt * 1.6)
        self.delta_t = max(0.0, self.delta_t - dt)
        self.disp_score += (self.engine.score - self.disp_score) * min(1, dt * 7) if self.engine else 0
        if self.banner[1] > 0:
            self.banner = (self.banner[0], self.banner[1] - dt)
        fc, ft, fd = self.fx_flash
        self.fx_flash = (fc, max(0.0, ft - dt), fd)
        for f in self.floaters:
            f["ttl"] -= dt
            f["pos"].y -= 24 * dt
        self.floaters = [f for f in self.floaters if f["ttl"] > 0]
        self.update_particles(dt)
        if self.state != "play":
            return
        if self.freeze > 0:                                   # hit-stop / slow-mo
            self.freeze -= dt
            dt *= 0.15
        self.t += dt
        self.slice_t = max(0.0, self.slice_t - dt)
        target_open = 1.0 if self.inside_ops() else (0.3 if self.slice_t > 0 else 0.0)
        self.door_open += (target_open - self.door_open) * min(1, dt * 6)
        for r in self.rt.values():
            d = r.target - r.pos
            if d.length() > 1:
                r.pos += d.normalize() * min(d.length(), 280 * dt)
            r.recoil = max(0.0, r.recoil - 40 * dt)
        self.update_facing(dt)

        hostiles = [t for t in self.room.threats if not t["civilian"]]
        if self.contact and hostiles:
            if any(t["armed"] for t in hostiles):
                self.threat_t -= dt
                sec = int(self.threat_t)
                if self.threat_t < 3.5 and sec != self.last_sec:
                    self.sfx.play("tick" if self.threat_t > 1.5 else "heart")
                self.last_sec = sec
                if self.threat_t <= 0:
                    self.threat_fires()
                    self.threat_t = 4.5
        elif self.contact and not hostiles and self.state == "play":
            self.finish_room()

    def update_facing(self, dt):
        mp = V2(pygame.mouse.get_pos())
        alive = [V2(t["pos"]) for t in self.room.threats]
        for n, r in self.rt.items():
            if r.status == "corridor":
                want = math.atan2(self.doorway.y - r.pos.y, self.doorway.x - r.pos.x)
            elif n == self.selected and ROOM.collidepoint(mp) and r.status == "inside":
                want = math.atan2(mp.y - r.pos.y, mp.x - r.pos.x)
            elif n == "D" and r.held:
                want = math.pi / 2
            elif alive and r.status == "inside":
                tp = min(alive, key=lambda p: p.distance_to(r.pos))
                want = math.atan2(tp.y - r.pos.y, tp.x - r.pos.x)
            else:
                want = -math.pi / 2
            r.ang += angle_diff(r.ang, want) * min(1, dt * 10)
        ops = [self.rt[o].pos for o in self.inside_ops()]
        for t in self.room.threats:
            tgt = min(ops, key=lambda p: p.distance_to(V2(t["pos"]))) if ops else self.doorway
            want = math.atan2(tgt.y - t["pos"][1], tgt.x - t["pos"][0])
            t["ang"] += angle_diff(t["ang"], want) * min(1, dt * 6)

    def threat_fires(self):
        victims = self.inside_ops()
        armed = [t for t in self.room.threats if t["armed"] and not t["civilian"]]
        if not victims or not armed:
            return
        v = random.choice(victims)
        shooter = min(armed, key=lambda t: V2(t["pos"]).distance_to(self.rt[v].pos))
        self.shoot_fx(shooter["pos"], self.rt[v].pos, enemy=True)
        self.sfx.play("enemy")
        self.sfx.play("hit")
        self.engine.adjust(v, "Hit taken", -30)
        self.hits += 1
        self.flash(RED, 0.4)
        self.say(f"{v} took a hit! Neutralize armed threats faster.", RED)
        self.flush(v)

    def update_particles(self, dt):
        for p in self.parts:
            p["life"] -= dt
            p["pos"] += p["vel"] * dt
            p["vel"] *= max(0.0, 1 - (5 if p["kind"] != "casing" else 3) * dt)
        self.parts = [p for p in self.parts if p["life"] > 0]
        for tr in self.tracers:
            tr["life"] -= dt
        self.tracers = [tr for tr in self.tracers if tr["life"] > 0]
        for fl in self.flashes:
            fl["life"] -= dt
        self.flashes = [fl for fl in self.flashes if fl["life"] > 0]

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
        self.sfx.play("combo")
        self.flash(GREEN, 0.5)

    # ---------------------------------------------------------------- coach
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
            return ("Armed threats first, then secure suspects. Stay in your sector, keep your line of fire "
                    "clear of teammates, never shoot civilians (C)." + extra)
        return ""

    # -------------------------------------------------------------- drawing
    def text(self, font, s, pos, col=WHITE, center=False):
        surf = font.render(s, True, col)
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        self.surf.blit(surf, rect)
        return rect

    def text_o(self, font, s, pos, col=WHITE, center=False, alpha=255):
        base = font.render(s, True, (8, 8, 12))
        top = font.render(s, True, col)
        for o in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            r = base.get_rect(center=(pos[0] + o[0], pos[1] + o[1])) if center else base.get_rect(topleft=(pos[0] + o[0], pos[1] + o[1]))
            base.set_alpha(alpha)
            self.surf.blit(base, r)
        top.set_alpha(alpha)
        self.surf.blit(top, top.get_rect(center=pos) if center else top.get_rect(topleft=pos))

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

    def rrect(self, rect, col, radius=8, border=None, alpha=None):
        if alpha is not None:
            s = pygame.Surface(pygame.Rect(rect).size, pygame.SRCALPHA)
            pygame.draw.rect(s, (*col, alpha), s.get_rect(), border_radius=radius)
            if border:
                pygame.draw.rect(s, border, s.get_rect(), 1, border_radius=radius)
            self.surf.blit(s, pygame.Rect(rect).topleft)
        else:
            pygame.draw.rect(self.surf, col, rect, border_radius=radius)
            if border:
                pygame.draw.rect(self.surf, border, rect, 1, border_radius=radius)

    def bar(self, x, y, w, h, frac, col, label="", pulse=False):
        self.rrect((x, y, w, h), (28, 31, 42), 4, (60, 66, 84))
        fw = int(w * max(0, min(1, frac)))
        if fw > 2:
            c = shade(col, 1.0 + (0.25 * math.sin(self.tt * 12) if pulse else 0))
            pygame.draw.rect(self.surf, c, (x + 1, y + 1, fw - 2, h - 2), border_radius=3)
            pygame.draw.rect(self.surf, shade(c, 1.35), (x + 1, y + 1, fw - 2, max(1, (h - 2) // 3)), border_radius=3)
        if label:
            self.text(self.f13, label, (x + 5, y + 1), WHITE)

    def halo(self, col):
        if col not in self.halos:
            self.halos[col] = make_halo(col)
        return self.halos[col]

    def cone_rot(self, base, key, ang):
        deg = int(round(-math.degrees(ang) / 10.0)) * 10 % 360
        k = (key, deg)
        if k not in self.cone_cache:
            self.cone_cache[k] = pygame.transform.rotate(base, deg)
        return self.cone_cache[k]

    def draw(self):
        if self.state == "title":
            self.surf = self.screen
            self.draw_title()
        else:
            self.surf = self.world
            self.draw_map()
            self.surf = self.screen
            self.screen.fill((10, 11, 16))
            sh = self.trauma ** 2 * 14
            off = (int(random.uniform(-sh, sh)), int(random.uniform(-sh, sh)))
            self.screen.blit(self.world, off)
            self.draw_panel()
            self.draw_bottom()
            self.draw_banner()
            if self.state == "debrief":
                self.draw_debrief()
            elif self.state == "over":
                self.draw_end(False)
            elif self.state == "win":
                self.draw_end(True)
        self.screen.blit(self.vig, (0, 0))
        fc, ft, fd = self.fx_flash
        if ft > 0:
            v = pygame.Surface((W, H), pygame.SRCALPHA)
            v.fill((*fc, int(90 * ft / fd)))
            self.screen.blit(v, (0, 0))
        if self.state == "play" and self.contact and self.threat_t < 3 and any(
                t["armed"] for t in self.room.threats):
            v = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.rect(v, (255, 30, 30, int(50 + 40 * math.sin(self.tt * 10))), (0, 0, W, H), 10)
            self.screen.blit(v, (0, 0))
        if self.scan_on:
            self.screen.blit(self.scan, (0, 0))
        pygame.display.flip()

    # ---- the world
    def draw_map(self):
        s = self.surf
        s.fill((12, 14, 20))
        s.blit(self.floor_tex, ROOM.topleft)
        s.blit(self.corr_tex, CORR.topleft)
        third = ROOM.width / 3
        for i in (1, 2):
            for yy in range(ROOM.top, ROOM.bottom, 14):
                pygame.draw.line(s, (255, 255, 255), (ROOM.left + third * i, yy), (ROOM.left + third * i, yy + 4))
        self.draw_dark()
        for i, nm in enumerate(("LEFT", "FAR", "RIGHT")):
            self.text(self.f13, f"{nm} SECTOR", (ROOM.left + third * (i + .5), ROOM.top + 13), (190, 196, 210), True)
        self.draw_walls()
        for d in self.down:
            self.draw_body(d)
        for t in self.room.threats:
            self.draw_threat(t)
        for n in sorted(self.rt, key=lambda k: self.rt[k].pos.y):
            self.draw_operator(n)
        self.draw_effects()
        if self.slice_t > 0:
            self.draw_slice_ui()
        if not self.room.sliced and not self.inside_ops():
            a = int(170 + 60 * math.sin(self.tt * 3))
            self.text_o(self.f22, "UNKNOWN - SLICE THE PIE (Z)", ROOM.center, (a, a, a + 20), True)

    def draw_dark(self):
        ops = self.inside_ops()
        if not self.room.sliced and not ops:
            target = 238
        else:
            target = 168 if not self.room.sliced else 118
        self.dark_a += (target - self.dark_a) * min(1, self.dt * 3)
        d = self.dark
        d.fill((4, 6, 13, int(self.dark_a)))
        off = V2(ROOM.topleft)

        def light(tex, pos):
            d.blit(tex, (pos.x - off.x - tex.get_width() / 2, pos.y - off.y - tex.get_height() / 2),
                   special_flags=pygame.BLEND_RGBA_SUB)

        if self.door_open > 0.25:
            light(self.glow_l, self.doorway + V2(0, 10))
        for n in ops:
            r = self.rt[n]
            light(self.cone_rot(self.cone_base, "c", r.ang), r.pos)
            light(self.glow_s, r.pos)
        for fl in self.flashes:
            light(self.glow_l, fl["pos"])
        if self.slice_t > 0:
            f = 1 - self.slice_t / 0.9
            ang = math.radians(-160 + 140 * f)
            light(self.cone_rot(self.wedge_base, "w", ang), self.doorway)
        self.surf.blit(d, ROOM.topleft)

    def draw_walls(self):
        s, hw = self.surf, DOOR_W // 2
        segs = [((ROOM.left, ROOM.top), (ROOM.right, ROOM.top)),
                ((ROOM.left, ROOM.top), (ROOM.left, ROOM.bottom)),
                ((ROOM.right, ROOM.top), (ROOM.right, ROOM.bottom)),
                ((ROOM.left, ROOM.bottom), (self.door_x - hw, ROOM.bottom)),
                ((self.door_x + hw, ROOM.bottom), (ROOM.right, ROOM.bottom)),
                ((CORR.left, CORR.top), (CORR.left, CORR.bottom)),
                ((CORR.right, CORR.top), (CORR.right, CORR.bottom)),
                ((CORR.left, CORR.bottom), (CORR.right, CORR.bottom))]
        for w, c in ((12, (30, 33, 42)), (8, (98, 104, 118)), (4, (160, 166, 180)), (1, (214, 220, 232))):
            for a, b in segs:
                pygame.draw.line(s, c, a, b, w)
        hinge = V2(self.door_x - hw, ROOM.bottom)
        th = -math.radians(85) * self.door_open
        end = hinge + V2(math.cos(th), math.sin(th)) * DOOR_W
        pygame.draw.line(s, (70, 44, 24), hinge, end, 8)
        pygame.draw.line(s, (150, 100, 56), hinge, end, 5)
        pygame.draw.line(s, (200, 150, 96), hinge, end, 1)
        pygame.draw.circle(s, (220, 220, 230), hinge, 4)
        self.text(self.f13, "DOOR", (self.door_x, ROOM.bottom + 12), CYAN, True)

    def draw_person(self, pos, ang, armor, accent, weapon=True, hands_up=False, recoil=0.0, light=False):
        s = self.surf
        fwd = V2(math.cos(ang), math.sin(ang))
        side = V2(-fwd.y, fwd.x)
        s.blit(self.shadow, (pos.x - 17 + 3, pos.y - 13 + 5))
        if weapon:
            b, tip = pos + side * 5 + fwd * (4 - recoil), pos + side * 5 + fwd * (30 - recoil)
            pygame.draw.line(s, (16, 18, 22), b, tip, 7)
            pygame.draw.line(s, (74, 78, 90), b, tip, 3)
            if light:
                pygame.draw.circle(s, (255, 252, 210), tip, 2)
        if hands_up:
            for sg in (-1, 1):
                pygame.draw.circle(s, (232, 196, 160), pos + fwd * 14 + side * 9 * sg, 4)
        for sg in (-1, 1):
            pygame.draw.circle(s, shade(accent, .8), pos + side * 10 * sg, 7)
            pygame.draw.circle(s, (16, 18, 22), pos + side * 10 * sg, 7, 1)
        pygame.draw.circle(s, armor, pos, 11)
        pygame.draw.circle(s, (16, 18, 22), pos, 11, 2)
        pygame.draw.circle(s, accent, pos - fwd * 1, 7)
        pygame.draw.circle(s, shade(accent, 1.4), pos - fwd * 3 - side * 2, 2)

    def draw_operator(self, n):
        r = self.rt[n]
        col = OP_COL[n]
        self.draw_person(r.pos, r.ang, (44, 50, 62), col, True, False, r.recoil, light=r.status != "corridor")
        if n == self.selected and self.state == "play":
            rad = 22 + 2 * math.sin(self.tt * 6)
            pygame.draw.circle(self.surf, WHITE, r.pos, rad, 2)
            pygame.draw.polygon(self.surf, WHITE, [(r.pos.x, r.pos.y - 32), (r.pos.x - 5, r.pos.y - 40),
                                                   (r.pos.x + 5, r.pos.y - 40)])
        ammo = self.team[n].ammo
        low = ammo < 10
        self.text(self.f13, f"{n} {ammo}", r.pos + V2(0, 27), RED if low and int(self.tt * 3) % 2 else (WHITE if not low else YEL), True)
        if r.held:
            self.text(self.f13, "REAR", r.pos + V2(0, -30), col, True)
        if self.door_operator() == n:
            rad = 34 + int(4 * math.sin(self.tt * 12))
            pygame.draw.circle(self.surf, RED, self.doorway, rad, 2)
            self.text_o(self.f16, "MOVE!", self.doorway + V2(0, -46), RED, True)

    def draw_threat(self, t):
        st = self.threat_state(t)
        if st == "hidden":
            return
        p = V2(t["pos"])
        pulse = 0.5 + 0.5 * math.sin(self.tt * 4 + t["phase"])
        if st == "unknown":
            self.surf.blit(self.halo((150, 155, 170)), p - V2(30, 30))
            pygame.draw.circle(self.surf, (60, 64, 76), p, 15)
            pygame.draw.circle(self.surf, (150, 155, 170), p, 15, 2)
            self.text(self.f22, "?", p, WHITE, True)
            return
        if t["civilian"]:
            armor, accent, hc = (46, 64, 110), (96, 150, 255), (96, 150, 255)
        elif t["armed"]:
            armor, accent, hc = (92, 30, 34), (240, 76, 80), (255, 70, 70)
        else:
            armor, accent, hc = (110, 70, 26), (250, 168, 64), (255, 160, 60)
        h = self.halo(hc)
        h.set_alpha(int(150 + 100 * pulse))
        self.surf.blit(h, p - V2(30, 30))
        self.draw_person(p, t["ang"], armor, accent, weapon=t["armed"] and not t["civilian"],
                         hands_up=not t["armed"] or t["civilian"])
        lab = "C" if t["civilian"] else ("H" if t["armed"] else "U")
        self.text_o(self.f13, lab, p + V2(0, -24), hc, True)

    def draw_body(self, d):
        s = self.surf
        pos, kind = d["pos"], d["kind"]
        col = {"armed": (60, 28, 30), "unarmed": (70, 52, 30), "civ": (130, 20, 26)}[kind]
        body = pygame.Surface((36, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(body, (*col, 235), (0, 2, 36, 16))
        pygame.draw.circle(body, (*shade(col, 1.5), 235), (28, 10), 6)
        body = pygame.transform.rotate(body, -math.degrees(d["ang"]) + 90)
        s.blit(body, pos - V2(body.get_width() / 2, body.get_height() / 2))
        if kind == "civ":
            self.text(self.f13, "!!", pos + V2(0, -18), RED, True)

    def draw_effects(self):
        s = self.surf
        for tr in self.tracers:
            f = tr["life"] / 0.14
            pygame.draw.line(s, shade(tr["col"], .5 + .5 * f), tr["a"], tr["b"], max(1, int(4 * f)))
            pygame.draw.line(s, (255, 255, 255), tr["a"], tr["b"], 1)
        for fl in self.flashes:
            f = fl["life"] / 0.09
            pts = []
            for i in range(10):
                rad = (16 if i % 2 == 0 else 6) * (0.6 + 0.6 * f)
                a = i * math.pi / 5 + fl["life"] * 40
                pts.append((fl["pos"].x + math.cos(a) * rad, fl["pos"].y + math.sin(a) * rad))
            pygame.draw.polygon(s, (255, 235, 150), pts)
            pygame.draw.circle(s, (255, 255, 255), fl["pos"], 4)
        for p in self.parts:
            f = max(0.0, p["life"] / p["max"])
            if p["kind"] == "spark":
                pygame.draw.line(s, shade(p["col"], .4 + .6 * f), p["pos"], p["pos"] - p["vel"] * 0.03, 2)
            elif p["kind"] == "casing":
                pygame.draw.rect(s, shade(p["col"], .5 + .5 * f), (p["pos"].x, p["pos"].y, 4, 2))
            else:
                r = int(p["size"] * (2.5 - 1.5 * f))
                d = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(d, (*p["col"], int(110 * f)), (r + 1, r + 1), r)
                s.blit(d, p["pos"] - V2(r + 1, r + 1))
        mp = V2(pygame.mouse.get_pos())
        sel = self.selected
        if self.state == "play" and sel and self.rt[sel].status == "inside" and ROOM.collidepoint(mp):
            bad = self.flags_teammate(sel, mp)
            pygame.draw.line(s, RED if bad else (170, 220, 255), self.rt[sel].pos + V2(math.cos(self.rt[sel].ang),
                             math.sin(self.rt[sel].ang)) * 30, mp, 1)
            pygame.draw.circle(s, RED if bad else (170, 220, 255), mp, 9, 1)
            pygame.draw.line(s, RED if bad else (170, 220, 255), mp - V2(14, 0), mp + V2(14, 0), 1)
            pygame.draw.line(s, RED if bad else (170, 220, 255), mp - V2(0, 14), mp + V2(0, 14), 1)
            if bad:
                self.text_o(self.f13, "FLAGGING TEAMMATE", mp + V2(0, -22), RED, True)
        for f in self.floaters:
            a = int(255 * min(1, f["ttl"] / 0.5))
            self.text_o(self.f22 if f["big"] else self.f16, f["text"], f["pos"], f["col"], alpha=a)

    def draw_slice_ui(self):
        f = 1 - self.slice_t / 0.9
        ang = math.radians(-160 + 140 * f)
        tip = self.doorway + V2(math.cos(ang), math.sin(ang)) * 300
        pygame.draw.line(self.surf, CYAN, self.doorway, tip, 2)
        self.text_o(self.f13, "SLICING", self.doorway + V2(0, -58), CYAN, True)

    # ---- HUD
    def draw_panel(self):
        s = self.screen
        x0, w = MAP_W + 14, W - MAP_W - 28
        s.blit(self.panel_bg, (MAP_W, 0))
        pygame.draw.line(s, CYAN, (MAP_W, 0), (MAP_W, H), 2)
        self.text(self.f22, "CQB TRAINER", (x0, 10), WHITE)
        self.text(self.f13, f"Room {min(self.level + 1, len(LEVELS))}/{len(LEVELS)}: {self.cfg['name']}  [{self.diff}]"
                  f"  {'MUTED' if self.sfx.muted else ''}", (x0, 38), GREY)
        eng = self.engine
        sc = int(self.disp_score)
        col = GREEN if eng.score >= 100 else (YEL if eng.score >= 60 else RED)
        self.text(self.f40, f"{sc}", (x0, 56), col)
        if self.delta_t > 0:
            self.text(self.f16, f"{self.score_delta:+d}", (x0 + 100, 60 - int(8 * (1 - self.delta_t / 1.4))),
                      GREEN if self.score_delta >= 0 else RED)
        mult = min(1 + eng.streak // 5, 2)
        self.text(self.f16, f"streak {eng.streak}", (x0 + 150, 76), YEL if mult > 1 else GREY)
        self.text(self.f16, f"x{mult}", (x0 + 240, 76), YEL if mult > 1 else DIM)
        self.text(self.f13, f"fail below {eng.fail_below}", (x0 + 150, 96), DIM)

        if self.last_press is not None and any(r.status == "corridor" for r in self.rt.values()):
            left = 4.0 - (self.t - self.last_press)
            self.bar(x0, 122, w, 16, left / 4, GREEN if left > 1.5 else RED, "ENTRY TEMPO (4s)", pulse=left < 1.5)
        else:
            self.bar(x0, 122, w, 16, 0, DIM, "ENTRY TEMPO")
        if self.contact and any(t["armed"] for t in self.room.threats):
            self.bar(x0, 146, w, 16, self.threat_t / (self.cfg["fire"] if self.threat_t > 4.5 else 4.5),
                     RED if self.threat_t < 4 else ORANGE, "ARMED THREAT CLOCK", pulse=self.threat_t < 3)
        else:
            self.bar(x0, 146, w, 16, 0, DIM, "THREAT CLOCK")
        self.text(self.f13, f"CALL: {'READY' if self.pending_call else '-'}", (x0, 168),
                  YEL if self.pending_call else DIM)

        self.text(self.f16, "TEAM", (x0, 190), GREY)
        for i, (n, op) in enumerate(self.team.items()):
            y = 210 + i * 42
            r = self.rt[n]
            self.rrect((x0 - 4, y - 3, w + 8, 38), (40, 45, 62), 6, OP_COL[n] if n == self.selected else (54, 60, 80))
            pygame.draw.circle(s, OP_COL[n], (x0 + 14, y + 16), 12)
            self.text(self.f16, n, (x0 + 14, y + 16), (15, 15, 20), True)
            self.text(self.f13, f"{op.role:<6} sector:{op.sector}", (x0 + 36, y))
            low = op.ammo < 10
            self.bar(x0 + 36, y + 17, 110, 12, op.ammo / 30, RED if low else (80, 150, 230), f"{op.ammo}", pulse=low)
            st = {"corridor": "STACK", "door": "DOOR", "inside": "IN"}[r.status]
            if r.held:
                st = "REAR"
            self.text(self.f13, st, (x0 + 158, y + 17), GREEN if r.status == "inside" else GREY)

        self.text(self.f16, "RULE FEED", (x0, 384), GREY)
        feed = self.feed[-13:]
        for i, (line, col) in enumerate(feed):
            f = 0.45 + 0.55 * (i + 1) / max(1, len(feed))
            self.text(self.f13, line[:38], (x0, 406 + i * 15), shade(col, f))
        for i, line in enumerate(["Z slice  X call  1-4 send A-D", "Arrows: leave the doorway",
                                  "Click: select/engage  L reload", "H: D rear  TAB cycle  M mute",
                                  "F1 coach  F2 scanlines  ESC menu"]):
            self.text(self.f13, line, (x0, 626 + i * 16), DIM)

    def draw_bottom(self):
        y = CORR.bottom + 14
        for i, (ch, col, lab) in enumerate([("H", (240, 76, 80), "armed hostile (neutralize first)"),
                                            ("U", (250, 168, 64), "unarmed suspect (secure)"),
                                            ("C", (96, 150, 255), "civilian - NEVER fire"),
                                            ("?", (150, 155, 170), "unidentified contact")]):
            x = 70 + (i % 2) * 330
            yy = y + (i // 2) * 24
            pygame.draw.circle(self.screen, col, (x, yy + 8), 9)
            self.text(self.f13, ch, (x, yy + 8), (15, 15, 20), True)
            self.text(self.f13, lab, (x + 16, yy + 1), GREY)
        yy = y + 58
        for line in self.wrap(self.f16, self.coach(), MAP_W - 100)[:2]:
            self.text(self.f16, line, (70, yy), (150, 205, 255))
            yy += 20
        for line in self.wrap(self.f13, self.coach_late(), MAP_W - 100)[:3]:
            self.text(self.f13, line, (70, yy), (150, 205, 255))
            yy += 16
        lines = self.wrap(self.f22, self.msg_text, MAP_W - 110)[:2]
        for i, line in enumerate(lines):
            self.text_o(self.f22, line, (70, H - 30 - 26 * (len(lines) - 1 - i)), self.msg_col)

    def draw_banner(self):
        txt, t = self.banner
        if t > 0:
            f = min(1, t / 0.3, (1.5 - t) / 0.2 + 0.0)
            self.text_o(self.f40, txt, (MAP_W // 2, 130 - int(20 * (1 - min(1, t)))), YEL, True, alpha=int(255 * max(0, min(1, f))))

    def card(self, rect, border):
        self.rrect(rect, (10, 12, 18), 14, border, alpha=232)

    def draw_debrief(self):
        cx = MAP_W // 2
        self.card((90, 90, MAP_W - 180, 460), GREEN)
        self.text_o(self.f40, "ROOM CLEARED", (cx, 140), GREEN, True)
        for i, line in enumerate(self.debrief):
            self.text(self.f16, line, (cx, 200 + i * 24), WHITE, True)
        self.text(self.f22, "Mistakes this room", (cx, 280), YEL, True)
        if not self.room_bad:
            self.text(self.f16, "None - textbook entry!", (cx, 315), GREEN, True)
        for i, (k, v) in enumerate(self.room_bad.most_common(6)):
            self.text(self.f16, f"{k}  x{v}", (cx, 315 + i * 24), RED, True)
        if int(self.tt * 2) % 2:
            self.text(self.f16, "ENTER - next room", (cx, 510), GREY, True)

    def draw_end(self, win):
        cx = MAP_W // 2
        self.card((60, 70, MAP_W - 120, 500), GREEN if win else RED)
        if win:
            sc = self.engine.score
            grade, gc = (("S", (255, 215, 90)) if sc >= 2800 else ("A", GREEN) if sc >= 2000 else
                         ("B", CYAN) if sc >= 1200 else ("C", GREY))
            self.text_o(self.f40, "MISSION COMPLETE", (cx, 120), GREEN, True)
            self.text_o(self.f64, f"GRADE {grade}", (cx, 190), gc, True)
            self.text(self.f22, f"Final score: {sc}", (cx, 245), WHITE, True)
        else:
            self.text_o(self.f40, "MISSION FAILED", (cx, 120), RED, True)
            self.text(self.f22, self.fail_reason, (cx, 180), WHITE, True)
            self.text(self.f16, f"Score: {self.engine.score}", (cx, 215), GREY, True)
        self.text(self.f22, "Your most common mistakes", (cx, 285), YEL, True)
        if not self.run_bad:
            self.text(self.f16, "None!", (cx, 320), GREEN, True)
        for i, (k, v) in enumerate(self.run_bad.most_common(6)):
            rule = next((r for r in self.rules if r.name == k), None)
            tip = f" - {rule.description}" if rule else ""
            self.text(self.f13, (f"{k} x{v}{tip}")[:80], (cx, 320 + i * 24), RED, True)
        self.text(self.f16, "R - retry    ENTER - menu", (cx, 535), GREY, True)

    def draw_title(self):
        s = self.screen
        for y in range(0, H, 4):
            f = y / H
            pygame.draw.rect(s, (int(8 + 20 * f), int(10 + 8 * f), int(24 + 26 * f)), (0, y, W, 4))
        hz = 420
        for i in range(-16, 17):
            pygame.draw.line(s, (36, 86, 130), (W // 2 + i * 22, hz), (W // 2 + i * 190, H), 1)
        for k in range(14):
            f = ((k + (self.tt * 0.5) % 1) / 14) ** 2
            pygame.draw.line(s, (36, 86, 130), (0, hz + f * (H - hz)), (W, hz + f * (H - hz)), 1)
        pygame.draw.line(s, CYAN, (0, hz), (W, hz), 1)
        pulse = 0.5 + 0.5 * math.sin(self.tt * 2)
        for o, c in ((4, (20, 60, 100)), (2, (40, 120, 180)), (0, WHITE)):
            self.text(self.f64, "CQB TRAINER", (W // 2 + o * 0.5, 58 + o * 0.5), c, True)
        self.text(self.f16, "A tactical training game scored by a Python rules engine", (W // 2, 108),
                  shade(CYAN, .7 + .3 * pulse), True)
        for i, d in enumerate(("easy", "normal", "hard")):
            on = d == self.diff
            self.text(self.f22, f"[{i + 1}] {d.upper()}", (80 + i * 190, 140), YEL if on else DIM)
        self.rrect((60, 178, 500, 340), (8, 10, 16), 12, (50, 90, 130), alpha=215)
        self.rrect((580, 178, 460, 340), (8, 10, 16), 12, (50, 90, 130), alpha=215)
        self.text(self.f16, "RULES  (reward / penalty)", (80, 190), CYAN)
        for i, r in enumerate(self.rules):
            tag = "  FATAL" if r.fatal else ""
            self.text(self.f16, f"{r.id} {r.name:<22} +{r.reward:<3} -{r.penalty}{tag}", (80, 218 + i * 24),
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
            self.text(self.f16, line, (600, 190 + i * 24), CYAN if i == 0 else WHITE)
        if int(self.tt * 2) % 2 == 0:
            self.text_o(self.f22, "ENTER - start     S - SOLO FPS     ESC - quit", (W // 2, 620), GREEN, True)
        self.text(self.f13, "M mute   F2 scanlines   F1 coach   ISO controls: WASD+mouse / gamepad", (W // 2, 680), DIM, True)


def main():
    while True:
        g = Game()
        while g.running:
            dt = min(g.clock.tick(FPS) / 1000, 0.05)
            for e in pygame.event.get():
                g.handle_event(e)
            g.poll_pad()
            g.update(dt)
            g.draw()
        if g.go_solo:
            from solo import SoloGame
            s = SoloGame(g.diff)
            s.run()
            continue
        break
    pygame.quit()


if __name__ == "__main__":
    main()