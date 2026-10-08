"""Deterministic synthetic landmark sequences.

These build kinematically consistent 2D skeletons from target joint angles so
the exercise logic can be unit-tested. They validate rule logic ONLY - they say
nothing about real-world pose-estimation accuracy.
"""
from __future__ import annotations

import math

import numpy as np

from app.vision.landmarks import LM, NUM_LANDMARKS, Pose

FPS = 30.0
ASPECT = 16 / 9


def _pose(coords: dict[int, tuple[float, float]], t_ms: float, vis: dict[int, float] | None = None,
          default_vis: float = 1.0, aspect: float = ASPECT) -> Pose:
    """coords are in aspect-corrected units (1 == frame height); converted to normalized."""
    pts = np.full((NUM_LANDMARKS, 3), 0.5)
    v = np.full(NUM_LANDMARKS, default_vis)
    for i, (x, y) in coords.items():
        pts[int(i)] = (x / aspect, y, 0.0)
    for i, val in (vis or {}).items():
        v[int(i)] = val
    return Pose(pts, v, t_ms, aspect)


def ease(n: int, a: float, b: float) -> list[float]:
    """n samples from a to b with cosine easing (inclusive end)."""
    return [a + (b - a) * (1 - math.cos(math.pi * i / max(n - 1, 1))) / 2 for i in range(n)]


def rep_profile(rest: float, bottom: float, down_s=1.2, hold_s=0.3, up_s=1.2, rest_s=0.8, fps=FPS) -> list[float]:
    d, h, u, r = (int(x * fps) for x in (down_s, hold_s, up_s, rest_s))
    return ease(d, rest, bottom) + [bottom] * h + ease(u, bottom, rest) + [rest] * r


def lead_in(angle: float, seconds=1.0, fps=FPS) -> list[float]:
    return [angle] * int(seconds * fps)


# ------------------------------------------------------------------ squat
def squat_pose(knee_deg: float, t_ms: float, lean_deg: float = 20.0, vis=None, aspect: float = ASPECT) -> Pose:
    shank, thigh, torso = 0.20, 0.22, 0.28
    ankle = np.array([0.5, 0.9])
    tilt = math.radians(10)
    knee = ankle + shank * np.array([math.sin(tilt), -math.cos(tilt)])
    d0 = (ankle - knee) / shank
    th = math.radians(knee_deg)
    # rotate d0 by th so the hip ends up above and behind the knee
    rot = np.array([[math.cos(th), math.sin(th)], [-math.sin(th), math.cos(th)]])
    hip = knee + thigh * (rot @ d0)
    if hip[0] > knee[0] + 1e-9:
        rot = rot.T
        hip = knee + thigh * (rot @ d0)
    psi = math.radians(lean_deg)
    sh = hip + torso * np.array([math.sin(psi), -math.cos(psi)])
    c: dict[int, tuple[float, float]] = {}
    for side, dx in (("LEFT", 0.0), ("RIGHT", 0.012)):
        c[LM[f"{side}_ANKLE"]] = (ankle[0] + dx, ankle[1])
        c[LM[f"{side}_HEEL"]] = (ankle[0] + dx - 0.02, ankle[1] + 0.02)
        c[LM[f"{side}_FOOT_INDEX"]] = (ankle[0] + dx + 0.06, ankle[1] + 0.02)
        c[LM[f"{side}_KNEE"]] = (knee[0] + dx, knee[1])
        c[LM[f"{side}_HIP"]] = (hip[0] + dx, hip[1])
        c[LM[f"{side}_SHOULDER"]] = (sh[0] + dx, sh[1])
        c[LM[f"{side}_ELBOW"]] = (sh[0] + dx + 0.05, sh[1] + 0.1)
        c[LM[f"{side}_WRIST"]] = (sh[0] + dx + 0.12, sh[1] + 0.1)
    c[LM.NOSE] = (sh[0] + 0.03, sh[1] - 0.08)
    return _pose(c, t_ms, vis, aspect=aspect)


