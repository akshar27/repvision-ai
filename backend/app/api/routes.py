from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from ..config import settings
from ..exercises import EXERCISES, CalibrationInput, build_config, config_from_calibration
from ..exercises.config import PRESETS, CalibrationError
from ..services.analysis_service import AnalysisService
from ..services.calibration_service import run_calibration_check
from ..services.storage_service import InvalidId, JsonResultStore, UploadTooLarge, new_id, validate_id
from ..tracking.feedback import DISCLAIMER
from ..vision.video_processor import VideoError, probe_video
from .dependencies import get_service, get_store

router = APIRouter(prefix="/api")

EXERCISE_INFO = {
    "squat": {"label": "Squat", "phases": ["STANDING", "DESCENDING", "BOTTOM", "ASCENDING"],
              "camera": "Film from the side or ~45°, whole body in frame (head to feet), camera at hip height, 2–3 m away."},
    "pushup": {"label": "Push-up", "phases": ["TOP", "DESCENDING", "BOTTOM", "ASCENDING"],
               "camera": "Film from the side at floor/hip height with head-to-feet visible."},
    "pullup": {"label": "Pull-up", "phases": ["DEAD_HANG", "ASCENDING", "TOP", "DESCENDING"],
               "camera": "Film from the front or slightly off-axis, level camera, arms and head visible. "
                         "Mark the bar height to enable top-clearance checks."},
}


def http_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _parse_calibration(exercise: str, preset: str | None, raw: str | None):
    cal = None
    if raw:
        try:
            cal = CalibrationInput.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            raise http_error(422, "invalid_calibration", f"Calibration JSON is invalid: {e}") from e
    try:
        return config_from_calibration(exercise, cal, preset)
    except CalibrationError as e:
        raise http_error(422, "invalid_calibration", str(e)) from e


def _check_exercise(exercise: str) -> None:
    if exercise not in EXERCISES:
        raise http_error(422, "invalid_exercise", f"Unknown exercise '{exercise}'. Choose from {list(EXERCISES)}.")


def _check_preset(preset: str | None) -> None:
    if preset is not None and preset not in PRESETS:
        raise http_error(422, "invalid_sensitivity", f"Unknown sensitivity '{preset}'. Choose from {list(PRESETS)}.")


@router.get("/health")
def health():
    import shutil as sh
    model = settings.assets_dir / f"pose_landmarker_{settings.pose_model}.task"
    return {"status": "ok", "pose_model": settings.pose_model, "pose_model_present": model.exists(),
            "ffmpeg": bool(sh.which("ffmpeg"))}


@router.get("/exercises")
def exercises():
    out = []
    for name in EXERCISES:
        presets = {p: build_config(name, p).model_dump() for p in PRESETS}
        out.append({"id": name, **EXERCISE_INFO[name], "default_config": presets["standard"], "presets": presets})
    return {"exercises": out, "sensitivity_presets": list(PRESETS), "disclaimer": DISCLAIMER}


@router.post("/analyze", status_code=202)
async def analyze(exercise: str = Form(...), video: UploadFile = File(...),
                  sensitivity: str | None = Form(None), calibration: str | None = Form(None),
                  service: AnalysisService = Depends(get_service), store: JsonResultStore = Depends(get_store)):
    _check_exercise(exercise)
    _check_preset(sensitivity)
    cfg = _parse_calibration(exercise, sensitivity, calibration)
    ext = Path(video.filename or "").suffix.lower()
    if ext not in settings.extension_set:
        raise http_error(415, "unsupported_media", f"Unsupported file type '{ext or 'none'}'. "
                         f"Allowed: {sorted(settings.extension_set)}.")
    if video.content_type and not (video.content_type.startswith("video/") or video.content_type == "application/octet-stream"):
        raise http_error(415, "unsupported_media", f"Content type '{video.content_type}' is not a video.")
    analysis_id = new_id()
    try:
        path = await store.save_upload(analysis_id, video, ext, settings.max_upload_mb * 1024 * 1024)
    except UploadTooLarge as e:
        raise http_error(413, "file_too_large", str(e)) from e
    except ValueError as e:
        raise http_error(422, "empty_file", str(e)) from e
    try:
        info = probe_video(path, video.filename)
        if info.duration_s > settings.max_video_seconds:
            raise VideoError(f"Video is {info.duration_s:.0f}s long; the limit is {settings.max_video_seconds}s.")
    except VideoError as e:
        store.delete_upload(path)
        raise http_error(422, "unreadable_video", str(e)) from e
    result = service.submit(analysis_id, exercise, path, Path(video.filename or "video").name, cfg)
    return {"analysis_id": result.id, "status": result.status, "exercise": exercise,
            "result_url": f"/api/results/{result.id}", "video_url": f"/api/videos/{result.id}"}


@router.get("/results/{analysis_id}")
def results(analysis_id: str, store: JsonResultStore = Depends(get_store)):
    try:
        validate_id(analysis_id)
    except InvalidId as e:
        raise http_error(400, "invalid_id", str(e)) from e
    r = store.load(analysis_id)
    if r is None:
        raise http_error(404, "not_found", "No analysis with that id.")
    return r


@router.get("/videos/{analysis_id}")
def videos(analysis_id: str, download: bool = False, store: JsonResultStore = Depends(get_store)):
    try:
        validate_id(analysis_id)
    except InvalidId as e:
        raise http_error(400, "invalid_id", str(e)) from e
    p = store.video_path(analysis_id)
    if not p.exists():
        raise http_error(404, "not_found", "Annotated video not available (analysis unknown, unfinished or failed).")
    return FileResponse(p, media_type="video/mp4",
                        filename=f"repvision-{analysis_id[:8]}.mp4" if download else None,
                        content_disposition_type="attachment" if download else "inline")


@router.post("/calibrate")
async def calibrate(exercise: str = Form(...), sensitivity: str | None = Form(None),
                    calibration: str | None = Form(None), video: UploadFile | None = File(None),
                    store: JsonResultStore = Depends(get_store)):
    """Validate a calibration, return the effective config, and (optionally) check camera setup on a short clip."""
    _check_exercise(exercise)
    _check_preset(sensitivity)
    cfg = _parse_calibration(exercise, sensitivity, calibration)
    setup, warnings, suggestions = None, [], {}
    if exercise == "pullup" and getattr(cfg, "bar_y", None) is None:
        warnings.append("No bar height set: pull-up top clearance will be reported as 'unverified' and reps "
                        "will be labelled 'uncertain' unless you relax 'require_bar_for_full'.")
    if video is not None and video.filename:
        ext = Path(video.filename).suffix.lower()
        if ext not in settings.extension_set:
            raise http_error(415, "unsupported_media", f"Unsupported file type '{ext}'.")
        cid = new_id()
        try:
            path = await store.save_upload(cid, video, ext, settings.max_upload_mb * 1024 * 1024)
        except UploadTooLarge as e:
            raise http_error(413, "file_too_large", str(e)) from e
        except ValueError as e:
            raise http_error(422, "empty_file", str(e)) from e
        try:
            setup, w2, suggestions = run_calibration_check(path, exercise, cfg)
            warnings += w2
        except VideoError as e:
            raise http_error(422, "unreadable_video", str(e)) from e
        finally:
            store.delete_upload(path)
    return {"exercise": exercise, "config": cfg.model_dump(), "warnings": warnings, "setup_check": setup,
            "suggested_overrides": suggestions, "camera_guidance": EXERCISE_INFO[exercise]["camera"]}
