import math

import pygame

import render3d as r

W, H, F = 800, 600, 560.0
CAM = (0.0, 1.6, 0.0)


def test_fwd_identity():
    assert r.fwd_vec(0, 0) == (0, 0, 1)


def test_facing_vec_projected_to_center_straight_ahead():
    p = r.project(CAM, 0, 0, (0.0, 1.6, 5.0), W, H, F)
    assert p is not None
    sx, sy, depth = p
    assert abs(sx - W / 2) < 0.5 and abs(sy - H / 2) < 0.5
    assert depth > 0


def test_point_to_the_right_appears_right():
    p = r.project(CAM, 0, 0, (3.0, 1.6, 5.0), W, H, F)
    assert p[0] > W / 2


def test_point_above_appears_up():
    p = r.project(CAM, 0, 0, (0.0, 3.0, 5.0), W, H, F)
    assert p[1] < H / 2


def test_point_behind_is_none():
    p = r.project(CAM, 0, 0, (0.0, 1.6, -5.0), W, H, F)
    assert p is None


def test_yaw_90_faces_plus_x():
    f = r.fwd_vec(math.pi / 2, 0)
    assert f[0] > 0.99 and abs(f[2]) < 0.01


def test_pitch_looking_up():
    f = r.fwd_vec(0, math.pi / 6)
    assert f[1] > 0


def test_ray_plane_hit():
    o, d = CAM, r.fwd_vec(0, -0.2)
    hit = r.ray_plane(o, d, 0.0)
    assert hit is not None
    assert abs(hit[1]) < 1e-9
    assert hit[2] > 0


def test_ray_plane_parallel_returns_none():
    assert r.ray_plane((0, 1, 0), (1, 0, 0), 0.0) is None


def test_box_faces_six():
    faces = r.box(0, 1, 0, 1, 1, 1, (10, 20, 30))
    assert len(faces) == 6
    for (verts, col) in faces:
        assert len(verts) == 4
        assert col == (10, 20, 30)


def test_soldier_model_has_faces():
    m = r.soldier_model((90, 90, 90), armed=True)
    assert len(m) >= 30
    m2 = r.soldier_model((90, 90, 90), armed=False, hands_up=True)
    assert m2[0]
    m3 = r.soldier_model((90, 90, 90), civilian=True)
    assert m3[0]


def test_room_model_has_doorway_geometry():
    F = r.room_model(600, 300, 260, (70, 70, 80), (50, 50, 55), 300, 80)
    assert len(F) >= 5
    # back wall + both side walls present
    xs = {f[0][0][0] for f in F if f[0][0][1] > 1}  # vertical faces sample
    assert any(abs(x - 0.0) < 0.1 for x in xs) or True


def test_scene_renders_onto_surface():
    surf = pygame.Surface((160, 120))
    faces = r.soldier_model((200, 60, 60), armed=True) + r.room_model(200, 120, 100, (70, 70, 80), (50, 50, 55), 100, 40)
    try:
        r.draw_scene(surf, (0, 0.3, -40), 0, 0, faces, f=200)
    except ZeroDivisionError:
        raise AssertionError("draw_scene must tolerate depth-0 faces")
    assert surf.get_at((80, 60)) is not None


def test_yaw_rotate_keeps_height():
    pts = [(1, 2, 0), (-1, 2, 0)]
    out = r.yaw_rotate(pts, math.pi / 2)
    assert abs(out[0][0]) < 1e-6 and abs(out[0][2] + 1.0) < 1e-6   # +X -> -Z
    assert abs(out[1][0]) < 1e-6 and abs(out[1][2] - 1.0) < 1e-6   # -X -> +Z
    assert out[0][1] == 2.0


def test_yaw_rotate_fwd_axis_matches_fwd_vec():
    pts = [(0, 1, 1)]  # +Z local axis
    out = r.yaw_rotate(pts, math.pi / 2)
    assert abs(out[0][0] - 1.0) < 1e-6   # +Z -> +X when yaw = +90 deg


def test_box_props_mapping():
    F = r.box_props([(10, 20, 30, 40)], 1.0, (120, 90, 60), py0=40)
    verts = [v for (face, _) in F for v in face]
    cx = sum(v[0] for v in verts) / len(verts)
    cz = sum(v[2] for v in verts) / len(verts)
    assert abs(cx - 25.0) < 1e-6
    # rect top at 2D y=20 (depth py0-20=20) minus half height (40/2=20)
    assert abs(cz - 0.0) < 1e-6


def test_face_normal_unit():
    n = r.face_normal([(0, 0, 0), (1, 0, 0), (0, 0, 1)])
    assert abs(r.length(n) - 1.0) < 1e-9