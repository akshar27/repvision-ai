"""MediaPipe Pose Landmarker (Tasks API) adapter."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..config import settings
from .landmarks import NUM_LANDMARKS, Pose
from .pose_estimator import PoseEstimator

MODEL_URLS = {
    "lite": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "full": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    "heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}


class ModelNotFoundError(RuntimeError):
    pass


def model_path(variant: str) -> Path:
    return settings.assets_dir / f"pose_landmarker_{variant}.task"


class MediaPipePoseEstimator(PoseEstimator):
    """One instance == one tracking session (VIDEO running mode keeps temporal state).

    Create a new instance per video/webcam session; the underlying model file is
    memory-mapped by MediaPipe, so construction is cheap relative to inference.
    """

    name = "mediapipe-pose-landmarker"

    def __init__(self, variant: str | None = None, min_detection: float = 0.5,
                 min_presence: float = 0.5, min_tracking: float = 0.5) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        variant = variant or settings.pose_model
        path = model_path(variant)
        if not path.exists():
            raise ModelNotFoundError(
                f"Pose model not found at {path}. Run `python scripts/download_models.py {variant}` "
                f"(or download {MODEL_URLS.get(variant, '<url>')} into backend/assets/)."
            )
        self._mp = mp
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=min_detection,
            min_pose_presence_confidence=min_presence,
            min_tracking_confidence=min_tracking,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int) -> Pose | None:
        h, w = frame_bgr.shape[:2]
        ts = max(int(timestamp_ms), self._last_ts + 1)  # MediaPipe requires strictly increasing
        self._last_ts = ts
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect_for_video(image, ts)
        if not result.pose_landmarks:
            return None
        lms = result.pose_landmarks[0]
        if len(lms) != NUM_LANDMARKS:
            return None
        pts = np.array([[l.x, l.y, l.z] for l in lms], dtype=np.float64)
        vis = np.array([l.visibility if l.visibility is not None else 0.0 for l in lms], dtype=np.float64)
        return Pose(pts, vis, float(timestamp_ms), aspect=w / h)

    def close(self) -> None:
        if getattr(self, "_landmarker", None) is not None:
            self._landmarker.close()
            self._landmarker = None
