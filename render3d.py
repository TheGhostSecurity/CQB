"""Low-poly software 3D renderer for CQB Trainer (solo FPS mode).

No external engine: tiny vector math + painter's-algorithm polygon rasterizer
on top of pygame, plus procedural models for soldiers, rifles and room props.
"""
import math

import pygame

# ---------------------------------------------------------------- vector math
V3 = tuple  # (x, y, z)


def sub(a: V3, b: V3) -> V3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a: V3, b: V3) -> V3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a: V3, s: float) -> V3:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: V3, b: V3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: V3, b: V3) -> V3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def norm(a: V3) -> V3:
    l = math.sqrt(dot(a, a)) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)


def length(a: V3) -> float:
    return math.sqrt(dot(a, a))


def fwd_vec(yaw: float, pitch: float) -> V3:
    """Camera forward vector. yaw rotates around Y, +pitch looks up (+Y)."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    return (sy * cp, sp, cy * cp)


# ------------------------------------------------------------------ camera
def project(cam: V3, yaw: float, pitch: float, p: V3, w: int, h: int, f: float,
            near: float = 0.05):
    """Perspective-project world point p. Returns (screen_x, screen_y, depth)
    or None if the point is behind the near plane."""
    fv = fwd_vec(yaw, pitch)
    up = (0.0, 1.0, 0.0)
    right = norm(cross(up, fv))
    up2 = cross(fv, right)
    d = sub(p, cam)
    z = dot(d, fv)
    if z <= near:
        return None
    x = dot(d, right)
    y = dot(d, up2)
    sx = w / 2 + x * f / z
    sy = h / 2 - y * f / z
    return (sx, sy, z)


def ray(cam: V3, yaw: float, pitch: float) -> tuple:
    """Origin + unit direction of the screen-center ray."""
    return cam, fwd_vec(yaw, pitch)


def ray_plane(origin: V3, dir_: V3, y: float) -> V3:
    """Intersection of a ray with the horizontal plane Y=y, or None."""
    if dir_[1] == 0:
        return None
    t = (y - origin[1]) / dir_[1]
    if t <= 0:
        return None
    return add(origin, mul(dir_, t))


# ------------------------------------------------------------------ geometry
def box_face(center: V3, size: V3, col):
    """Six quads for an axis-aligned box, each face (verts, color)."""
    x, y, z = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    faces = []
    c = (x - hx, y - hy, z - hz)  # min corner
    # px = +x, nx = -x, py, ny, pz, nz
    def q(v1, v2, v3, v4):
        faces.append(((v1, v2, v3, v4), col))
    q((x + hx, y - hy, z - hz), (x + hx, y + hy, z - hz),
      (x + hx, y + hy, z + hz), (x + hx, y - hy, z + hz))
    q((x - hx, y - hy, z + hz), (x - hx, y + hy, z + hz),
      (x - hx, y + hy, z - hz), (x - hx, y - hy, z - hz))
    q((x - hx, y + hy, z - hz), (x + hx, y + hy, z - hz),
      (x + hx, y + hy, z + hz), (x - hx, y + hy, z + hz))
    q((x - hx, y - hy, z + hz), (x + hx, y - hy, z + hz),
      (x + hx, y - hy, z - hz), (x - hx, y - hy, z - hz))
    q((x - hx, y - hy, z + hz), (x - hx, y + hy, z + hz),
      (x + hx, y + hy, z + hz), (x + hx, y - hy, z + hz))
    q((x + hx, y - hy, z - hz), (x + hx, y + hy, z - hz),
      (x - hx, y + hy, z - hz), (x - hx, y - hy, z - hz))
    return faces


def box(cx, cy, cz, sx, sy, sz, col):
    return box_face((cx, cy, cz), (sx, sy, sz), col)


def yaw_rotate(points, yaw, origin=(0, 0, 0)):
    """Rotate local points around the vertical axis through origin."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    ox, _, oz = origin
    out = []
    for (x, y, z) in points:
        dx, dz = x - ox, z - oz
        out.append((ox + dx * cy + dz * sy, y, oz - dx * sy + dz * cy))
    return out


def face_normal(vs):
    a = sub(vs[1], vs[0])
    b = sub(vs[2], vs[0])
    return norm(cross(a, b))


