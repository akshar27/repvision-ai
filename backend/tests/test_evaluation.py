from app.evaluation.metrics import Interval, evaluate, iou, match


def doc(reps, key, **extra):
    return {"exercise": "squat", "reps": [dict(start_ms=a, end_ms=b, **{key: lab}) for a, b, lab in reps], **extra}


def test_iou_and_matching_is_one_to_one():
    assert iou(Interval(0, 100, "full"), Interval(50, 150, "full")) == 50 / 150
    gt = [Interval(0, 100, "full"), Interval(200, 300, "full")]
    pred = [Interval(10, 110, "full"), Interval(15, 105, "full")]     # two preds on the same GT rep
    assert len(match(gt, pred)) == 1


def test_perfect_prediction():
    reps = [(0, 1000, "full"), (2000, 3000, "partial")]
    r = evaluate(doc(reps, "label"), doc(reps, "classification"))
    assert r["total_count_error"] == 0 and r["full_rep_precision"] == 1 and r["full_rep_recall"] == 1
    assert r["partial_rep_recall"] == 1 and r["classification_macro_f1"] == 1


def test_offsetting_count_errors_are_not_hidden():
    gt = doc([(0, 1000, "full"), (2000, 3000, "full")], "label")
    pr = doc([(0, 1000, "full"), (5000, 6000, "full")], "classification")     # same count, one miss + one phantom
    r = evaluate(gt, pr)
    assert r["total_count_error"] == 0
    assert r["counts"]["missed"] == 1 and r["counts"]["extra"] == 1
    assert r["full_rep_precision"] == 0.5 and r["full_rep_recall"] == 0.5


def test_partial_predicted_as_full_and_uncertain():
    gt = doc([(0, 1000, "partial"), (2000, 3000, "full")], "label")
    pr = doc([(0, 1000, "full"), (2000, 3000, "uncertain")], "classification")
    r = evaluate(gt, pr)
    assert r["partial_rep_recall"] == 0 and r["full_rep_recall"] == 0
    assert r["counts"]["predicted_uncertain"] == 1


def test_error_category_recall_and_metadata():
    gt = {"exercise": "squat", "reps": [{"start_ms": 0, "end_ms": 1000, "label": "partial", "errors": ["depth"]}]}
    pr = {"exercise": "squat", "reps": [{"start_ms": 0, "end_ms": 1000, "classification": "partial",
                                         "feedback": [{"code": "SQUAT_DEPTH", "message": "Insufficient squat depth"}]}],
          "performance": {"processing_seconds": 2.0, "processing_fps": 30.0}, "tracking": {"pose_coverage": 0.9}}
    r = evaluate(gt, pr)
    assert r["error_categories"]["depth"]["recall"] == 1.0
    assert r["processing_fps"] == 30.0 and r["tracking_pose_coverage"] == 0.9


def test_exercise_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        evaluate({"exercise": "squat", "reps": []}, {"exercise": "pushup", "reps": []})
