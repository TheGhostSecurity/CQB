"""
CQB Rules Engine (game-design prototype)
-----------------------------------------
Generates a rule set for a close-quarters tactical GAME, scores player
actions with rewards/penalties, and exports the rules to JSON so any game
engine (Unity, Godot, Unreal, web) can load them.

Run:  python cqb_rules_engine.py
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict


# ------------------------------------------------------------------ data
@dataclass
class Rule:
    id: str
    name: str
    description: str
    trigger: str          # action type that activates this rule
    check: str            # name of a function in CHECKS
    reward: int           # points when the rule is followed
    penalty: int          # points lost when it is broken
    fatal: bool = False   # breaking it fails the run immediately


@dataclass
class Action:
    actor: str
    type: str             # slice_pie | enter | engage | hold | reload | call
    data: dict = field(default_factory=dict)


@dataclass
class Operator:
    name: str
    role: str
    sector: str
    ammo: int = 30


@dataclass
class Room:
    threats: list         # [{"id","sector","armed","civilian"}]
    sliced: bool = False
    entered: list = field(default_factory=list)


# ---------------------------------------------------------------- checks
# Each check returns True (rule followed) or False (rule broken).
def _target(a, room):
    return next((t for t in room.threats if t["id"] == a.data.get("target")), None)

def chk_sliced(a, team, room):      return room.sliced
def chk_stack_order(a, team, room): return a.actor == list(team)[len(room.entered)]
def chk_call(a, team, room):        return bool(a.data.get("call"))
def chk_ammo(a, team, room):        return team[a.actor].ammo >= 10
def chk_speed(a, team, room):       return a.data.get("seconds", 99) <= 4
def chk_no_funnel(a, team, room):   return a.data.get("steps_in_doorway", 0) <= 1
def chk_sector(a, team, room):
    return a.data.get("sector") == team[a.actor].sector or a.data.get("own_sector_clear", False)
def chk_no_flag(a, team, room):     return not a.data.get("muzzle_on_teammate", False)
def chk_no_civilian(a, team, room):
    t = _target(a, room)
    return not (t and t["civilian"])
def chk_priority(a, team, room):
    t = _target(a, room)
    if not t or t["civilian"]:
        return True
    armed_left = any(x["armed"] and not x["civilian"] for x in room.threats)
    return t["armed"] or not armed_left
def chk_rear(a, team, room):        return a.data.get("facing_back", False)

CHECKS = {f.__name__: f for f in [
    chk_sliced, chk_stack_order, chk_call, chk_ammo, chk_speed, chk_no_funnel,
    chk_sector, chk_no_flag, chk_no_civilian, chk_priority, chk_rear]}


# ------------------------------------------------------- rule generator
def generate_rules(difficulty: str = "normal") -> list[Rule]:
    """Build the rule set. Difficulty scales penalties."""
    mult = {"easy": 0.5, "normal": 1.0, "hard": 1.5}[difficulty]
    P = lambda x: int(x * mult)
    return [
        Rule("R01", "Slice the pie", "Check the room from outside before entering.",
             "enter", "chk_sliced", 10, P(15)),
        Rule("R02", "Stack order", "Operators enter in their assigned order.",
             "enter", "chk_stack_order", 10, P(15)),
        Rule("R03", "Announce entry", "Call out when moving through a door.",
             "enter", "chk_call", 5, P(10)),
        Rule("R04", "Ammo check", "Do not enter with a nearly empty weapon.",
             "enter", "chk_ammo", 5, P(10)),
        Rule("R05", "Speed", "Enter within 4 seconds of the go signal.",
             "enter", "chk_speed", 10, P(5)),
        Rule("R06", "Leave the fatal funnel", "Do not stall in the doorway.",
             "enter", "chk_no_funnel", 10, P(20)),
        Rule("R07", "Sector discipline", "Cover only your sector until it is clear.",
             "engage", "chk_sector", 10, P(15)),
        Rule("R08", "No flagging", "Never point your weapon at a teammate.",
             "engage", "chk_no_flag", 5, P(25)),
        Rule("R09", "Threat priority", "Engage armed threats before unarmed ones.",
             "engage", "chk_priority", 15, P(20)),
        Rule("R10", "Protect civilians", "Never fire on a civilian.",
             "engage", "chk_no_civilian", 0, P(100), fatal=True),
        Rule("R11", "Rear security", "The last operator watches behind the team.",
             "hold", "chk_rear", 10, P(20)),
        Rule("R12", "Call your reload", "Announce a reload so the team can cover you.",
             "reload", "chk_call", 5, P(10)),
    ]


# ------------------------------------------------------------ the engine
class Engine:
    def __init__(self, rules, team, room, score=100, fail_below=40):
        self.rules, self.team, self.room = rules, team, room
        self.score, self.fail_below = score, fail_below
        self.streak, self.failed, self.log = 0, False, []

    def step(self, action: Action):
        if self.failed:
            return
        for rule in (r for r in self.rules if r.trigger == action.type):
            ok = CHECKS[rule.check](action, self.team, self.room)
            if ok:
                self.streak += 1
                bonus = min(1 + self.streak // 5, 2)      # streak multiplier (max 2x)
                delta = rule.reward * bonus
            else:
                self.streak = 0
                delta = -rule.penalty
                if rule.fatal:
                    self.failed = True
            self.score += delta
            self.log.append((action.actor, action.type, rule.name,
                             "OK " if ok else "BAD", delta, self.score))
        self._apply(action)
        if self.score < self.fail_below:
            self.failed = True

    def adjust(self, actor, label, delta):
        """Apply a one-off bonus/penalty (e.g. taking a hit, room-clear bonus)."""
        self.score += delta
        self.log.append((actor, "event", label, "OK " if delta >= 0 else "BAD",
                         delta, self.score))
        if self.score < self.fail_below:
            self.failed = True

    def _apply(self, a: Action):
        if a.type == "slice_pie":
            self.room.sliced = True
        elif a.type == "enter":
            self.room.entered.append(a.actor)
        elif a.type == "engage":
            self.team[a.actor].ammo -= a.data.get("rounds", 1)
            self.room.threats = [t for t in self.room.threats
                                 if t["id"] != a.data.get("target")]
        elif a.type == "reload":
            self.team[a.actor].ammo = 30

    def report(self):
        for row in self.log:
            print(f"{row[0]:>2} {row[1]:<10} {row[2]:<24} {row[3]} {row[4]:>+5} -> {row[5]}")
        print("RESULT:", "FAILED" if self.failed else "PASSED", "| score", self.score)


# ------------------------------------------------------------ save / load
def export_rules(rules, path="cqb_rules.json"):
    with open(path, "w") as f:
        json.dump([asdict(r) for r in rules], f, indent=2)

def load_rules(path="cqb_rules.json"):
    with open(path) as f:
        return [Rule(**r) for r in json.load(f)]


# ------------------------------------------------------------------ demo
def new_team():
    return {"A": Operator("A", "point", "left"),
            "B": Operator("B", "second", "right"),
            "C": Operator("C", "third", "far"),
            "D": Operator("D", "rear", "rear")}

def new_room():
    return Room(threats=[
        {"id": "T1", "sector": "left",  "armed": True,  "civilian": False},
        {"id": "T2", "sector": "right", "armed": False, "civilian": False},
        {"id": "C1", "sector": "far",   "armed": False, "civilian": True}])

if __name__ == "__main__":
    rules = generate_rules("normal")
    export_rules(rules)

    print("=== Good run ===")
    e = Engine(rules, new_team(), new_room())
    good = [
        Action("A", "slice_pie"),
        Action("A", "enter", {"call": "entering", "seconds": 3, "steps_in_doorway": 1}),
        Action("B", "enter", {"call": "entering", "seconds": 3, "steps_in_doorway": 1}),
        Action("A", "engage", {"target": "T1", "sector": "left"}),
        Action("B", "engage", {"target": "T2", "sector": "right"}),
        Action("D", "hold", {"facing_back": True}),
    ]
    for a in good: e.step(a)
    e.report()

    print("\n=== Bad run ===")
    e = Engine(rules, new_team(), new_room())
    bad = [
        Action("B", "enter", {"seconds": 7, "steps_in_doorway": 3}),
        Action("A", "engage", {"target": "T2", "sector": "right", "muzzle_on_teammate": True}),
        Action("C", "engage", {"target": "C1", "sector": "far"}),
    ]
    for a in bad: e.step(a)
    e.report()
