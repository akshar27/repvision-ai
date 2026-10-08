import math

from app.exercises import build_config, create_analyzer
from app.vision.landmarks import LM
from tests.synth import FPS, ease, feed, lead_in, pullup_pose, rep_profile, seq

BAR = 0.20


def run(angles, bar_y=BAR, preset="standard", cfg_over=None, **kw):
    cfg = build_config("pullup", preset, cfg_over, bar_y)
    a = create_analyzer("pullup", cfg)
    return feed(a, seq(pullup_pose, angles, bar_y=BAR, **kw)), a


FULL = lead_in(172) + rep_profile(172, 40, 1.2, 0.3, 1.2)


def test_valid_full_repetition_with_bar_calibration():
    reps, _ = run(FULL)
    assert [r.classification for r in reps] == ["full"]
    r = reps[0]
    assert r.criteria["top_clearance"] == "met"
    assert r.rom["shoulder_travel_ratio"] >= 0.3
    assert r.measurements["clearance_margin_ratio"] >= 0


def test_insufficient_top_clearance_is_partial():
    reps, _ = run(FULL, head_up=0.06)       # head stays below the calibrated bar
    assert reps[0].classification == "partial"
    assert reps[0].criteria["top_clearance"] == "not_met"
    assert any(f.code == "PULLUP_CLEARANCE_NOT_MET" for f in reps[0].feedback)


def test_uncertain_top_clearance_without_bar():
    reps, _ = run(FULL, bar_y=None)
    assert reps[0].classification == "uncertain"
    assert reps[0].criteria["top_clearance"] == "unverified"
    assert any(f.code == "PULLUP_CLEARANCE_UNVERIFIED" for f in reps[0].feedback)


def test_uncertain_when_head_landmarks_hidden_at_top():
    vis = {int(i): 0.1 for i in (LM.NOSE, LM.MOUTH_LEFT, LM.MOUTH_RIGHT)}
    reps, _ = run(FULL, vis=vis)
    assert reps[0].classification == "uncertain"
    assert reps[0].criteria["top_clearance"] == "unverified"


def test_without_bar_requirement_relaxed_counts_full_but_unverified():
    reps, _ = run(FULL, bar_y=None, cfg_over={"require_bar_for_full": False})
    assert reps[0].classification == "full"
    assert reps[0].criteria["top_clearance"] == "unverified"


def test_bent_elbow_start_is_partial():
    prof = lead_in(135, 1.5) + ease(30, 135, 40) + [40] * 9 + ease(36, 40, 172) + [172] * 30
    reps, _ = run(prof)
    assert reps and reps[0].classification == "partial"
    assert any(f.code == "PULLUP_START_BENT" for f in reps[0].feedback)


def test_insufficient_range_of_motion():
    reps, _ = run(lead_in(172) + rep_profile(172, 110))
    assert reps[0].classification == "partial"
    assert any(f.code == "PULLUP_ROM" for f in reps[0].feedback)


def test_incomplete_return_to_dead_hang():
    prof = lead_in(172) + ease(36, 172, 40) + [40] * 9 + ease(30, 40, 125) + [125] * 70
    reps, _ = run(prof)
    assert reps and reps[0].classification != "full"
    assert any(f.code == "PULLUP_NO_HANG" for f in reps[0].feedback)


def test_partial_pullup_incomplete_return_then_second_pull():
    prof = lead_in(172) + ease(36, 172, 40) + [40] * 9 + ease(25, 40, 120) + ease(25, 120, 40) + [40] * 6 + ease(36, 40, 172) + [172] * 30
    reps, _ = run(prof)
    assert [r.classification for r in reps] == ["partial", "partial"]


def test_multiple_full_reps():
    reps, _ = run(lead_in(172) + rep_profile(172, 40, 1.0, 0.2, 1.0) * 3)
    assert [r.classification for r in reps] == ["full"] * 3


def test_phase_names_and_no_motion():
    a = create_analyzer("pullup", build_config("pullup", "standard", None, BAR))
    r = a.update(pullup_pose(172, 0, bar_y=BAR), 0)
    assert r.phase == "DEAD_HANG"
    reps, _ = run([172.0] * 200)
    assert reps == []


def test_not_hanging_posture_ignored():
    from tests.synth import squat_pose
    reps = feed(create_analyzer("pullup"), seq(squat_pose, lead_in(172) + rep_profile(172, 80)))
    assert reps == []
