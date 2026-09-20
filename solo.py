"""Solo FPS mode for CQB Trainer.

You play one operator, first-person, with industry-standard controls
(WASD + mouse, or a gamepad). The CQB rules engine still scores every
decision: slice the pie, call out, ammo economy, three fire modes, threat
priority, and the fatal civilian rule.
"""
import math
import random

import pygame

import render3d as R
from controls import Pad, KEY_HINTS
from cqb_game import (MAP_W as MP, W, H, ROOM, GREEN, RED, YEL, CYAN, WHITE, GREY, DIM, ORANGE,
                      shade, LEVELS, THEMES, make_room, make_decor, Sfx,
                      build_vignette, build_scanlines, make_glow, FPS)
from cqb_rules_engine import Engine, Action, Operator

FIRE_MODES = ["SEMI", "BURST", "AUTO"]
MODE_ROUNDS = {"SEMI": 1, "BURST": 3, "AUTO": 1}
PLAY_SPEED = 230.0
RAD = 0.42
EYE = 1.62
FOCAL = 560.0


def world_z(py):
    return ROOM.bottom - py  # door at z=0, back wall at z=ROOM.height


class SoloGame:
    def __init__(self, diff="normal"):
        pygame.quit()
        pygame.init()
        self.diff = diff
        self.sfx = Sfx()
        pygame.display.set_caption("CQB Trainer - Solo FPS")
        pygame.display.quit()
        self.screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
        self.world = pygame.Surface((MP, H))
        self.vig = build_vignette().convert_alpha()
        self.scan = build_scanlines().convert_alpha()
        self.glow_l = make_glow(200, 220)
        mono = "consolas,dejavusansmono,couriernew,monospace"
        self.f13 = pygame.font.SysFont(mono, 13)
        self.f16 = pygame.font.SysFont(mono, 16)
        self.f22 = pygame.font.SysFont(mono, 22, bold=True)
        self.f40 = pygame.font.SysFont(mono, 40, bold=True)
        self.f64 = pygame.font.SysFont(mono, 64, bold=True)
        self.pad = Pad()
        self.b_st = {}
        self.clock = pygame.time.Clock()
        self.state, self.running = "menu", True
        self.start_run()

    # --------------------------------------------------------- level setup
    def start_run(self):
        from cqb_rules_engine import generate_rules
        self.rules = generate_rules(self.diff)
        self.engine, self.level = None, 0
        self.bad, self.feed, self.floaters = [], [], []
        self.fail_reason = ""
        self.disp_score = 100.0
        self.sfx.drone_on()
        self.new_level()

    def new_level(self):
        self.cfg = LEVELS[self.level]
        self.theme = THEMES[self.cfg["name"]]
        self.door_x, self.room = make_room(self.cfg)
        self.op = Operator("A", "point", "solo", 30)
        self.team = {"A": self.op}
        if self.engine is None:
            self.engine = Engine(self.rules, self.team, self.room)
        else:
            self.engine.team, self.engine.room = self.team, self.room
        self.log_seen = len(self.engine.log)
        self.entered = False
        self.pending_call, self.t = "", 0.0
        self.slice_t0 = -999.0
        self.hits, self.down = 0, []
        self.tracers, self.flashes = [], []
        self.fire_mode = "SEMI"
        self.fire_cd, self.reload_until = 0.0, 0.0
        self.trigger_held = False
        self.threat_t, self.last_sec = self.cfg["fire"], 99
        self.msg_text, self.msg_col = "SLICE (Z) at the doorway, then step in. Call first (C).", WHITE
        self.trauma, self.freeze = 0.0, 0.0
        self.fx_flash = (RED, 0.0, 0.3)
        self.recoil, self.bob_t = 0.0, 0.0
        self.px, self.pz = float(self.door_x), -100.0
        self.yaw, self.pitch = 0.0, 0.0
        self.build_world()
        self.state = "play"

    def build_world(self):
        rng = random.Random(self.level * 101 + random.randint(0, 999))
        self.prop_rects = make_decor(self.door_x, self.room.threats, rng)
        wall_col = shade(self.theme["c1"], 0.7)
        self.faces = []
        self.faces += R.room_model(ROOM.width, ROOM.height, 320, wall_col,
                                   self.theme["c2"], self.door_x - ROOM.left, 84)
        self.faces += R.box_props([(x, y, w, h) for (x, y, w, h) in self.prop_rects],
                                  1.1, self.theme["prop"], py0=ROOM.bottom)
        hw = 42
        self.boxes = [(60, -320, self.door_x - hw, 0.0),
                      (self.door_x + hw, -320, 720, 0.0)]
        for (x, y, w, h) in self.prop_rects:
            self.boxes.append((x, world_z(y + h), x + w, world_z(y)))
        for t in self.room.threats:
            t["pos3"] = (t["pos"][0], 0.0, ROOM.bottom - t["pos"][1])
            t.setdefault("phase", random.random() * 6.28)

    # ------------------------------------------------------------- queries
    def cam(self):
        return (self.px, EYE, self.pz)

    def hostiles(self):
        return [t for t in self.room.threats if not t["civilian"]]

    def los_clear(self, a, b):
        for box in self.boxes:
            if seg_aabb(a, b, box):
                return False
        if not (60 <= self.px <= 720):
            return False
        return True

    def aim_target(self, max_ang=0.16, max_d=520):
        o = self.cam()
        d = R.fwd_vec(self.yaw, self.pitch)
        best, best_d = None, max_d
        for t in self.room.threats:
            tp = (t["pos3"][0], 1.15, t["pos3"][2])
            to = R.sub(tp, o)
            L = R.length(to)
            if L < 0.6 or L > best_d:
                continue
            if R.dot(R.norm(to), d) < math.cos(max_ang):
                continue
            if not self.los_clear(o, to):
                continue
            best, best_d = t, L
        return best

    def muzzle(self):
        f = R.fwd_vec(self.yaw, self.pitch)
        r = R.norm(R.cross((0, 1, 0), f))
        c = self.cam()
        return R.add(R.add(c, R.mul(f, 0.7)), R.mul(r, 0.24))

    # -------------------------------------------------------------- actions
    def say(self, text, col=WHITE):
        self.msg_text, self.msg_col = text, col

    def do_slice(self):
        if self.room.sliced:
            return self.say("Room already sliced.", GREY)
        if not -10 <= self.pz < 24:
            return self.say("Get to the doorway, then slice (Z / LB).", GREY)
        self.engine.step(Action("A", "slice_pie"))
        self.slice_t0 = self.t
        self.sfx.play("whoosh")
        self.say("Pie sliced - contacts sighted. Call (C) and step through the door.", GREEN)

    def do_call(self):
        self.pending_call = "Entering!"
        self.sfx.play("radio")
        self.say("CALL READY - spoken on your reload or door entry.", YEL)

    def do_reload(self):
        if self.t < self.reload_until:
            return
        if self.op.ammo >= 28:
            return self.say("Magazine is nearly full.", GREY)
        self.engine.step(Action("A", "reload", {"call": self.pending_call}))
        self.reload_until = self.t + 1.4
        self.pending_call = ""
        self.sfx.play("reload")
        self.flush("A")
        self.say("Reloading... keep your sector covered.", WHITE)

    def cycle_mode(self):
        self.fire_mode = FIRE_MODES[(FIRE_MODES.index(self.fire_mode) + 1) % 3]
        self.sfx.play("click")
        self.say(f"FIRE MODE: {self.fire_mode}", CYAN)

    def try_enter(self):
        if self.entered:
            return
        self.entered = True
        sec = max(0.0, self.t - self.slice_t0)
        self.engine.step(Action("A", "enter", {"call": self.pending_call or "", "seconds": sec,
                                               "steps_in_doorway": 0, "own_sector_clear": True}))
        self.pending_call = ""
        self.flush("A")
        if not self.room.sliced:
            self.say("You entered without slicing the pie - 10:1 odds next time.", RED)
        elif sec > 4:
            self.say("Entry too slow - slice, call, move.", YEL)
        else:
            self.say("Inside. Armed threats first - never shoot civilians.", GREEN)

    def fire(self):
        if not self.room.sliced:
            return self.say("You can't see the room yet - slice first (Z / LB).", RED)
        if self.t < self.reload_until:
            return
        if self.op.ammo < 1:
            self.sfx.play("click")
            return self.say("Out of ammo - reload (R / RB).", RED)
        t = self.aim_target()
        if t is None:
            return
        rounds = MODE_ROUNDS[self.fire_mode]
        lethal = t["armed"] or t["civilian"]
        self.engine.step(Action("A", "engage", {"target": t["id"], "sector": t["sector"],
                                                "own_sector_clear": True,
                                                "muzzle_on_teammate": False,
                                                "rounds": rounds if lethal else 0}))
        self.fire_cd = 0.13 if self.fire_mode != "BURST" else 0.42
        self.recoil = 0.9
        self.freeze = 0.03
        self.ammo_fx(t, rounds)
        if t["civilian"]:
            self.fail_reason = "You fired on a civilian."
        elif not t["armed"]:
            self.say("Suspect secured. Move on.", WHITE)
        self.flush("A")

    def ammo_fx(self, t, rounds):
        tp = (t["pos3"][0], 1.15, t["pos3"][2])
        m = self.muzzle()
        shots = 1 if self.fire_mode == "SEMI" else 3
        for _ in range(shots):
            self.tracers.append(dict(a=m, b=tp, life=0.14, col=(255, 240, 170)))
        self.flashes.append(dict(pos=tp, life=0.09))
        self.sfx.play("shot" if self.fire_mode == "SEMI" else "burst")
        if t["armed"] and not t["civilian"]:
            self.down.append(dict(pos3=tp, col=(60, 28, 30)))

    # -------------------------------------------------------------- scoring
    def flush(self, actor=""):
        eng = self.engine
        rows = eng.log[self.log_seen:]
        self.log_seen = len(eng.log)
        if not rows:
            return
        total = sum(r[4] for r in rows)
        self.feed.append((f"{rows[0][0]} {rows[0][1]}: {total:+d}", GREEN if total >= 0 else RED))
        self.feed = self.feed[-6:]
        self.floaters.append(dict(text=f"{total:+d}", ttl=1.2, col=GREEN if total >= 0 else RED))
        any_bad = any(r[3].strip() == "BAD" for r in rows)
        for r in rows:
            if r[3].strip() == "BAD":
                self.bad.append(r[2])
        if any_bad:
            self.sfx.play("bad")
            self.fx_flash = (RED, 0.22, 0.22)
        elif total > 0:
            self.sfx.play("chime")
        if eng.failed and self.state == "play":
            self.fail_reason = self.fail_reason or "Score fell below the minimum."
            self.state = "over"
            self.sfx.drone_off()
            self.sfx.play("fatal" if "civilian" in self.fail_reason else "lose")
            self.fx_flash = (RED, 0.6, 0.6)

    def finish_room(self):
        eng = self.engine
        elapsed = self.t - (self.slice_t0 if self.slice_t0 > 0 else self.t)
        par = 30 - 2 * self.level
        bonus = 25 + max(0, int(par - elapsed)) * 2
        eng.adjust("Team", "Room cleared", bonus)
        self.flush("A")
        if self.state != "play":
            return
        self.debrief = [f"Time: {elapsed:4.1f}s (par {par}s)   Hits taken: {self.hits}",
                        f"Room bonus: +{bonus}   Score: {eng.score}"]
        self.state = "debrief"
        self.sfx.play("combo")
        self.fx_flash = (GREEN, 0.5, 0.5)

    # ---------------------------------------------------------------- input
    def press(self, k):
        if k == pygame.K_m:
            self.sfx.toggle()
            return
        if self.state == "play":
            if k == pygame.K_ESCAPE:
                self.state = "menu"
            elif k == pygame.K_z or k == pygame.K_1:
                self.do_slice()
            elif k == pygame.K_c or k == pygame.K_x:
                self.do_call()
            elif k == pygame.K_r:
                self.do_reload()
            elif k == pygame.K_f or k == pygame.K_2:
                self.cycle_mode()
            return
        if k == pygame.K_ESCAPE or k == pygame.K_q:
            self.running = False
            return
        if self.state == "menu":
            if k in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = "play"
            elif k == pygame.K_r:
                self.start_run()
            elif k == pygame.K_r:
                self.start_run()
            return
        if self.state == "debrief" and k in (pygame.K_RETURN, pygame.K_SPACE):
            self.level += 1
            if self.level >= len(LEVELS):
                self.state = "win"
                self.sfx.drone_off()
                self.sfx.play("win")
            else:
                self.new_level()
            return
        if self.state in ("over", "win"):
            if k == pygame.K_r:
                self.start_run()

    def walk_input(self):
        k = pygame.key.get_pressed()
        x, y = 0.0, 0.0
        if k:
            if k[pygame.K_w] or k[pygame.K_UP]:
                y += 1
            if k[pygame.K_s] or k[pygame.K_DOWN]:
                y -= 1
            if k[pygame.K_a] or k[pygame.K_LEFT]:
                x -= 1
            if k[pygame.K_d] or k[pygame.K_RIGHT]:
                x += 1
        mx, my = self.pad.move()
        return max(-1.0, min(1.0, x + mx)), max(-1.0, min(1.0, y + my))

    # --------------------------------------------------------------- update
    def update(self, dt):
        self.t += dt
        self.bob_t += dt
        self.trauma = max(0.0, self.trauma - dt * 1.8)
        self.disp_score += (self.engine.score - self.disp_score) * min(1, dt * 7)
        fc, ft, fd = self.fx_flash
        self.fx_flash = (fc, max(0.0, ft - dt), fd)
        for f in self.floaters:
            f["ttl"] -= dt
        self.floaters = [f for f in self.floaters if f["ttl"] > 0]
        self.recoil = max(0.0, self.recoil - dt * 6)
        if self.state != "play":
            return
        if self.freeze > 0:
            self.freeze -= dt
            dt *= 0.2
        self.fire_cd = max(0.0, self.fire_cd - dt)
        # look
        try:
            mx, my = pygame.mouse.get_rel()
        except pygame.error:
            mx, my = 0, 0
        lx, ly = self.pad.look()
        self.yaw += mx * 0.0022 + lx * 0.030
        self.pitch -= (my * 0.0022 - ly * 0.030)
        self.pitch = max(-1.25, min(1.25, self.pitch))
        # move
        ix, iy = self.walk_input()
        f = R.fwd_vec(self.yaw, 0)
        r = R.norm(R.cross((0, 1, 0), f))
        move_player(self, (f[0] * iy + r[0] * ix) * PLAY_SPEED * dt,
                    (f[2] * iy + r[2] * ix) * PLAY_SPEED * dt)
        # fire (semi needs a fresh press; auto/burst fire while held)
        trigger = False
        if pygame.mouse.get_pressed():
            trigger = pygame.mouse.get_pressed()[0]
        trigger = trigger or self.pad.fire()
        if trigger and (self.fire_mode == "AUTO" or not self.trigger_held) and self.fire_cd <= 0:
            self.fire()
        self.trigger_held = trigger
        # enter
        if not self.entered and self.pz >= 0:
            self.try_enter()
        # threat clock
        armed = [t for t in self.room.threats if t["armed"] and not t["civilian"]]
        if self.entered and armed:
            self.threat_t -= dt
            sec = int(self.threat_t)
            if self.threat_t < 3.5 and sec != self.last_sec:
                self.sfx.play("tick")
            self.last_sec = sec
            if self.threat_t <= 0:
                self.enemy_fire(armed)
                self.threat_t = self.cfg["fire"]
        elif self.entered and self.state == "play" and not self.room.threats:
            self.finish_room()

    def enemy_fire(self, armed):
        o = self.cam()
        shoot = [t for t in armed if self.los_clear((t["pos3"][0], 1.1, t["pos3"][2]), o)]
        if not shoot:
            return
        t = random.choice(shoot)
        self.tracers.append(dict(a=(t["pos3"][0], 1.1, t["pos3"][2]), b=self.cam(),
                                 life=0.16, col=(255, 130, 90)))
        self.sfx.play("enemy")
        self.sfx.play("hit")
        self.engine.adjust("A", "Hit taken", -30)
        self.hits += 1
        self.fx_flash = (RED, 0.4, 0.4)
        self.trauma = 1.0
        self.say("You took a hit - neutralize armed threats faster!", RED)
        self.flush("A")

    # ----------------------------------------------------------------- draw
    def text(self, font, s, pos, col=WHITE, center=False):
        surf = font.render(s, True, col)
        rect = surf.get_rect(center=pos) if center else surf.get_rect(topleft=pos)
        self.screen.blit(surf, rect)

    def text_o(self, font, s, pos, col=WHITE, center=False, alpha=255):
        base = font.render(s, True, (8, 8, 12))
        top = font.render(s, True, col)
        for o in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            r = base.get_rect(center=pos) if center else base.get_rect(topleft=pos)
            base.set_alpha(alpha)
            self.screen.blit(base, (r.x + o[0], r.y + o[1]))
        top.set_alpha(alpha)
        self.screen.blit(top, top.get_rect(center=pos) if center else top.get_rect(topleft=pos))

    def draw_world(self):
        w = self.world
        w.fill((6, 8, 14))
        cam = self.cam()
        light = (0.5, 0.7, 0.5) if self.room.sliced else (0.18, 0.26, 0.26)
        faces = list(self.faces)
        for d in self.down:
            faces.append((((d["pos3"][0] - 0.4, 0.0, d["pos3"][2] - 0.5),
                           (d["pos3"][0] + 0.4, 0.0, d["pos3"][2] - 0.5),
                           (d["pos3"][0] + 0.4, 0.12, d["pos3"][2] + 0.5),
                           (d["pos3"][0] - 0.4, 0.12, d["pos3"][2] + 0.5)), d["col"]))
        R.draw_scene(w, cam, self.yaw, self.pitch, faces, f=FOCAL, light=light)
        # threats only visible after the pie is sliced
        if self.room.sliced:
            for t in self.room.threats:
                self.draw_npc(w, t)
        if not self.room.sliced:
            a = int(210 - 30 * math.sin(self.t * 3))
            dim = pygame.Surface((MP, H), pygame.SRCALPHA)
            dim.fill((3, 5, 11, a))
            w.blit(dim, (0, 0))
        else:
            w.blit(self.glow_l, (self.door_x - self.glow_l.get_width() / 2, 40))

    def draw_npc(self, w, t):
        acc = (92, 30, 34) if t["armed"] else ((46, 64, 110) if t["civilian"] else (110, 70, 26))
        faces = R.soldier_model(acc, civilian=t["civilian"],
                                armed=t["armed"] and not t["civilian"],
                                hands_up=t["civilian"] or not t["armed"])
        p3 = t["pos3"]
        rot = math.atan2(self.px - p3[0], self.pz - p3[2])
        moved = [(R.yaw_rotate(vs, rot, (p3[0], 0, p3[2])), col) for (vs, col) in faces]
        R.draw_scene(w, self.cam(), self.yaw, self.pitch, moved, f=FOCAL,
                     light=(0.5, 0.7, 0.5))
        lab = "C" if t["civilian"] else ("H" if t["armed"] else "U")
        col = (96, 150, 255) if t["civilian"] else ((255, 70, 70) if t["armed"] else (255, 160, 60))
        p = R.project(self.cam(), self.yaw, self.pitch, (p3[0], 2.1, p3[2]), MP, H, FOCAL)
        if p:
            surf = self.f13.render(lab, True, col)
            w.blit(surf, surf.get_rect(center=(p[0], p[1])))

    def draw_effects(self):
        for tr in self.tracers:
            a = R.project(self.cam(), self.yaw, self.pitch, tr["a"], MP, H, FOCAL)
            b = R.project(self.cam(), self.yaw, self.pitch, tr["b"], MP, H, FOCAL)
            if a and b:
                f = tr["life"] / 0.15
                pygame.draw.line(self.screen, shade(tr["col"], .5 + .5 * f),
                                 (a[0], a[1]), (b[0], b[1]), 3)
        self.tracers = [t for t in self.tracers if t["life"] > 0]
        # crosshair
        cx, cy = W - MP + MP // 2, H // 2
        tgt = self.aim_target()
        col = RED if tgt else WHITE
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            pygame.draw.rect(self.screen, col, (cx - 12, cy - 5, 9, 3))
        pygame.draw.rect(self.screen, col, (cx + 3, cy - 5, 9, 3))
        pygame.draw.rect(self.screen, col, (cx - 5, cy - 12, 3, 9))
        pygame.draw.rect(self.screen, col, (cx - 5, cy + 3, 3, 9))
        pygame.draw.circle(self.screen, col, (cx, cy), 2)

    def draw_viewmodel(self):
        bx = math.sin(self.bob_t * 9) * 0.012
        by = abs(math.cos(self.bob_t * 9)) * 0.02
        rec = self.recoil * 0.06
        faces = R.box(0.26, -0.20, 0.28, 0.10, 0.12, 0.10, (26, 28, 34))
        faces += R.box(0.26, -0.16, 0.42, 0.08, 0.19, 0.42, (20, 22, 27))
        faces += R.box(0.20, -0.30, 0.32, 0.05, 0.04, 0.06, (40, 42, 50))
        faces += R.box(0.24, -0.16, 0.62, 0.05, 0.05, 0.12, (10, 10, 12))
        R.draw_scene(self.screen, (bx, -0.18 - by - rec, 0.02), 0, 0, faces, f=FOCAL)
        R.draw_scene(self.screen, (0.0, -0.20 - by - rec, 0.02), 0, 0,
                     R.box(0.28, -0.05, 0.08, 0.16, 0.16, 0.10, (52, 40, 64)), f=FOCAL)

    def draw_hud(self):
        eng = self.engine
        sc = int(self.disp_score)
        col = GREEN if eng.score >= 100 else (YEL if eng.score >= 60 else RED)
        self.text(self.f16, f"SCORE {sc}", (14, 12), col)
        self.text(self.f16, f"AMMO {self.op.ammo}", (14, 34), RED if self.op.ammo < 10 else WHITE)
        self.text(self.f16, f"MODE {self.fire_mode}", (14, 56), CYAN)
        self.text(self.f16, f"CALL: {'READY' if self.pending_call else '-'}", (14, 78),
                  YEL if self.pending_call else DIM)
        armed = [t for t in self.room.threats if t["armed"] and not t["civilian"]]
        if self.entered and armed:
            frac = self.threat_t / self.cfg["fire"]
            pygame.draw.rect(self.screen, (28, 31, 42), (14, 100, 230, 10), border_radius=3)
            fw = int(230 * max(0, min(1, frac)))
            if fw > 2:
                pygame.draw.rect(self.screen, RED if frac < 0.6 else ORANGE,
                                 (15, 101, fw - 2, 8), border_radius=2)
            self.text(self.f13, "ARMED CLOCK", (14, 84), GREY)
        for i, (line, c) in enumerate(self.feed[-4:]):
            self.text(self.f13, line, (14, H - 96 + i * 15), shade(c, 0.9))
        for f in self.floaters:
            self.text_o(self.f22, f["text"], (MP // 2, 110), f["col"], True,
                        alpha=int(255 * min(1, f["ttl"])))
        dusk = "  (entry over 4s costs points)" if (self.entered and not self.room.sliced) else ""
        self.text(self.f13, "WASD move   Mouse look   LMB fire   F mode   R reload   C call   Z slice"
                            + ("" if self.room.sliced else "  [SLICE first by the door]"), (14, H - 26), DIM)
        if self.msg_text:
            lines = self.wrap(self.f16, self.msg_text, 600)
            for i, line in enumerate(lines):
                self.text_o(self.f16, line, (MP // 2, 130 + i * 20), self.msg_col, True)

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

    def draw(self):
        self.screen.blit(self.world, (0, 0))
        if self.state == "play":
            self.draw_effects()
            self.draw_viewmodel()
            self.draw_hud()
        self.draw_post()
        if self.state == "debrief":
            self.draw_debrief()
        elif self.state == "over":
            self.draw_end(False)
        elif self.state == "win":
            self.draw_end(True)
        elif self.state == "menu":
            self.draw_menu()
        pygame.display.flip()

    def draw_post(self):
        fc, ft, fd = self.fx_flash
        if ft > 0:
            v = pygame.Surface((W, H), pygame.SRCALPHA)
            v.fill((*fc, int(90 * ft / fd)))
            self.screen.blit(v, (0, 0))
        self.screen.blit(self.vig, (0, 0))
        if self.trauma > 0:
            v = pygame.Surface((W, H), pygame.SRCALPHA)
            v.fill((255, 30, 30, int(45 * self.trauma)))
            self.screen.blit(v, (0, 0))
            self.screen.blit(v, (int(self.trauma ** 2 * 12), 0))
        self.screen.blit(self.scan, (0, 0))

    def card(self, rect, border):
        s = pygame.Surface(pygame.Rect(rect).size, pygame.SRCALPHA)
        pygame.draw.rect(s, (10, 12, 18, 232), s.get_rect(), border_radius=14)
        pygame.draw.rect(s, border, s.get_rect(), 1, border_radius=14)
        self.screen.blit(s, pygame.Rect(rect).topleft)

    def draw_debrief(self):
        cx = MP // 2
        self.card((90, 90, MP - 180, 460), GREEN)
        self.text_o(self.f40, "ROOM CLEARED", (cx, 140), GREEN, True)
        for i, line in enumerate(self.debrief):
            self.text(self.f16, line, (cx, 200 + i * 24), WHITE, True)
        self.text(self.f22, "Mistakes this room", (cx, 280), YEL, True)
        if not self.bad:
            self.text(self.f16, "None - textbook solo entry!", (cx, 315), GREEN, True)
        for i, k in enumerate(sorted(set(self.bad))[:6]):
            self.text(self.f16, k, (cx, 315 + i * 24), RED, True)
        if int(self.t * 2) % 2:
            self.text(self.f16, "ENTER - next room", (cx, 510), GREY, True)

    def draw_end(self, win):
        cx = MP // 2
        self.card((60, 70, MP - 120, 500), GREEN if win else RED)
        if win:
            sc = self.engine.score
            grade, gc = (("S", (255, 215, 90)) if sc >= 2800 else ("A", GREEN) if sc >= 2000 else
                         ("B", CYAN) if sc >= 1200 else ("C", GREY))
            self.text_o(self.f40, "MISSION COMPLETE", (cx, 120), GREEN, True)
            self.text_o(self.f64, f"GRADE {grade}", (cx, 190), gc, True)
            self.text(self.f22, f"Final score: {sc}", (cx, 250), WHITE, True)
        else:
            self.text_o(self.f40, "MISSION FAILED", (cx, 120), RED, True)
            self.text(self.f22, self.fail_reason, (cx, 180), WHITE, True)
            self.text(self.f16, f"Score: {self.engine.score}", (cx, 215), GREY, True)
        self.text(self.f22, "Most common mistakes", (cx, 285), YEL, True)
        if not self.bad:
            self.text(self.f16, "None!", (cx, 320), GREEN, True)
        for i, k in enumerate(sorted(set(self.bad))[:6]):
            self.text(self.f13, k[:70], (cx, 320 + i * 24), RED, True)
        self.text(self.f16, "R - retry    ENTER - menu    Q - quit", (cx, 535), GREY, True)

    def draw_menu(self):
        self.card((80, 60, MP - 160, H - 120), CYAN)
        cx = MP // 2
        self.text_o(self.f40, "PAUSED - CONTROLS", (cx, 110), CYAN, True)
        for i, line in enumerate(KEY_HINTS):
            self.text(self.f16, line, (cx, 160 + i * 21),
                      YEL if line.startswith(("KEY", "GAMEPAD")) else WHITE, True)
        self.text(self.f16, "RETURN - resume    Q - back to menu    R - restart", (cx, H - 110), GREY, True)

    # ----------------------------------------------------------------- loop
    def run(self):
        try:
            pygame.event.set_grab(True)
            pygame.mouse.set_visible(False)
        except pygame.error:
            pass
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.05)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN:
                    self.press(e.key)
            self.poll_pad()
            self.update(dt)
            self.draw_world()
            self.draw()
        try:
            pygame.event.set_grab(False)
            pygame.mouse.set_visible(True)
        except pygame.error:
            pass

    def poll_pad(self):
        if not self.pad.present:
            return
        if self.state == "play":
            if self.pad.btn_tap("LB", self.b_st):
                self.do_slice()
            if self.pad.btn_tap("Y", self.b_st):
                self.do_call()
            if self.pad.btn_tap("RB", self.b_st):
                self.do_reload()
            if self.pad.btn_tap("X", self.b_st):
                self.cycle_mode()
            if self.pad.btn_tap("START", self.b_st):
                self.state = "menu"
        elif self.state == "menu":
            if self.pad.btn_tap("START", self.b_st) or self.pad.btn_tap("A", self.b_st):
                self.state = "play"
            if self.pad.btn_tap("BACK", self.b_st):
                self.running = False


def move_player(g, dx, dz):
    nx, nz = g.px + dx, g.pz + dz
    nx = max(60 + RAD, min(720 - RAD, nx))
    nz = max(-320 + RAD, min(332 - RAD, nz))
    for (x0, z0, x1, z1) in g.boxes:
        cx = min(max(nx, x0), x1)
        cz = min(max(nz, z0), z1)
        dxb, dzb = nx - cx, nz - cz
        d2 = dxb * dxb + dzb * dzb
        if d2 < RAD * RAD:
            if d2 > 1e-9:
                d = math.sqrt(d2)
                push = RAD - d
                nx += dxb / d * push
                nz += dzb / d * push
            else:
                nx, nz = g.px, g.pz
    g.px, g.pz = nx, nz


def seg_aabb(a, b, box):
    x0, z0, x1, z1 = box
    tmin, tmax = 0.0, 1.0
    for (p0, p1, lo, hi) in ((a[0], b[0], x0, x1), (a[2], b[2], z0, z1)):
        if abs(p1 - p0) < 1e-9:
            if p0 < lo or p0 > hi:
                return False
        else:
            t1 = (lo - p0) / (p1 - p0)
            t2 = (hi - p0) / (p1 - p0)
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return False
    return True