# ------------------------------------------------------------------ push-up
def pushup_pose(elbow_deg: float, t_ms: float, sag: float = 0.0, vis=None, aspect: float = ASPECT) -> Pose:
    """Side view, facing right. ``sag`` = hip offset below shoulder-ankle line as fraction of line length."""
    U = F = 0.14
    L = 0.55
    ankle = np.array([0.2, 0.8])
    wrist = np.array([0.2 + 0.50, 0.8])
    th = math.radians(elbow_deg)
    d = math.sqrt(U * U + F * F - 2 * U * F * math.cos(th))
    lo, hi = 0.0, 0.7
    for _ in range(60):  # solve body pitch so shoulder-wrist distance == d
        a = (lo + hi) / 2
        s = ankle + L * np.array([math.cos(a), -math.sin(a)])
        if np.linalg.norm(s - wrist) > d:
            hi = a
        else:
            lo = a
    a = (lo + hi) / 2
    sh = ankle + L * np.array([math.cos(a), -math.sin(a)])
    # elbow: circle intersection, pick the lower (outward/back) solution
    v = wrist - sh
    dist = np.linalg.norm(v)
    aa = (U * U - F * F + dist * dist) / (2 * dist)
    hh = math.sqrt(max(U * U - aa * aa, 0))
    base = sh + aa * v / dist
    perp = np.array([-v[1], v[0]]) / dist
    cands = [base + hh * perp, base - hh * perp]
    elbow = max(cands, key=lambda p: p[1] - 0.5 * p[0])   # lower & further back
    line = (sh - ankle)
    hip = ankle + 0.62 * line + np.array([0.0, sag * L])
    c: dict[int, tuple[float, float]] = {}
    for side, dx in (("LEFT", 0.0), ("RIGHT", 0.01)):
        c[LM[f"{side}_ANKLE"]] = (ankle[0] + dx, ankle[1])
        c[LM[f"{side}_HIP"]] = (hip[0] + dx, hip[1])
        c[LM[f"{side}_SHOULDER"]] = (sh[0] + dx, sh[1])
        c[LM[f"{side}_ELBOW"]] = (elbow[0] + dx, elbow[1])
        c[LM[f"{side}_WRIST"]] = (wrist[0] + dx, wrist[1])
        c[LM[f"{side}_KNEE"]] = ((ankle[0] + hip[0]) / 2 + dx, (ankle[1] + hip[1]) / 2)
    c[LM.NOSE] = (sh[0] + 0.06, sh[1] - 0.03)
    return _pose(c, t_ms, vis, aspect=aspect)


# ------------------------------------------------------------------ pull-up
def pullup_pose(elbow_deg: float, t_ms: float, bar_y: float = 0.20, head_up: float = 0.12, vis=None,
                aspect: float = ASPECT) -> Pose:
    """Frontal view, hanging from a bar at ``bar_y``. ``head_up``: mouth height above shoulder line."""
    U = F = 0.14
    th = math.radians(elbow_deg)
    d = math.sqrt(U * U + F * F - 2 * U * F * math.cos(th))
    c: dict[int, tuple[float, float]] = {}
    cx = 0.5
    shoulder_y = bar_y + d
    for side, sgn in (("LEFT", -1), ("RIGHT", 1)):
        w = np.array([cx + sgn * 0.12, bar_y])
        s = np.array([cx + sgn * 0.08, shoulder_y])
        v = w - s
        dist = np.linalg.norm(v)
        a = (U * U - F * F + dist * dist) / (2 * dist)
        h = math.sqrt(max(U * U - a * a, 0))
        base = s + a * v / dist
        perp = np.array([-v[1], v[0]]) / dist
        e = max([base + h * perp, base - h * perp], key=lambda p: sgn * (p[0] - cx))   # elbow flares outward
        c[LM[f"{side}_WRIST"]] = (w[0], w[1])
        c[LM[f"{side}_ELBOW"]] = (e[0], e[1])
        c[LM[f"{side}_SHOULDER"]] = (s[0], s[1])
        c[LM[f"{side}_HIP"]] = (cx + sgn * 0.05, shoulder_y + 0.28)
    c[LM.NOSE] = (cx, shoulder_y - head_up - 0.025)
    c[LM.MOUTH_LEFT] = (cx - 0.02, shoulder_y - head_up)
    c[LM.MOUTH_RIGHT] = (cx + 0.02, shoulder_y - head_up)
    return _pose(c, t_ms, vis, aspect=aspect)


def feed(analyzer, poses: list[Pose | None], times: list[float] | None = None):
    """Feed a sequence; returns list of RepEvent (including those flushed at the end)."""
    reps = []
    last = 0.0
    for i, p in enumerate(poses):
        t = times[i] if times else i * 1000.0 / FPS
        r = analyzer.update(p, t)
        reps += r.new_reps
        last = t
    reps += analyzer.finish(last)
    return reps


def seq(fn, angles: list[float], t0: float = 0.0, **kw) -> list[Pose]:
    return [fn(a, t0 + i * 1000.0 / FPS, **kw) for i, a in enumerate(angles)]
