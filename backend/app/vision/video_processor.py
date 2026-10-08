"""Decode -> pose -> analyze -> annotate -> encode. Exercise logic stays model-agnostic."""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

from ..exercises.base import ExerciseAnalyzer
from ..models.schemas import (OutputVideo, PerformanceInfo, RepEvent, RepSummary, SeriesPoint,
                              TrackingStats, VideoInfo, num)
from ..rendering.overlay import Annotator
from .pose_estimator import PoseEstimator

log = logging.getLogger(__name__)
MAX_SERIES_POINTS = 1500


class VideoError(ValueError):
    """Unreadable / unsupported / too-long video. Message is safe to show the user."""


def hardware_description() -> str:
    desc = f"{platform.system()} {platform.machine()}, {os.cpu_count()} logical CPUs"
    if platform.system() == "Darwin":
        try:
            brand = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                   timeout=2).stdout.strip()
            if brand:
                desc = f"{brand} ({desc})"
        except Exception:  # pragma: no cover
            pass
    return desc


def probe_video(path: Path, filename: str | None = None) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise VideoError("Could not open the video. The file may be corrupt or use a codec this "
                             "OpenCV build cannot decode (try re-encoding to H.264 MP4).")
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise VideoError("The video contains no decodable frames.")
        h, w = frame.shape[:2]          # post-rotation size
        if not np.isfinite(fps) or fps < 1 or fps > 240:
            fps = 30.0
        if n <= 0:
            n = 0
        return VideoInfo(filename=filename, width=w, height=h, fps=round(fps, 3),
                         duration_s=round(n / fps, 3) if n else 0.0, frame_count=n)
    finally:
        cap.release()


def iter_frames(path: Path, fps_hint: float) -> Iterator[tuple[int, float, np.ndarray]]:
    """Yield (index, timestamp_ms, BGR frame). Always releases the capture."""
    cap = cv2.VideoCapture(str(path))
    try:
        idx, last_t = 0, -1.0
        while True:
            if not cap.grab():
                break
            t = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
            if t <= last_t or (idx > 0 and t <= 0):          # missing / non-monotonic container timestamps
                t = idx * 1000.0 / fps_hint
                if t <= last_t:
                    t = last_t + 1.0
            ok, frame = cap.retrieve()
            if not ok or frame is None:
                idx += 1                                       # dropped/invalid frame: skip but keep timing
                continue
            last_t = t
            yield idx, t, frame
            idx += 1
    finally:
        cap.release()


class _FfmpegWriter:
    def __init__(self, path: Path, w: int, h: int, fps: float) -> None:
        self.path = path
        self.log = open(path.with_suffix(".ffmpeg.log"), "wb")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
               "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self.log)
        self.codec = "h264 (libx264, ffmpeg)"

    def write(self, frame: np.ndarray) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self) -> bool:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self.proc.wait()
        self.log.close()
        ok = rc == 0 and self.path.exists() and self.path.stat().st_size > 0
        if ok:
            self.path.with_suffix(".ffmpeg.log").unlink(missing_ok=True)
        return ok


class _CvWriter:
    def __init__(self, path: Path, w: int, h: int, fps: float) -> None:
        self.path = path
        self.writer, self.codec, self.browser_ok = None, None, False
        for fourcc, browser in (("avc1", True), ("mp4v", False)):
            wr = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), fps, (w, h))
            if wr.isOpened():
                self.writer, self.codec, self.browser_ok = wr, fourcc, browser
                break
        if self.writer is None:
            raise VideoError("No usable video encoder found. Install ffmpeg (brew install ffmpeg / apt install ffmpeg).")

    def write(self, frame: np.ndarray) -> None:
        self.writer.write(frame)

    def close(self) -> bool:
        self.writer.release()
        return self.path.exists() and self.path.stat().st_size > 0


def _open_writer(path: Path, w: int, h: int, fps: float):
    if shutil.which("ffmpeg"):
        try:
            return _FfmpegWriter(path, w, h, fps), True, None
        except Exception as e:  # pragma: no cover
            log.warning("ffmpeg writer failed to start: %s", e)
    cvw = _CvWriter(path, w, h, fps)
    warn = None if cvw.browser_ok else (
        "ffmpeg was not found, so the annotated video was encoded as MPEG-4 Part 2 (mp4v), which most browsers "
        "cannot play inline. Install ffmpeg (macOS: `brew install ffmpeg`, Linux: `apt install ffmpeg`) for H.264 output.")
    return cvw, cvw.browser_ok, warn


