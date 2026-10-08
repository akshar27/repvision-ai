"""Feedback catalog. Messages are observations of measured movement, not medical advice."""
from __future__ import annotations

from collections import Counter

from ..models.schemas import FeedbackItem, RepEvent

DISCLAIMER = (
    "RepVision AI provides estimated movement feedback from 2D pose estimation. It is not a medical "
    "assessment, injury-risk diagnosis, or guarantee of exercise safety or technique quality. "
    "Accuracy depends on camera placement, lighting, clothing and the pose model."
)

# code -> (severity, message template)
CATALOG: dict[str, tuple[str, str]] = {
    "REP_FULL": ("success", "Full repetition completed."),
    "LOW_VISIBILITY": ("error", "Unable to validate repetition due to poor landmark visibility."),
    "TRACKING_GAP": ("error", "Tracking was lost during this repetition, so it could not be validated."),
    "VIDEO_ENDED": ("info", "The video ended before this repetition finished, so it could not be validated."),
    "INVALID_START": ("info", "The video started mid-movement, so the starting position could not be validated."),
    # squat
    "SQUAT_DEPTH": ("warning", "Insufficient squat depth (minimum knee angle {min_angle:.0f}°, target ≤ {target:.0f}°)."),
    "SQUAT_HIP_ABOVE_KNEE": ("warning", "Hips did not drop to knee level (required by the strict preset)."),
    "SQUAT_NO_STAND": ("warning", "Incomplete standing extension before the next movement."),
    "SQUAT_START_NOT_STANDING": ("warning", "Repetition did not start from a full standing position."),
    "SQUAT_TORSO": ("warning", "Significant torso movement detected (peak inclination {lean:.0f}° from vertical)."),
    # push-up
    "PUSHUP_DEPTH": ("warning", "Insufficient depth (minimum elbow angle {min_angle:.0f}°, target ≤ {target:.0f}°)."),
    "PUSHUP_SHOULDER": ("warning", "Shoulders did not travel far enough downward."),
    "PUSHUP_NO_LOCKOUT": ("warning", "Incomplete elbow extension at the top."),
    "PUSHUP_START_NOT_EXTENDED": ("warning", "Repetition did not start from fully extended arms."),
    "PUSHUP_SAG": ("warning", "Significant hip sagging detected ({dev:.0%} of body length below the shoulder–ankle line)."),
    "PUSHUP_PIKE": ("warning", "Significant hip elevation detected ({dev:.0%} of body length above the shoulder–ankle line)."),
    # pull-up
    "PULLUP_START_BENT": ("warning", "Started with bent elbows (no full dead hang before the pull)."),
    "PULLUP_ROM": ("warning", "Insufficient upward range of motion (minimum elbow angle {min_angle:.0f}°, shoulder travel {travel:.2f}× arm length)."),
    "PULLUP_NO_HANG": ("warning", "Did not return to a dead hang."),
    "PULLUP_CLEARANCE_UNVERIFIED": ("info", "Top clearance could not be verified (no bar calibration, or head landmarks not visible at the top)."),
    "PULLUP_CLEARANCE_NOT_MET": ("warning", "Head did not clear the calibrated bar height at the top."),
}


def make(code: str, **kw) -> FeedbackItem:
    sev, tmpl = CATALOG[code]
    return FeedbackItem(code=code, severity=sev, message=tmpl.format(**kw) if kw else tmpl)


def summarize(reps: list[RepEvent]) -> list[dict]:
    """Aggregate feedback across reps: [{code, severity, message, count}] most frequent first."""
    counts: Counter[str] = Counter()
    sample: dict[str, FeedbackItem] = {}
    for r in reps:
        for f in r.feedback:
            if f.code == "REP_FULL":
                continue
            counts[f.code] += 1
            sample.setdefault(f.code, f)
    return [
        {"code": c, "severity": sample[c].severity, "message": sample[c].message, "count": n}
        for c, n in counts.most_common()
    ]
