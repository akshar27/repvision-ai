"""Short-clip setup check: camera-view guidance + suggested rest threshold."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..exercises import create_analyzer
from ..exercises.config import ExerciseConfig, build_config
from ..vision.landmarks import LM
from ..vision.mediapipe_estimator import MediaPipePoseEstimator
from ..vision.pose_estimator import PoseEstimator
from ..vision.video_processor import VideoError, iter_frames, probe_video

REQUIRED = {
    "squat": {"hips": [LM.LEFT_HIP, LM.RIGHT_HIP], "knees": [LM.LEFT_KNEE, LM.RIGHT_KNEE],
              "ankles": [LM.LEFT_ANKLE, LM.RIGHT_ANKLE]},
    "pushup": {"shoulders": [LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER], "elbows": [LM.LEFT_ELBOW, LM.RIGHT_ELBOW],
               "wrists": [LM.LEFT_WRIST, LM.RIGHT_WRIST], "hips": [LM.LEFT_HIP, LM.RIGHT_HIP],
               "ankles": [LM.LEFT_ANKLE, LM.RIGHT_ANKLE]},
    "pullup": {"shoulders": [LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER], "elbows": [LM.LEFT_ELBOW, LM.RIGHT_ELBOW],
               "wrists": [LM.LEFT_WRIST, LM.RIGHT_WRIST], "head": [LM.NOSE, LM.MOUTH_LEFT, LM.MOUTH_RIGHT]},
}
CLIP_SECONDS = 5.0


def run_calibration_check(path: Path, exercise: str, cfg: ExerciseConfig, estimator: PoseEstimator | None = None,
                          seconds: float = CLIP_SECONDS):
    info = probe_video(path)
    est = estimator or MediaPipePoseEstimator()
    analyzer = create_analyzer(exercise, cfg)
    vis: dict[str, list[float]] = {k: [] for k in REQUIRED[exercise]}
    out_of_frame: dict[str, int] = {k: 0 for k in REQUIRED[exercise]}
    signals: list[float] = []
    n = n_pose = 0
    try:
        for _i, t, frame in iter_frames(path, info.fps):
            if t > seconds * 1000:
                break
            n += 1
            pose = est.detect(frame, int(t))
            if pose is None:
                continue
            n_pose += 1
            for grp, idxs in REQUIRED[exercise].items():
                vis[grp].append(float(np.mean([pose.vis(i) for i in idxs])))
                if any(not (0.0 <= pose.points[i][0] <= 1.0 and 0.0 <= pose.points[i][1] <= 1.0) for i in idxs):
                    out_of_frame[grp] += 1
            f = analyzer.extract(pose)
            if f is not None:
                signals.append(f.signal)
    finally:
        if estimator is None:
            est.close()
    if n == 0:
        raise VideoError("No frames could be read for the setup check.")
    thr = cfg.min_visibility
    warnings, groups = [], {}
    if n_pose / n < 0.6:
        warnings.append("No person was detected in much of the clip. Make sure your full body is in view and well lit.")
    for grp, vals in vis.items():
        mean = float(np.mean(vals)) if vals else 0.0
        groups[grp] = round(mean, 3)
        if mean < thr:
            warnings.append(f"{grp.capitalize()} are often not visible (mean visibility {mean:.2f} < {thr:.2f}). "
                            "Adjust the camera so they stay in frame and unobstructed.")
        elif out_of_frame[grp] > 0.2 * max(1, n_pose):
            warnings.append(f"{grp.capitalize()} leave the frame in many frames – step back or zoom out.")
    suggestions: dict[str, float] = {}
    if len(signals) >= 10:
        top = float(np.percentile(signals, 85))
        if top < cfg.machine.rest_enter_deg + 3:
            cand = max(110.0, round(top - 8))
            try:
                build_config(exercise, cfg.preset, {"machine.rest_enter_deg": cand,
                                                    "machine.partial_min_deg": min(cfg.machine.partial_min_deg, cand - 5)})
                suggestions["machine.rest_enter_deg"] = cand
                if cfg.machine.partial_min_deg > cand - 5:
                    suggestions["machine.partial_min_deg"] = cand - 5
                warnings.append(f"The most extended position in this clip is ~{top:.0f}°, below the rest threshold "
                                f"({cfg.machine.rest_enter_deg:.0f}°). Reps may not be detected; consider the suggested override.")
            except Exception:
                pass
    elif n_pose >= 10:
        warnings.append("Required landmarks were valid in too few frames to estimate your extended position.")
    setup = {"frames_checked": n, "pose_coverage": round(n_pose / n, 3), "valid_frames": len(signals),
             "mean_visibility": groups, "extended_position_deg": round(float(np.percentile(signals, 85)), 1) if signals else None}
    return setup, warnings, suggestions
