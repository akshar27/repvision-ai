"""Local-filesystem storage. All paths derive from validated ids (no path traversal).

``ResultStore`` is the seam for swapping JSON files for SQLite/PostgreSQL later:
the rest of the app only calls ``save/load/exists``.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Protocol

from ..config import settings
from ..models.schemas import AnalysisResult

_ID_RE = re.compile(r"^[a-f0-9]{32}$")


class InvalidId(ValueError):
    pass


class UploadTooLarge(ValueError):
    pass


def new_id() -> str:
    return uuid.uuid4().hex


def validate_id(analysis_id: str) -> str:
    if not _ID_RE.fullmatch(analysis_id or ""):
        raise InvalidId("Invalid analysis id.")
    return analysis_id


class ResultStore(Protocol):
    def save(self, result: AnalysisResult) -> None: ...
    def load(self, analysis_id: str) -> AnalysisResult | None: ...
    def list_ids(self) -> list[str]: ...


class JsonResultStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.root = Path(data_dir or settings.data_dir)
        self.uploads = self.root / "uploads"
        self.outputs = self.root / "outputs"
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)

    # --- paths (ids validated first) ---
    def output_dir(self, analysis_id: str) -> Path:
        return self.outputs / validate_id(analysis_id)

    def result_path(self, analysis_id: str) -> Path:
        return self.output_dir(analysis_id) / "result.json"

    def video_path(self, analysis_id: str) -> Path:
        return self.output_dir(analysis_id) / "annotated.mp4"

    def upload_path(self, analysis_id: str, ext: str) -> Path:
        return self.uploads / f"{validate_id(analysis_id)}{ext}"

    # --- results ---
    def save(self, result: AnalysisResult) -> None:
        d = self.output_dir(result.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "result.json.tmp"
        tmp.write_text(result.model_dump_json(indent=1))
        os.replace(tmp, self.result_path(result.id))      # atomic: readers never see a partial file

    def load(self, analysis_id: str) -> AnalysisResult | None:
        p = self.result_path(analysis_id)
        if not p.exists():
            return None
        return AnalysisResult.model_validate_json(p.read_text())

    def list_ids(self) -> list[str]:
        return [p.name for p in self.outputs.iterdir() if p.is_dir() and _ID_RE.fullmatch(p.name)]

    # --- uploads ---
    async def save_upload(self, analysis_id: str, upload, ext: str, max_bytes: int) -> Path:
        """Stream an UploadFile to disk, enforcing the size limit while reading."""
        dest = self.upload_path(analysis_id, ext)
        size = 0
        try:
            with open(dest, "wb") as f:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadTooLarge(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.")
                    f.write(chunk)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
        if size == 0:
            dest.unlink(missing_ok=True)
            raise ValueError("Uploaded file is empty.")
        return dest

    def delete_upload(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def save_calibration(self, name: str, payload: dict) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:60] or "calibration"
        d = settings.annotations_dir
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{safe}.json"
        p.write_text(json.dumps(payload, indent=2))
        return p
