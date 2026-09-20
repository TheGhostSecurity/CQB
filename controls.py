"""Industry-standard control mapping for CQB Trainer (keyboard+mouse / gamepad).

Keyboard = classic FPS: WASD move, mouse look, LMB fire, R reload, F fire-mode.
Gamepad = Xbox/PlayStation layout (consistent indices across both brands):
  LS move, RS look, LT aim, RT fire, LB slice, RB reload,
  A interact/enter, X fire-mode cycle, Y call out, B hold rear,
  Back (Select) menu, Start pause.
"""
import pygame

DEADZONE = 0.22


def joy_axis(j, i):
    if not j:
        return 0.0
    try:
        v = j.get_axis(i)
    except (pygame.error, ValueError, IndexError):
        return 0.0
    return v if abs(v) > DEADZONE else 0.0


def joy_btn(j, i):
    if not j:
        return False
    try:
        return bool(j.get_button(i))
    except (pygame.error, ValueError, IndexError):
        return False


def any_joystick():
    if pygame.joystick.get_count() == 0:
        return None
    j = pygame.joystick.Joystick(0)
    j.init()
    return j


class Pad:
    """Reads the first connected gamepad in a stable, brand-neutral way."""

    BTN = dict(A=0, B=1, X=2, Y=3, LB=4, RB=5, BACK=6, START=7, LS=8, RS=9)

    def __init__(self):
        self.j = any_joystick()
        self.sel = self.j if self.j else None

    @property
    def present(self):
        return self.j is not None

    def move(self):
        """Left-stick (x, y) for movement, y forward-positive."""
        if not self.j:
            return (0.0, 0.0)
        x = joy_axis(self.j, 0)
        y = -joy_axis(self.j, 1)  # stick up = forward
        return (x, y)

    def look(self):
        """Right-stick (x, y); x turns, y pitches."""
        if not self.j:
            return (0.0, 0.0)
        return (joy_axis(self.j, 2), joy_axis(self.j, 3))

    def _ax(self, i):
        return joy_axis(self.j, i) if self.j else 0.0

    def fire(self):
        if not self.j:
            return False
        try:
            return self._ax(5) > 0.5 or self._ax(4) > 0.5 or self.btn("A")
        except (pygame.error, ValueError, IndexError):
            return self.btn("A")

    def btn(self, name):
        return joy_btn(self.j, self.BTN[name]) if self.j else False

    def hat(self):
        if not self.j:
            return None
        try:
            if self.j.get_numhats() > 0:
                h = self.j.get_hat(0)
                if h != (0, 0):
                    return h
        except (pygame.error, ValueError, IndexError):
            pass
        return None

    def btn_tap(self, name, states):
        if not self.j:
            return False
        b = self.btn(name)
        was = states.get(name, False)
        states[name] = b
        return b and not was


KEY_HINTS = [
    "KEYBOARD + MOUSE",
    "WASD  move     Mouse  look",
    "LMB  fire      R  reload",
    "F  fire mode   C  call out",
    "Z  slice (solo)   ESC  pause",
    "",
    "GAMEPAD (XBOX / PLAYSTATION)",
    "LS  move        RS  look",
    "RT  fire        RB  reload",
    "X  fire mode    Y  call out",
    "LB  slice       A  interact",
    "B  hold (rear)  START  pause",
    "",
    "TEAM MODE (command)",
    "1-4 send A-D   Arrows leave door",
    "TAB select     Mouse click engage",
    "GAMEPAD: A send   B hold rear",
    "X call   Y reload   LB slice   D-pad door",
]