"""Pydantic schemas shared by the analyzers and the HTTP API."""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field

Classification = Literal["full", "partial", "uncertain"]
Severity = Literal["success", "info", "warning", "error"]


def num(x: float | None, nd: int = 3) -> float | None:
    """JSON-safe number: NaN/inf -> None."""
    if x is None:
        return None
    x = float(x)
    return round(x, nd) if math.isfinite(x) else None


class FeedbackItem(BaseModel):
    code: str
    severity: Severity
    message: str


class RepEvent(BaseModel):
    index: int
    start_ms: float
    end_ms: float
    duration_ms: float
    classification: Classification
    measurements: dict[str, float | None] = Field(default_factory=dict)
    rom: dict[str, float | None] = Field(default_factory=dict)
    criteria: dict[str, bool | str | None] = Field(default_factory=dict)
    feedback: list[FeedbackItem] = Field(default_factory=list)
    measurement_confidence: float          # confidence in landmark measurements during the rep
    classification_confidence: float       # heuristic confidence in the full/partial/uncertain label


class RepSummary(BaseModel):
    total: int = 0
    full: int = 0
    partial: int = 0
    uncertain: int = 0


class SeriesPoint(BaseModel):
    t: float
    signal: float | None
    angles: dict[str, float | None] = Field(default_factory=dict)
    phase: str
    valid: bool


class TrackingStats(BaseModel):
    frames_processed: int
    frames_with_pose: int
    frames_valid: int
    pose_coverage: float
    valid_coverage: float


class VideoInfo(BaseModel):
    filename: str | None = None
    width: int
    height: int
    fps: float
    duration_s: float
    frame_count: int


class PerformanceInfo(BaseModel):
    processing_seconds: float
    processing_fps: float
    pose_model: str
    inference_max_side: int
    hardware: str
    note: str = "Measured on the machine that ran this analysis; not a benchmark."


class OutputVideo(BaseModel):
    available: bool
    codec: str | None = None
    browser_compatible: bool = False
    warning: str | None = None


class AnalysisResult(BaseModel):
    id: str
    status: Literal["queued", "processing", "completed", "failed"]
    exercise: str
    created_at: str
    progress: float = 0.0
    error: str | None = None
    video: VideoInfo | None = None
    summary: RepSummary = Field(default_factory=RepSummary)
    reps: list[RepEvent] = Field(default_factory=list)
    series: list[SeriesPoint] = Field(default_factory=list)
    tracking: TrackingStats | None = None
    performance: PerformanceInfo | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    feedback_summary: list[dict[str, Any]] = Field(default_factory=list)
    output_video: OutputVideo | None = None
    disclaimer: str = ""
