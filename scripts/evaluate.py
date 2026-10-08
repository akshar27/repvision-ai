#!/usr/bin/env python3
"""Compare an analysis result JSON against manually annotated ground truth.

  python scripts/evaluate.py ground_truth.json data/outputs/<id>/result.json [--csv report.csv] [--json report.json]

Ground truth format: see data/annotations/ground_truth_example.json
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.evaluation.metrics import evaluate  # noqa: E402


def flatten(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from flatten(v, f"{prefix}{k}.")
        else:
            yield f"{prefix}{k}", v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ground_truth", type=Path)
    ap.add_argument("prediction", type=Path)
    ap.add_argument("--min-iou", type=float, default=0.3)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args()
    report = evaluate(json.loads(a.ground_truth.read_text()), json.loads(a.prediction.read_text()), a.min_iou)
    text = json.dumps(report, indent=2)
    print(text)
    if a.json:
        a.json.write_text(text)
    if a.csv:
        with a.csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["metric", "value"])
            w.writerows(flatten(report))


if __name__ == "__main__":
    main()
