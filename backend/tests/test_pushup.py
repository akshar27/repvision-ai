import math

from app.exercises import build_config, create_analyzer
from app.vision import geometry as g
from app.vision.landmarks import LM
from tests.synth import FPS, ease, feed, lead_in, pushup_pose, rep_profile, seq


def run(angles, preset="standard", **kw):
    a = create_analyzer("pushup", build_config("pushup", preset))
    return feed(a, seq(pushup_pose, angles, **kw)), a


def test_synthetic_pose_elbow_angle():
    p = pushup_pose(90.0, 0)
    ang = g.angle_deg(p.xy(LM.LEFT_SHOULDER), p.xy(LM.LEFT_ELBOW), p.xy(LM.LEFT_WRIST))
    assert math.isclose(ang, 90.0, abs_tol=1.0)


def test_valid_full_repetition():
    reps, _ = run(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9))
    assert [r.classification for r in reps] == ["full"]
    assert reps[0].rom["shoulder_drop_ratio"] > 0.08
    assert reps[0].feedback[0].code == "REP_FULL"


def test_incomplete_depth_is_partial():
    reps, _ = run(lead_in(168) + rep_profile(168, 120, 0.9, 0.2, 0.9))
    assert [r.classification for r in reps] == ["partial"]
    assert any(f.code == "PUSHUP_DEPTH" for f in reps[0].feedback)


def test_incomplete_extension_is_partial():
    prof = lead_in(168) + ease(27, 168, 70) + [70] * 6 + ease(20, 70, 135) + ease(20, 135, 70) + [70] * 5 + ease(27, 70, 168) + [168] * 25
    reps, _ = run(prof)
    assert reps[0].classification == "partial"
    assert any(f.code == "PUSHUP_NO_LOCKOUT" for f in reps[0].feedback)


def test_hip_sag_flagged_but_rep_still_full():
    reps, _ = run(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9), sag=0.15)
    assert reps[0].classification == "full"
    assert any(f.code == "PUSHUP_SAG" for f in reps[0].feedback)
    assert not any(f.code == "PUSHUP_PIKE" for f in reps[0].feedback)


def test_hip_pike_flagged():
    reps, _ = run(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9), sag=-0.18)
    assert any(f.code == "PUSHUP_PIKE" for f in reps[0].feedback)


def test_straight_body_has_no_alignment_warning():
    reps, _ = run(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9), sag=0.0)
    codes = {f.code for f in reps[0].feedback}
    assert not codes & {"PUSHUP_SAG", "PUSHUP_PIKE"}


def test_tracking_loss_mid_rep_not_counted_as_full():
    poses = seq(pushup_pose, lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9))
    mid = len(poses) // 2
    for i in range(mid - 20, mid + 20):
        poses[i] = None
    reps = feed(create_analyzer("pushup"), poses)
    assert not any(r.classification == "full" for r in reps)
    assert all(r.classification == "uncertain" for r in reps)


def test_no_motion_and_low_visibility():
    reps, _ = run([168.0] * 300)
    assert reps == []
    vis = {int(i): 0.1 for i in (LM.LEFT_ELBOW, LM.RIGHT_ELBOW)}
    reps, _ = run(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9), vis=vis)
    assert reps == []


def test_multiple_reps():
    reps, _ = run(lead_in(168) + rep_profile(168, 70, 0.8, 0.1, 0.8) * 4)
    assert [r.classification for r in reps] == ["full"] * 4


def test_standing_posture_is_not_counted():
    # squat skeleton (upright body) fed to the push-up analyzer must not count
    from tests.synth import squat_pose
    a = create_analyzer("pushup")
    reps = feed(a, seq(squat_pose, lead_in(172) + rep_profile(172, 80)))
    assert reps == []
