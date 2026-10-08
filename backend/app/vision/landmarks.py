"""Internal, model-agnostic landmark representation.

Landmark indices follow the 33-point BlazePose topology, which is also what
MediaPipe Pose Landmarker emits. Other estimators (ViTPose+, RTMPose, ...) must
map their output onto this topology inside their own ``PoseEstimator`` adapter.

Coordinates stored in :class:`Pose` are *normalized image coordinates*
(x in [0,1] of frame width, y in [0,1] of frame height). They are NOT metric.
Because x and y are normalized by different pixel extents, any angle or
distance must be computed in aspect-corrected space; use :meth:`Pose.xy`.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np


class LM(IntEnum):
    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_PINKY = 17
    RIGHT_PINKY = 18
    LEFT_INDEX = 19
    RIGHT_INDEX = 20
    LEFT_THUMB = 21
    RIGHT_THUMB = 22
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_HEEL = 29
    RIGHT_HEEL = 30
    LEFT_FOOT_INDEX = 31
    RIGHT_FOOT_INDEX = 32


NUM_LANDMARKS = 33

# Skeleton connections used by the renderer (subset of BlazePose body graph).
SKELETON_EDGES: tuple[tuple[int, int], ...] = (
    (LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER),
    (LM.LEFT_SHOULDER, LM.LEFT_ELBOW), (LM.LEFT_ELBOW, LM.LEFT_WRIST),
    (LM.RIGHT_SHOULDER, LM.RIGHT_ELBOW), (LM.RIGHT_ELBOW, LM.RIGHT_WRIST),
    (LM.LEFT_SHOULDER, LM.LEFT_HIP), (LM.RIGHT_SHOULDER, LM.RIGHT_HIP),
    (LM.LEFT_HIP, LM.RIGHT_HIP),
    (LM.LEFT_HIP, LM.LEFT_KNEE), (LM.LEFT_KNEE, LM.LEFT_ANKLE),
    (LM.RIGHT_HIP, LM.RIGHT_KNEE), (LM.RIGHT_KNEE, LM.RIGHT_ANKLE),
    (LM.LEFT_ANKLE, LM.LEFT_HEEL), (LM.LEFT_HEEL, LM.LEFT_FOOT_INDEX),
    (LM.RIGHT_ANKLE, LM.RIGHT_HEEL), (LM.RIGHT_HEEL, LM.RIGHT_FOOT_INDEX),
    (LM.NOSE, LM.LEFT_SHOULDER), (LM.NOSE, LM.RIGHT_SHOULDER),
)


@dataclass
class Pose:
    """One detected person in one frame."""

    points: np.ndarray        # (33, 3) normalized x, y, relative depth z
    visibility: np.ndarray    # (33,) per-landmark visibility/confidence in [0,1]
    timestamp_ms: float
    aspect: float = 1.0       # frame width / frame height

    def __post_init__(self) -> None:
        self.points = np.asarray(self.points, dtype=np.float64).reshape(NUM_LANDMARKS, 3)
        self.visibility = np.asarray(self.visibility, dtype=np.float64).reshape(NUM_LANDMARKS)

    def xy(self, idx: int) -> np.ndarray:
        """Aspect-corrected 2D point: x scaled by aspect so that 1 unit == 1 frame height."""
        p = self.points[int(idx)]
        return np.array([p[0] * self.aspect, p[1]], dtype=np.float64)

    def vis(self, idx: int) -> float:
        return float(self.visibility[int(idx)])

    def min_vis(self, *idxs: int) -> float:
        return float(min(self.visibility[int(i)] for i in idxs))

    def has_nan(self) -> bool:
        return bool(np.isnan(self.points).any() or np.isnan(self.visibility).any())

    def copy_with(self, points: np.ndarray) -> "Pose":
        return Pose(points, self.visibility.copy(), self.timestamp_ms, self.aspect)
