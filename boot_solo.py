"""Boot loader for the bundled CQB solo FPS.

The exe's entire job: run the solo FPS and nothing else, and make it
impossible to be too dark. Guarantee = one additive near-white pass is
injected immediately before every pygame.display.flip(). Whatever moody
painting solo.py does underneath, the frame that actually reaches the monitor
is always lifted hard toward white/bright. (The world's own fill/light are
also nudged white in solo.py as a second layer.)

Entry: boots SoloGame("normal") directly. WASD + mouse (or a gamepad):
Z slice, C call, LMB fire. One window, no hub, no team choreography.
"""
import pygame

import solo as S

ADD_WHITE = (120, 140, 160, 255)  # RGBA additive: pulls every pixel bright


def _boot():
    g = S.SoloGame("normal")

    orig_flip = pygame.display.flip

    def bright_flip():
        ov = pygame.Surface(g.screen.get_size(), pygame.SRCALPHA)
        ov.fill(ADD_WHITE)
        g.screen.blit(ov, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        return orig_flip()

    pygame.display.flip = bright_flip
    try:
        g.run()
    finally:
        pygame.display.flip = orig_flip


if __name__ == "__main__":
    _boot()
