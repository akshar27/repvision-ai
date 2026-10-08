from __future__ import annotations

import shutil
import subprocess
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_service, get_store
from app.main import app
from app.services.analysis_service import AnalysisService
from app.services.storage_service import JsonResultStore
from app.vision.pose_estimator import PoseEstimator
from tests.synth import FPS, lead_in, pullup_pose, pushup_pose, rep_profile, seq, squat_pose

W, H = 640, 360     # 16:9 to match the synthetic pose aspect


def squat_poses():
    return seq(squat_pose, lead_in(172) + rep_profile(172, 80, 1.0, 0.2, 1.0) * 3)


def pushup_poses():
    return seq(pushup_pose, lead_in(168) + rep_profile(168, 70, 0.8, 0.1, 0.8) * 2)


KINDS = {60: squat_poses, 140: pushup_poses}      # frame gray level -> pose sequence


class FakeEstimator(PoseEstimator):
    """Replays a synthetic skeleton sequence; the kind is encoded in the video's gray level."""
    name = "fake-synthetic"

    def __init__(self) -> None:
        self.i = 0
        self.poses = None

    def detect(self, frame_bgr, timestamp_ms):
        if self.poses is None:
            level = float(frame_bgr.mean())
            key = min(KINDS, key=lambda k: abs(k - level))
            self.poses = KINDS[key]()
        p = self.poses[self.i] if self.i < len(self.poses) else None
        self.i += 1
        return p


def make_video(path, gray: int, n_frames: int, w=W, h=H, fps=FPS):
    wr = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(n_frames):
        f = np.full((h, w, 3), gray, np.uint8)
        cv2.putText(f, str(i), (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        wr.write(f)
    wr.release()
    return path


@pytest.fixture()
def client(tmp_path):
    store = JsonResultStore(tmp_path / "data")
    service = AnalysisService(store, estimator_factory=FakeEstimator, workers=2)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as c:
        c.store = store
        yield c
    app.dependency_overrides.clear()
    service.shutdown()


def wait_done(client, analysis_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/results/{analysis_id}").json()
        if r["status"] in ("completed", "failed"):
            return r
        time.sleep(0.2)
    raise TimeoutError("analysis did not finish")
