import math

import numpy as np

from app.vision import geometry as g
from app.vision.landmarks import Pose
from app.vision.smoothing import LandmarkSmoother, ScalarSmoother, ema_alpha


def test_right_angle():
    assert math.isclose(g.angle_deg((1, 0), (0, 0), (0, 1)), 90.0, abs_tol=1e-9)


def test_elbow_angle_straight_and_folded():
    assert math.isclose(g.angle_deg((0, 0), (1, 0), (2, 0)), 180.0, abs_tol=1e-6)
    assert math.isclose(g.angle_deg((0, 0), (1, 0), (0, 0)), 0.0, abs_tol=1e-3)


def test_knee_angle_45():
    # hip above-left of knee, ankle straight below knee, 45 deg between them
    assert math.isclose(g.angle_deg((-1, -1), (0, 0), (0, 1)), 135.0, abs_tol=1e-6)


def test_degenerate_vectors_return_nan():
    assert math.isnan(g.angle_deg((0, 0), (0, 0), (1, 1)))
    assert math.isnan(g.angle_deg((1, 1), (1, 1), (1, 1)))
    assert math.isnan(g.angle_deg((float("nan"), 0), (0, 0), (1, 1)))


def test_collinear_numerical_safety():
    # float error could push cosine slightly beyond [-1, 1]
    assert 0.0 <= g.angle_deg((0.1, 0.1), (0.2, 0.2), (0.3, 0.3)) <= 180.0


def test_distance_and_normalized():
    assert g.distance((0, 0), (3, 4)) == 5.0
    assert g.normalized_distance((0, 0), (3, 4), 10) == 0.5
    assert math.isnan(g.normalized_distance((0, 0), (3, 4), 0))


def test_vertical_displacement_and_velocity():
    assert g.normalized_vertical_displacement(0.6, 0.4, 0.5) == 0.4 / 1.0 * 1.0 or True
    assert math.isclose(g.normalized_vertical_displacement(0.6, 0.4, 0.5), 0.4)
    assert math.isclose(g.velocity(10, 20, 500), 20.0)
    assert math.isnan(g.velocity(10, 20, 0))


def test_torso_inclination():
    assert math.isclose(g.torso_inclination_deg((0, -1), (0, 0)), 0.0, abs_tol=1e-9)
    assert math.isclose(g.torso_inclination_deg((1, -1), (0, 0)), 45.0, abs_tol=1e-9)


def test_line_deviation_sign():
    assert g.line_deviation((0.5, 0.1), (0, 0), (1, 0)) > 0      # below line (y down) = positive
    assert g.line_deviation((0.5, -0.1), (0, 0), (1, 0)) < 0
    assert math.isnan(g.line_deviation((0, 0), (0, 0), (0, 1)))   # vertical: ambiguous


def test_confident():
    assert g.confident([0.9, 0.8], 0.5)
    assert not g.confident([0.9, 0.2], 0.5)
    assert not g.confident([float("nan")], 0.5)


def test_pose_aspect_correction():
    pts = np.zeros((33, 3))
    pts[0] = (0.5, 0.5, 0)
    pts[1] = (0.5 + 0.1, 0.5, 0)
    p = Pose(pts, np.ones(33), 0, aspect=2.0)
    # a 0.1 horizontal step on a 2:1 frame is 0.2 frame-heights
    assert math.isclose(g.distance(p.xy(0), p.xy(1)), 0.2)


def test_ema_alpha_frame_rate_independent():
    a30 = 1 - (1 - ema_alpha(33.3, 100)) ** 1
    two = 1 - (1 - ema_alpha(16.65, 100)) ** 2
    assert math.isclose(a30, two, rel_tol=1e-6)
    assert ema_alpha(33, 0) == 1.0


def test_scalar_smoother_reduces_jitter_and_resets_on_gap():
    s = ScalarSmoother(tau_ms=100)
    rng = np.random.default_rng(0)
    raw = 100 + rng.normal(0, 5, 200)
    out = [s.update(i * 33.3, x) for i, x in enumerate(raw)]
    assert np.std(out[20:]) < np.std(raw[20:]) * 0.6
    assert s.update(1e6, 50.0) == 50.0          # after a long gap, no lag from stale state


def test_landmark_smoother_disabled_and_enabled():
    pts = np.zeros((33, 3))
    p0 = Pose(pts.copy(), np.ones(33), 0)
    p1 = Pose(pts + 1.0, np.ones(33), 33)
    sm = LandmarkSmoother(tau_ms=100)
    sm.update(p0)
    out = sm.update(p1)
    assert 0 < out.points[0, 0] < 1
    off = LandmarkSmoother(tau_ms=0)
    off.update(p0)
    assert off.update(p1).points[0, 0] == 1.0
