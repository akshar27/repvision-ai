import math

from app.exercises import build_config, create_analyzer
from app.vision import geometry as g
from app.vision.landmarks import LM
from tests.synth import FPS, feed, lead_in, rep_profile, seq, squat_pose


def run(angles, preset="standard", **kw):
    a = create_analyzer("squat", build_config("squat", preset))
    return feed(a, seq(squat_pose, angles, **kw)), a


def test_synthetic_pose_has_requested_knee_angle():
    p = squat_pose(100.0, 0)
    ang = g.angle_deg(p.xy(LM.LEFT_HIP), p.xy(LM.LEFT_KNEE), p.xy(LM.LEFT_ANKLE))
    assert math.isclose(ang, 100.0, abs_tol=0.5)


def test_valid_full_repetition():
    reps, a = run(lead_in(172) + rep_profile(172, 80))
    assert [r.classification for r in reps] == ["full"]
    r = reps[0]
    assert r.measurements["min_angle"] < 100
    assert r.criteria["returned_standing"] and r.criteria["depth_knee_angle"]
    assert r.feedback[0].code == "REP_FULL"
    assert 0.5 < r.measurement_confidence <= 1.0 and r.classification_confidence > 0.5
    assert r.duration_ms > 1500


def test_three_reps_counted_once_each():
    reps, _ = run(lead_in(172) + rep_profile(172, 80) * 3)
    assert [r.classification for r in reps] == ["full"] * 3
    assert [r.index for r in reps] == [1, 2, 3]
    assert all(reps[i].end_ms <= reps[i + 1].start_ms + 200 for i in range(2))


def test_partial_depth_repetition():
    reps, _ = run(lead_in(172) + rep_profile(172, 120))
    assert [r.classification for r in reps] == ["partial"]
    assert any(f.code == "SQUAT_DEPTH" for f in reps[0].feedback)


def test_no_motion_yields_no_reps():
    reps, a = run([172.0] * 300)
    assert reps == [] and a.counter.summary.total == 0


def test_standing_jitter_yields_no_reps():
    import numpy as np
    rng = np.random.default_rng(1)
    reps, _ = run(list(170 + rng.normal(0, 2.5, 400)))
    assert reps == []


def test_oscillation_near_depth_threshold_counts_one_rep():
    # hover around the 100 deg depth threshold at the bottom: must not double count
    bottom = [100 + 3 * math.sin(i * 1.7) for i in range(25)]
    profile = lead_in(172) + rep_profile(172, 100, hold_s=0)[:36] + bottom
    profile += rep_profile(172, 100, hold_s=0)[36:]
    reps, _ = run(profile)
    assert len(reps) == 1


def test_oscillation_near_rest_threshold_counts_one_rep():
    top = [158 + 4 * math.sin(i * 2.3) for i in range(30)]   # wobbling around rest_enter (160)
    reps, _ = run(lead_in(172) + rep_profile(172, 80, rest_s=0) + top + [172] * 30)
    assert len(reps) == 1


def test_incomplete_standing_extension_then_second_rep():
    # squat, come up only to 140, squat again from there, then stand fully
    from tests.synth import ease
    prof = (lead_in(172) + ease(36, 172, 80) + [80] * 9 + ease(20, 80, 140) + ease(20, 140, 80) + [80] * 5
            + ease(36, 80, 172) + [172] * 30)
    reps, _ = run(prof)
    assert [r.classification for r in reps] == ["partial", "partial"]
    assert any(f.code == "SQUAT_NO_STAND" for f in reps[0].feedback)
    # the second descent began from a non-standing position, which the rules do not accept as a full rep
    assert reps[1].criteria["started_standing"] is False
    assert any(f.code == "SQUAT_START_NOT_STANDING" for f in reps[1].feedback)


def test_missing_landmarks_mid_rep_is_uncertain():
    prof = lead_in(172) + rep_profile(172, 80)
    poses = seq(squat_pose, prof)
    mid = len(poses) // 2
    for i in range(mid - 20, mid + 20):    # ~1.3 s of lost tracking at the bottom
        poses[i] = None
    reps = feed(create_analyzer("squat"), poses)
    assert reps and all(r.classification == "uncertain" for r in reps)
    assert not any(r.classification == "full" for r in reps)


def test_low_visibility_legs_are_not_counted():
    vis = {int(i): 0.1 for i in (LM.LEFT_HIP, LM.RIGHT_HIP, LM.LEFT_KNEE, LM.RIGHT_KNEE)}
    reps, _ = run(lead_in(172) + rep_profile(172, 80), vis=vis)
    assert reps == []


def test_strict_preset_rejects_borderline_depth():
    prof = lead_in(172) + rep_profile(172, 95)
    standard, _ = run(prof, "standard")
    strict, _ = run(prof, "strict")
    assert standard[0].classification == "full"
    assert strict[0].classification == "partial"


def test_torso_lean_warning_does_not_change_classification():
    reps, _ = run(lead_in(172) + rep_profile(172, 80), lean_deg=70)
    assert reps[0].classification == "full"
    assert any(f.code == "SQUAT_TORSO" for f in reps[0].feedback)


def test_video_starting_mid_squat_is_uncertain():
    prof = rep_profile(172, 80)[int(0.6 * FPS):]
    prof = [130 - 0.0] * 3 + prof
    reps, _ = run(prof)
    assert all(r.classification != "full" for r in reps)


def test_reset_clears_session_and_isolated_sessions():
    a = create_analyzer("squat")
    b = create_analyzer("squat")
    feed(a, seq(squat_pose, lead_in(172) + rep_profile(172, 80)))
    assert a.counter.summary.full == 1 and b.counter.summary.total == 0
    a.reset()
    assert a.counter.summary.total == 0
