"""Pose-estimator interface. Exercise logic only ever sees :class:`Pose`."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .landmarks import Pose


class PoseEstimator(ABC):
    """Adapter contract for any 2D pose model (MediaPipe, ViTPose+, RTMPose, ...).

    Implementations must emit the 33-point BlazePose topology (see ``LM``) with
    normalized image coordinates, or map their own topology onto it.
    """

    name: str = "abstract"

    @abstractmethod
    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> Pose | None:
        """Return the primary person's pose, or None if nobody was detected.

        ``timestamp_ms`` must be non-decreasing across calls for a given session.
        """

    def close(self) -> None:  # pragma: no cover - trivial
        """Release model resources."""

    def __enter__(self) -> "PoseEstimator":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
