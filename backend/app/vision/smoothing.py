"""Time-aware exponential smoothing (frame-rate independent)."""
from __future__ import annotations

import math

import numpy as np

from .landmarks import Pose


def ema_alpha(dt_ms: float, tau_ms: float) -> float:
    """Smoothing factor for a first-order low-pass with time constant ``tau_ms``."""
    if tau_ms <= 0 or dt_ms <= 0:
        return 1.0
    return 1.0 - math.exp(-dt_ms / tau_ms)


class ScalarSmoother:
    def __init__(self, tau_ms: float = 60.0, reset_gap_ms: float = 500.0) -> None:
        self.tau_ms, self.reset_gap_ms = tau_ms, reset_gap_ms
        self.value: float | None = None
        self._t: float | None = None

    def reset(self) -> None:
        self.value, self._t = None, None

    def update(self, t_ms: float, x: float) -> float:
        if not np.isfinite(x):
            return float("nan") if self.value is None else self.value
        if self.value is None or self._t is None or t_ms - self._t > self.reset_gap_ms or t_ms < self._t:
            self.value = float(x)
        else:
            a = ema_alpha(t_ms - self._t, self.tau_ms)
            self.value += a * (float(x) - self.value)
        self._t = t_ms
        return self.value


class LandmarkSmoother:
    """EMA over landmark coordinates. tau_ms=0 disables smoothing."""

    def __init__(self, tau_ms: float = 60.0, reset_gap_ms: float = 500.0) -> None:
        self.tau_ms, self.reset_gap_ms = tau_ms, reset_gap_ms
        self._pts: np.ndarray | None = None
        self._t: float | None = None

    def reset(self) -> None:
        self._pts, self._t = None, None

    def update(self, pose: Pose) -> Pose:
        t = pose.timestamp_ms
        if (self._pts is None or self._t is None or t < self._t
                or t - self._t > self.reset_gap_ms or self.tau_ms <= 0):
            self._pts = pose.points.copy()
        else:
            a = ema_alpha(t - self._t, self.tau_ms)
            self._pts = self._pts + a * (pose.points - self._pts)
        self._t = t
        return pose.copy_with(self._pts.copy())
