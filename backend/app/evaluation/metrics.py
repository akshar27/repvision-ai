"""Evaluate predicted repetitions against manually annotated ground truth.

Predictions are matched to ground-truth reps by temporal overlap (interval IoU),
one-to-one, greedy in descending IoU, with a minimum IoU. Counting-only metrics
can hide offsetting errors (a missed rep + a phantom rep); matching prevents that.
"""
from __future__ import annotations

from dataclasses import dataclass

LABELS = ("full", "partial")


@dataclass
class Interval:
    start_ms: float
    end_ms: float
    label: str


def iou(a: Interval, b: Interval) -> float:
    inter = max(0.0, min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms))
    union = (a.end_ms - a.start_ms) + (b.end_ms - b.start_ms) - inter
    return inter / union if union > 0 else 0.0


def match(gt: list[Interval], pred: list[Interval], min_iou: float = 0.3) -> list[tuple[int, int, float]]:
    cands = sorted(((iou(g, p), gi, pi) for gi, g in enumerate(gt) for pi, p in enumerate(pred)), reverse=True)
    used_g, used_p, out = set(), set(), []
    for v, gi, pi in cands:
        if v < min_iou:
            break
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        out.append((gi, pi, v))
    return sorted(out)


def _div(a: float, b: float) -> float | None:
    return round(a / b, 4) if b else None


def _f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None or (p + r) == 0:
        return None if (p is None and r is None) else 0.0
    return round(2 * p * r / (p + r), 4)


def evaluate(gt_doc: dict, pred_doc: dict, min_iou: float = 0.3) -> dict:
    gt = [Interval(r["start_ms"], r["end_ms"], r["label"]) for r in gt_doc["reps"]]
    pred = [Interval(r["start_ms"], r["end_ms"], r["classification"]) for r in pred_doc["reps"]]
    if gt_doc.get("exercise") and pred_doc.get("exercise") and gt_doc["exercise"] != pred_doc["exercise"]:
        raise ValueError(f"exercise mismatch: ground truth {gt_doc['exercise']} vs prediction {pred_doc['exercise']}")
    pairs = match(gt, pred, min_iou)
    matched_g = {g for g, _, _ in pairs}
    matched_p = {p for _, p, _ in pairs}

    per_label = {}
    for lab in LABELS:
        tp = sum(1 for g, p, _ in pairs if gt[g].label == lab and pred[p].label == lab)
        fp = sum(1 for p, x in enumerate(pred) if x.label == lab) - tp
        fn = sum(1 for x in gt if x.label == lab) - tp
        prec, rec = _div(tp, tp + fp), _div(tp, tp + fn)
        per_label[lab] = {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "f1": _f1(prec, rec)}
    f1s = [v["f1"] for v in per_label.values() if v["f1"] is not None]
    n_gt, n_pred = len(gt), len(pred)

    errors = {}
    for cat in {e for r in gt_doc["reps"] for e in r.get("errors", [])}:
        have = [i for i, r in enumerate(gt_doc["reps"]) if cat in r.get("errors", [])]
        hit = 0
        for g, p, _ in pairs:
            if g in have and any(cat.lower() in f["code"].lower() or cat.lower() in f["message"].lower()
                                 for f in pred_doc["reps"][p].get("feedback", [])):
                hit += 1
        errors[cat] = {"annotated": len(have), "detected": hit, "recall": _div(hit, len(have))}

    perf, trk = pred_doc.get("performance") or {}, pred_doc.get("tracking") or {}
    return {
        "exercise": gt_doc.get("exercise"),
        "min_iou": min_iou,
        "counts": {"ground_truth": n_gt, "predicted": n_pred, "matched": len(pairs),
                   "missed": n_gt - len(matched_g), "extra": n_pred - len(matched_p),
                   "predicted_uncertain": sum(1 for p in pred if p.label == "uncertain")},
        "total_count_error": n_pred - n_gt,
        "total_count_abs_error": abs(n_pred - n_gt),
        "total_count_relative_error": _div(abs(n_pred - n_gt), n_gt),
        "full": per_label["full"], "partial": per_label["partial"],
        "full_rep_precision": per_label["full"]["precision"], "full_rep_recall": per_label["full"]["recall"],
        "partial_rep_recall": per_label["partial"]["recall"],
        "classification_macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
        "error_categories": errors,
        "mean_matched_iou": round(sum(v for *_, v in pairs) / len(pairs), 4) if pairs else None,
        "processing_seconds": perf.get("processing_seconds"), "processing_fps": perf.get("processing_fps"),
        "tracking_pose_coverage": trk.get("pose_coverage"), "tracking_valid_coverage": trk.get("valid_coverage"),
    }
