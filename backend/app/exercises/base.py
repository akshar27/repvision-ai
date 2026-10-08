"""Exercise analyzer base class.

Pipeline per frame:  Pose -> smoothing -> exercise feature extraction (validated)
-> repetition state machine -> per-cycle evaluation -> RepEvent.
Subclasses implement only ``extract`` (features) and ``evaluate`` (rep rules).
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from ..models.schemas import FeedbackItem, RepEvent, num
from ..tracking import feedback as fb
from ..tracking.rep_counter import RepCounter
from ..tracking.state_machine import Cycle, Phase, RepStateMachine
from ..vision.landmarks import Pose
from ..vision.smoothing import LandmarkSmoother
from .config import BaseExerciseConfig


@dataclass
class Features:
    """Validated per-frame measurements for one exercise."""
    signal: float                         # primary joint angle driving the state machine
    confidence: float                     # min landmark visibility among landmarks used
    angles: dict[str, float]              # named angles for charts/overlay
    aux: dict[str, float] = field(default_factory=dict)
    draw_angles: list[tuple[int, int, int, float]] = field(default_factory=list)  # (a, vertex, c, value)
    joints: list[int] = field(default_factory=list)


@dataclass
class FrameRec:
    t: float
    valid: bool
    signal: float
    confidence: float
    aux: dict[str, float]


@dataclass
class FrameResult:
    t_ms: float
    status: str                           # ok | no_pose | low_confidence
    phase: str
    signal: float
    angles: dict[str, float]
    confidence: float
    new_reps: list[RepEvent]
    pose: Pose | None
    messages: list[str]
    draw_angles: list[tuple[int, int, int, float]]
    joints: list[int]


@dataclass
class Evaluation:
    classification: str                   # full | partial | uncertain
    feedback: list[FeedbackItem]
    criteria: dict[str, bool | str | None]
    measurements: dict[str, float | None]
    rom: dict[str, float | None]
    margins: list[float]                  # normalized distances to decision boundaries, for confidence


class ExerciseAnalyzer(ABC):
    name = "abstract"
    phase_names = {Phase.REST: "REST", Phase.FLEXING: "FLEXING", Phase.PEAK: "PEAK", Phase.EXTENDING: "EXTENDING"}

    def __init__(self, cfg: BaseExerciseConfig) -> None:
        self.cfg = cfg
        self.machine = RepStateMachine(cfg.machine)
        self.counter = RepCounter()
        self.smoother = LandmarkSmoother(cfg.smoothing_tau_ms)
        self._frames: list[FrameRec] = []
        self._prev: tuple[float, float] | None = None   # (t, signal) last accepted
        self._rejects = 0

    # ------------------------------------------------------------ subclass API
    @abstractmethod
    def extract(self, pose: Pose) -> Features | None:
        """Return validated features or None when landmarks/posture are unusable."""

    @abstractmethod
    def evaluate(self, cyc: Cycle, frames: list[FrameRec]) -> Evaluation:
        """Apply exercise-specific rules to one completed movement cycle."""

    # ---------------------------------------------------------------- session
    def reset(self) -> None:
        self.machine.reset()
        self.counter.reset()
        self.smoother.reset()
        self._frames.clear()
        self._prev, self._rejects = None, 0

    @property
    def phase_name(self) -> str:
        return self.phase_names[self.machine.phase]

    # ----------------------------------------------------------------- update
    def update(self, pose: Pose | None, t_ms: float) -> FrameResult:
        smoothed: Pose | None = None
        feats: Features | None = None
        status = "no_pose"
        if pose is not None and not pose.has_nan():
            smoothed = self.smoother.update(pose)
            feats = self.extract(smoothed)
            status = "ok" if feats is not None else "low_confidence"
        elif pose is None:
            self.smoother.reset()

        if feats is not None and not self._plausible(t_ms, feats.signal):
            feats, status = None, "low_confidence"

        sig = feats.signal if feats else float("nan")
        self._frames.append(FrameRec(t_ms, feats is not None, sig, feats.confidence if feats else 0.0,
                                     dict(feats.aux) if feats else {}))
        cycles = self.machine.update(t_ms, sig if feats else None)
        new_reps = [self._finalize(c) for c in cycles]
        self._trim(t_ms)

        msgs: list[str] = []
        if status == "no_pose":
            msgs.append("No person detected")
        elif status == "low_confidence":
            msgs.append("Body not clearly visible – check camera position")
        return FrameResult(t_ms, status, self.phase_name, sig, dict(feats.angles) if feats else {},
                           feats.confidence if feats else 0.0, new_reps, smoothed,
                           msgs, list(feats.draw_angles) if feats else [], list(feats.joints) if feats else [])

    def finish(self, t_ms: float) -> list[RepEvent]:
        reps = [self._finalize(c) for c in self.machine.flush(t_ms)]
        return reps

    # ---------------------------------------------------------------- internals
    def _plausible(self, t: float, s: float) -> bool:
        """Reject single-frame landmark flips (physically impossible joint speed)."""
        if not math.isfinite(s):
            return False
        if self._prev is not None and t > self._prev[0]:
            dps = abs(s - self._prev[1]) / ((t - self._prev[0]) / 1000.0)
            if dps > self.cfg.max_signal_speed_dps and self._rejects < 5:
                self._rejects += 1
                return False
        self._prev, self._rejects = (t, s), 0
        return True

    def _trim(self, t: float) -> None:
        keep_from = t - 4000.0
        if self.machine.cycle is not None:
            keep_from = min(keep_from, self.machine.cycle.start_ms - 200.0)
        if self._frames and self._frames[0].t < keep_from:
            i = 0
            while i < len(self._frames) and self._frames[i].t < keep_from:
                i += 1
            del self._frames[:i]

    def _finalize(self, cyc: Cycle) -> RepEvent:
        frames = [f for f in self._frames if cyc.start_ms <= f.t <= cyc.end_ms]
        valid = [f for f in frames if f.valid]
        coverage = len(valid) / len(frames) if frames else 0.0
        mean_conf = float(np.mean([f.confidence for f in valid])) if valid else 0.0
        meas_conf = mean_conf * coverage

        if cyc.abandoned or cyc.gaps > 0 or coverage < self.cfg.min_rep_coverage:
            ev = self._uncertain("TRACKING_GAP" if (cyc.abandoned or cyc.gaps > 0) else "LOW_VISIBILITY", cyc, valid)
        elif cyc.truncated:
            ev = self._uncertain("VIDEO_ENDED", cyc, valid)
        elif not cyc.started_from_rest and not cyc.ever_armed and cyc.lead_ms < self.cfg.machine.start_lead_ms:
            ev = self._uncertain("INVALID_START", cyc, valid)
        else:
            ev = self.evaluate(cyc, frames)

        ev.measurements.update({"start_angle": num(cyc.start_signal, 1), "min_angle": num(cyc.min_signal, 1),
                                "end_angle": num(cyc.end_signal, 1), "coverage": num(coverage)})
        ev.rom.setdefault("angle_rom_deg", num(cyc.start_signal - cyc.min_signal, 1))
        margin = min(ev.margins) if ev.margins else 0.0
        cls_conf = meas_conf * (0.5 + 0.5 * max(0.0, min(1.0, margin)))
        if ev.classification == "uncertain":
            cls_conf = min(cls_conf, 0.4)
        rep = RepEvent(
            index=len(self.counter.reps) + 1, start_ms=round(cyc.start_ms, 1), end_ms=round(cyc.end_ms, 1),
            duration_ms=round(cyc.end_ms - cyc.start_ms, 1), classification=ev.classification,  # type: ignore[arg-type]
            measurements=ev.measurements, rom=ev.rom, criteria=ev.criteria, feedback=ev.feedback,
            measurement_confidence=round(meas_conf, 3), classification_confidence=round(cls_conf, 3))
        self.counter.add(rep)
        return rep

    def _uncertain(self, code: str, cyc: Cycle, valid: list[FrameRec]) -> Evaluation:
        return Evaluation("uncertain", [fb.make(code)], {"validated": False}, {}, {}, [0.0])


def seg(pose: Pose, a: int, b: int) -> float:
    return float(np.linalg.norm(pose.xy(a) - pose.xy(b)))


def clip01(x: float) -> float:
    return max(0.0, min(1.0, x))
