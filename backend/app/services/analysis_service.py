"""Job orchestration for a local MVP.

Analyses run on a small in-process thread pool. This is deliberately NOT a
durable queue: jobs that are in flight when the server stops are marked failed
on the next start. Use a real queue (Celery/RQ/Arq + Redis) before deploying.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import settings
from ..exercises import build_config, create_analyzer
from ..exercises.config import ExerciseConfig
from ..models.schemas import AnalysisResult
from ..tracking.feedback import DISCLAIMER, summarize
from ..vision.pose_estimator import PoseEstimator
from ..vision.video_processor import VideoError, process_video
from .storage_service import JsonResultStore

log = logging.getLogger(__name__)
EstimatorFactory = Callable[[], PoseEstimator]


def _default_factory() -> PoseEstimator:
    from ..vision.mediapipe_estimator import MediaPipePoseEstimator
    return MediaPipePoseEstimator()


class AnalysisService:
    def __init__(self, store: JsonResultStore, estimator_factory: EstimatorFactory | None = None,
                 workers: int | None = None) -> None:
        self.store = store
        self.factory = estimator_factory or _default_factory
        self.pool = ThreadPoolExecutor(max_workers=workers or settings.worker_threads, thread_name_prefix="analysis")
        self._lock = threading.Lock()
        self._mark_interrupted()

    def _mark_interrupted(self) -> None:
        for aid in self.store.list_ids():
            try:
                r = self.store.load(aid)
            except Exception:
                continue
            if r and r.status in ("queued", "processing"):
                r.status, r.error = "failed", "Interrupted by a server restart (the local job runner is not durable)."
                self.store.save(r)

    def submit(self, analysis_id: str, exercise: str, upload: Path, filename: str, cfg: ExerciseConfig) -> AnalysisResult:
        result = AnalysisResult(id=analysis_id, status="queued", exercise=exercise,
                                created_at=datetime.now(timezone.utc).isoformat(),
                                config=cfg.model_dump(), disclaimer=DISCLAIMER,
                                video=None)
        self.store.save(result)
        self.pool.submit(self._run, analysis_id, exercise, upload, filename, cfg)
        return result

    def _update(self, analysis_id: str, **kw) -> None:
        with self._lock:
            r = self.store.load(analysis_id)
            if r:
                for k, v in kw.items():
                    setattr(r, k, v)
                self.store.save(r)

    def _run(self, analysis_id: str, exercise: str, upload: Path, filename: str, cfg: ExerciseConfig) -> None:
        self._update(analysis_id, status="processing", progress=0.01)
        last = [0.0]

        def progress(p: float) -> None:
            if p - last[0] >= 0.05:
                last[0] = p
                self._update(analysis_id, progress=round(p, 3))

        try:
            analyzer = create_analyzer(exercise, cfg)
            with self.factory() as est:
                out = process_video(upload, analyzer, est, filename=filename,
                                    output_path=self.store.video_path(analysis_id),
                                    on_progress=progress, stride=settings.frame_stride,
                                    inference_max_side=settings.inference_max_side,
                                    max_seconds=settings.max_video_seconds,
                                    bar_y=getattr(cfg, "bar_y", None))
            self._update(analysis_id, status="completed", progress=1.0, video=out.video, summary=out.summary,
                         reps=out.reps, series=out.series, tracking=out.tracking, performance=out.performance,
                         warnings=out.warnings, feedback_summary=summarize(out.reps), output_video=out.output)
        except VideoError as e:
            self._update(analysis_id, status="failed", error=str(e))
        except Exception as e:  # noqa: BLE001 - surface any failure to the client, log the trace
            log.exception("analysis %s failed", analysis_id)
            self._update(analysis_id, status="failed", error=f"Analysis failed: {type(e).__name__}: {e}")
        finally:
            self.store.delete_upload(upload)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