# ---------------------------------------------------------------- models
def soldier_model(accent, civilian=False, armed=False, hands_up=False, team=False):
    """Low-poly soldier. Faces reference LOCAL model coords (facing +Z).
    Returns list of (verts, color). Colors: uniform plate for team,
    threat reds for hostiles, civilian blue."""
    skin = (214, 176, 148)
    boot = (40, 42, 48)
    cloth = accent
    vest = shade(accent, 0.8)
    dark = shade(accent, 0.55)
    F = []
    # legs
    for side in (-1, 1):
        F += box(side * 0.12, 0.32, 0.0, 0.16, 0.30, 0.22, boot if side < 0 else shade(boot, 0.8))
    # pelvis + torso
    F += box(0, 0.52, 0.0, 0.42, 0.22, 0.28, dark)
    F += box(0, 0.80, 0.0, 0.40, 0.36, 0.30, cloth)
    F += box(0, 0.80, 0.06, 0.34, 0.26, 0.14, vest)  # chest armor
    # shoulders + arms
    for side in (-1, 1):
        F += box(side * 0.26, 0.92, 0.10, 0.14, 0.30, 0.16, vest)
        F += box(side * 0.26, 1.06, 0.18, 0.10, 0.16, 0.10, skin)
    # head + helmet
    F += box(0, 1.22, 0.0, 0.17, 0.20, 0.19, skin)
    F += box(0, 1.34, -0.03, 0.22, 0.12, 0.20, dark)
    F += box(0, 1.30, 0.06, 0.24, 0.05, 0.10, dark)
    if hands_up:
        for side in (-1, 1):
            F += box(side * 0.30, 1.22, -0.05, 0.10, 0.10, 0.30, skin)
    elif armed:
        # rifle: receiver + stock + barrel pointing +Z
        F += box(0, 1.02, 0.42, 0.08, 0.10, 0.30, (28, 30, 34))
        F += box(0, 1.04, 0.62, 0.07, 0.08, 0.30, (52, 56, 62))
        F += box(0, 1.00, 0.20, 0.09, 0.16, 0.16, (38, 40, 46))
    if team:
        F += box(-0.30, 1.12, 0.0, 0.04, 0.46, 0.04, (240, 210, 90))
    return F


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def room_model(w, d, h_room, wall_col, floor_col, door_x, door_w, roof=True):
    """Room as an open box with a doorway gap facing +Z at z=d."""
    F = []
    # floor
    F.append((( (0, 0, 0), (w, 0, 0), (w, 0, d), (0, 0, d) ), floor_col))
    # back wall (z=0), left (x=0), right (x=w)
    F.extend(box(w / 2, h_room / 2, 0.0, w, h_room, 0.01, wall_col))
    F.extend(box(0.0, h_room / 2, d / 2, 0.01, h_room, d, wall_col))
    F.extend(box(w, h_room / 2, d / 2, 0.01, h_room, d, wall_col))
    # front wall with doorway
    x0 = door_x - door_w / 2
    x1 = door_x + door_w / 2
    if x0 > 0:
        F += box(x0 / 2, h_room / 2, d, x0, h_room, 0.01, wall_col)
    if w - x1 > 0:
        F += box((x1 + w) / 2, h_room / 2, d, w - x1, h_room, 0.01, wall_col)
    F.extend(box(door_x, h_room - 0.03, d, door_w + 0.04, 0.06, 0.02, shade(wall_col, 1.2)))
    if roof:
        F.extend(box(w / 2, h_room, d / 2, w, 0.01, d, shade(wall_col, 0.55)))
    return F


def box_props(rects, h, col, py0):
    """Turn a list of (x, y, w, prop_h) 2D rects into 3D boxes.
    py0 is the depth origin: a rect at 2D y maps to z = py0 - y
    (the door is at z=0, the back wall at z=py0)."""
    F = []
    for (px, py, pw, ph) in rects:
        cx = px + pw / 2
        cz = py0 - py - ph / 2
        F.extend(box(cx, h / 2, cz, pw, h, ph, col))
    return F


# ---------------------------------------------------------------- rendering
def draw_scene(surf, cam, yaw, pitch, world_faces, f=560, near=0.05, light=(0.4, 0.8, 0.45)):
    w, h = surf.get_size()
    cam_planes = []
    for (verts, col) in world_faces:
        vp = [project(cam, yaw, pitch, v, w, h, f, near) for v in verts]
        if any(p is None for p in vp):
            continue
        depth = sum(p[2] for p in vp) / len(vp)
        n = face_normal(verts)
        lam = 0.5 + 0.5 * max(0.0, dot(n, norm(light)))
        cols = tuple(int(c * lam) for c in col)
        cam_planes.append((depth, [(p[0], p[1]) for p in vp], cols))
    cam_planes.sort(key=lambda t: -t[0])
    for _, pts, col in cam_planes:
        pygame.draw.polygon(surf, col, pts)
        pygame.draw.polygon(surf, shade(col, 1.35), pts, 1)


def draw_wire(surf, cam, yaw, pitch, pts, col, f=560):
    w, h = surf.get_size()
    pp = [project(cam, yaw, pitch, p, w, h, f) for p in pts]
    if any(p is None for p in pp):
        return
    pygame.draw.lines(surf, col, False, [(p[0], p[1]) for p in pp], 1)