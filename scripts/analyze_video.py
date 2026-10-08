#!/usr/bin/env python3
"""CLI: analyze a video file with the same pipeline the API uses.

  python scripts/analyze_video.py squat clip.mp4 --out data/outputs/cli --sensitivity standard
  python scripts/analyze_video.py pullup clip.mp4 --calibration data/annotations/sample_calibration.json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.exercises import EXERCISES, CalibrationInput, config_from_calibration, create_analyzer  # noqa: E402
from app.tracking.feedback import DISCLAIMER, summarize  # noqa: E402
from app.vision.mediapipe_estimator import MediaPipePoseEstimator  # noqa: E402
from app.vision.video_processor import process_video  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exercise", choices=EXERCISES)
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/outputs/cli"))
    ap.add_argument("--sensitivity", choices=["lenient", "standard", "strict"], default=None)
    ap.add_argument("--calibration", type=Path, help="calibration JSON (see data/annotations/)")
    ap.add_argument("--bar-y", type=float, help="pull-up bar height as a fraction of frame height (0=top)")
    ap.add_argument("--no-video", action="store_true", help="skip writing the annotated video")
    a = ap.parse_args()

    cal = CalibrationInput.model_validate_json(a.calibration.read_text()) if a.calibration else None
    if a.bar_y is not None:
        cal = (cal or CalibrationInput()).model_copy(update={"bar_y": a.bar_y})
    cfg = config_from_calibration(a.exercise, cal, a.sensitivity)
    a.out.mkdir(parents=True, exist_ok=True)
    out_video = None if a.no_video else a.out / f"{a.video.stem}_{a.exercise}_annotated.mp4"
    with MediaPipePoseEstimator() as est:
        res = process_video(a.video, create_analyzer(a.exercise, cfg), est, filename=a.video.name, output_path=out_video,
                            inference_max_side=settings.inference_max_side, bar_y=getattr(cfg, "bar_y", None),
                            on_progress=lambda p: print(f"\r{p:5.0%}", end="", file=sys.stderr))
    print(file=sys.stderr)
    doc = {"exercise": a.exercise, "summary": res.summary.model_dump(), "reps": [r.model_dump() for r in res.reps],
           "tracking": res.tracking.model_dump(), "performance": res.performance.model_dump(),
           "video": res.video.model_dump(), "warnings": res.warnings, "feedback_summary": summarize(res.reps),
           "config": cfg.model_dump(), "disclaimer": DISCLAIMER}
    out_json = a.out / f"{a.video.stem}_{a.exercise}.json"
    out_json.write_text(json.dumps(doc, indent=1))
    s = res.summary
    print(f"{a.exercise}: total={s.total} full={s.full} partial={s.partial} uncertain={s.uncertain}")
    for r in res.reps:
        print(f"  #{r.index} {r.start_ms/1000:6.1f}-{r.end_ms/1000:6.1f}s {r.classification:9s} "
              f"min={r.measurements.get('min_angle')} conf={r.measurement_confidence:.2f}  "
              + "; ".join(f.message for f in r.feedback))
    t, p = res.tracking, res.performance
    print(f"tracking: pose {t.pose_coverage:.0%}, valid {t.valid_coverage:.0%} | {p.processing_fps:.1f} fps on {p.hardware}")
    for w in res.warnings:
        print("WARNING:", w)
    print(f"wrote {out_json}" + (f" and {out_video}" if out_video else ""))


if __name__ == "__main__":
    main()
