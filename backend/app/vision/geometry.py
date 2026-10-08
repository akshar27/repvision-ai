"""Numerically safe geometry helpers. All inputs are 2D points (aspect-corrected)."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

EPS = 1e-9


def _arr(p: Sequence[float]) -> np.ndarray:
    return np.asarray(p, dtype=np.float64)


def distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Euclidean distance."""
    return float(np.linalg.norm(_arr(a) - _arr(b)))


def angle_deg(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    """Interior angle at vertex ``b`` formed by a-b-c, in degrees [0, 180].

    Returns NaN when either arm has (near) zero length, instead of raising or
    returning a misleading 0/180.
    """
    ba = _arr(a) - _arr(b)
    bc = _arr(c) - _arr(b)
    na, nc = np.linalg.norm(ba), np.linalg.norm(bc)
    if na < EPS or nc < EPS or not np.isfinite(na) or not np.isfinite(nc):
        return float("nan")
    cos = float(np.dot(ba, bc) / (na * nc))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def normalized_distance(a: Sequence[float], b: Sequence[float], scale: float) -> float:
    """Distance divided by a body-relative scale (e.g. torso length); NaN if scale invalid."""
    if not np.isfinite(scale) or scale < EPS:
        return float("nan")
    return distance(a, b) / scale


def normalized_vertical_displacement(y_now: float, y_ref: float, scale: float) -> float:
    """Vertical displacement in body-scale units. Positive = downward in the image."""
    if not np.isfinite(scale) or scale < EPS:
        return float("nan")
    return (y_now - y_ref) / scale


def velocity(prev: float, curr: float, dt_ms: float) -> float:
    """Finite-difference rate of change per second."""
    if dt_ms <= 0 or not (np.isfinite(prev) and np.isfinite(curr)):
        return float("nan")
    return (curr - prev) / (dt_ms / 1000.0)


def relative_position(p: Sequence[float], origin: Sequence[float], scale: float) -> np.ndarray:
    """Position of ``p`` relative to ``origin`` in body-scale units."""
    if not np.isfinite(scale) or scale < EPS:
        return np.array([float("nan"), float("nan")])
    return (_arr(p) - _arr(origin)) / scale


def torso_inclination_deg(shoulder: Sequence[float], hip: Sequence[float]) -> float:
    """Angle between the hip->shoulder vector and the image vertical (0 = upright).

    This is a 2D projection; it underestimates true lean when the camera is not
    perpendicular to the sagittal plane.
    """
    v = _arr(shoulder) - _arr(hip)
    n = np.linalg.norm(v)
    if n < EPS:
        return float("nan")
    # image "up" is -y
    return math.degrees(math.acos(max(-1.0, min(1.0, float(-v[1] / n)))))


def line_deviation(point: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
    """Signed perpendicular offset of ``point`` from line a->b, divided by |ab|.

    Positive when the point lies *below* the line in the image (larger y),
    negative when above. NaN for a degenerate or near-vertical line (where
    "below" is ambiguous).
    """
    a, b, p = _arr(a), _arr(b), _arr(point)
    d = b - a
    length = np.linalg.norm(d)
    if length < EPS or abs(d[0]) < 0.2 * length:
        return float("nan")
    line_y = a[1] + (p[0] - a[0]) * d[1] / d[0]
    cross = abs(d[0] * (p[1] - a[1]) - d[1] * (p[0] - a[0])) / length
    return float(math.copysign(cross / length, p[1] - line_y))


def line_angle_from_horizontal_deg(a: Sequence[float], b: Sequence[float]) -> float:
    d = _arr(b) - _arr(a)
    if np.linalg.norm(d) < EPS:
        return float("nan")
    return math.degrees(math.atan2(abs(d[1]), abs(d[0])))


def weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    vals = np.asarray(values, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    ok = np.isfinite(vals) & np.isfinite(w) & (w > 0)
    if not ok.any():
        return float("nan")
    return float(np.sum(vals[ok] * w[ok]) / np.sum(w[ok]))


def confident(visibility: Sequence[float], threshold: float) -> bool:
    """True when every given visibility is a finite number >= threshold."""
    v = np.asarray(visibility, dtype=np.float64)
    return bool(v.size > 0 and np.isfinite(v).all() and (v >= threshold).all())