@dataclass
class ProcessedVideo:
    video: VideoInfo
    reps: list[RepEvent]
    summary: RepSummary
    series: list[SeriesPoint]
    tracking: TrackingStats
    performance: PerformanceInfo
    output: OutputVideo
    warnings: list[str] = field(default_factory=list)


def process_video(path: Path, analyzer: ExerciseAnalyzer, estimator: PoseEstimator, *, filename: str | None = None,
                  output_path: Path | None = None, on_progress: Callable[[float], None] | None = None,
                  stride: int = 1, inference_max_side: int = 640, max_seconds: float | None = None,
                  output_max_side: int = 1280, bar_y: float | None = None) -> ProcessedVideo:
    info = probe_video(path, filename)
    if max_seconds and info.duration_s > max_seconds:
        raise VideoError(f"Video is {info.duration_s:.0f}s long; the limit is {max_seconds:.0f}s.")
    started = time.perf_counter()
    stride = max(1, stride)
    annot = Annotator(analyzer.name, bar_y)
    writer, browser_ok, out_warn = None, False, None
    wrote = False
    warnings: list[str] = []
    series: list[SeriesPoint] = []
    n_proc = n_pose = n_valid = 0
    last_t = 0.0
    last_res = None
    out_size: tuple[int, int] | None = None

    try:
        for idx, t_ms, frame in iter_frames(path, info.fps):
            h, w = frame.shape[:2]
            if writer is None and output_path is not None:
                k = min(1.0, output_max_side / max(w, h))
                out_size = (int(w * k) // 2 * 2, int(h * k) // 2 * 2)
                writer, browser_ok, out_warn = _open_writer(output_path, out_size[0], out_size[1], info.fps)
            run_pose = (idx % stride == 0) or last_res is None
            if run_pose:
                small = frame
                m = max(w, h)
                if m > inference_max_side:
                    k = inference_max_side / m
                    small = cv2.resize(frame, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
                pose = estimator.detect(small, int(t_ms))
                if pose is not None:
                    pose.timestamp_ms = t_ms
                    pose.aspect = w / h
                res = analyzer.update(pose, t_ms)
                last_res = res
                n_proc += 1
                n_pose += pose is not None
                n_valid += res.status == "ok"
                for rep in res.new_reps:
                    annot.on_rep(rep, t_ms)
                series.append(SeriesPoint(t=round(t_ms, 1), signal=num(res.signal, 1),
                                          angles={k2: num(v, 1) for k2, v in res.angles.items()},
                                          phase=res.phase, valid=res.status == "ok"))
            last_t = t_ms
            if writer is not None:
                vis = frame.copy() if out_size == (w, h) else cv2.resize(frame, out_size, interpolation=cv2.INTER_AREA)
                vis = annot.draw(vis, last_res, analyzer.counter.summary, t_ms)
                writer.write(vis)
            if on_progress and info.frame_count and idx % 15 == 0:
                on_progress(min(0.99, idx / info.frame_count))
    finally:
        if writer is not None:
            wrote = writer.close()
            if not wrote:
                browser_ok = False
                out_warn = "The annotated video could not be written (encoder failed)."
    if n_proc == 0:
        raise VideoError("The video contained no decodable frames.")
    analyzer.finish(last_t)

    elapsed = time.perf_counter() - started
    reps = list(analyzer.counter.reps)
    if len(series) > MAX_SERIES_POINTS:
        step = int(np.ceil(len(series) / MAX_SERIES_POINTS))
        series = series[::step]
    if n_pose / n_proc < 0.5:
        warnings.append("A person was detected in fewer than half of the frames. Check that the whole body is in "
                        "view, well lit, and not too far from the camera.")
    elif n_valid / n_proc < 0.6:
        warnings.append("Required body landmarks were reliably visible in fewer than 60% of frames for this "
                        "exercise; repetition results may be incomplete. See the camera guidance in the README.")
    if out_warn:
        warnings.append(out_warn)
    output = OutputVideo(available=wrote, codec=getattr(writer, "codec", None),
                         browser_compatible=bool(wrote and browser_ok), warning=out_warn)
    return ProcessedVideo(
        video=info, reps=reps, summary=analyzer.counter.summary, series=series,
        tracking=TrackingStats(frames_processed=n_proc, frames_with_pose=n_pose, frames_valid=n_valid,
                               pose_coverage=round(n_pose / n_proc, 4), valid_coverage=round(n_valid / n_proc, 4)),
        performance=PerformanceInfo(processing_seconds=round(elapsed, 2), processing_fps=round(n_proc / elapsed, 2),
                                    pose_model=estimator.name, inference_max_side=inference_max_side,
                                    hardware=hardware_description()),
        output=output, warnings=warnings)
