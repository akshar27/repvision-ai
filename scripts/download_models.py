#!/usr/bin/env python3
"""Download official MediaPipe Pose Landmarker model assets.

Usage: python scripts/download_models.py [lite|full|heavy ...]   (default: full lite)
Models go to backend/assets/ (backend) and frontend/public/models/ (webcam mode).
"""
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_{v}/float16/latest/pose_landmarker_{v}.task"


def main() -> None:
    variants = sys.argv[1:] or ["full", "lite"]
    dest = ROOT / "backend" / "assets"
    dest.mkdir(parents=True, exist_ok=True)
    web = ROOT / "frontend" / "public" / "models"
    web.mkdir(parents=True, exist_ok=True)
    for v in variants:
        target = dest / f"pose_landmarker_{v}.task"
        if not target.exists():
            print(f"downloading {v} -> {target}")
            urllib.request.urlretrieve(URL.format(v=v), target)
        if v in ("lite", "full"):
            shutil.copyfile(target, web / target.name)
    print("done")


if __name__ == "__main__":
    main()
