#!/usr/bin/env python3
"""Export the single source of truth for the TypeScript (webcam) engine:

  frontend/lib/generated/exercise-configs.json  - all exercise configs per sensitivity preset
  frontend/lib/generated/feedback-catalog.json  - feedback codes/messages
  frontend/tests/fixtures/parity.json           - synthetic landmark scenarios + the Python engine's output,
                                                  replayed against the TS engine by `npm test`

Re-run after changing thresholds, feedback text or analyzer rules:  python scripts/export_shared.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.exercises import EXERCISES, build_config, create_analyzer  # noqa: E402
from app.exercises.config import PRESETS  # noqa: E402
from app.tracking.feedback import CATALOG, DISCLAIMER  # noqa: E402
from tests.synth import (ASPECT, FPS, ease, lead_in, pullup_pose, pushup_pose, rep_profile, seq,  # noqa: E402
                         squat_pose)

GEN = ROOT / "frontend" / "lib" / "generated"
FIX = ROOT / "frontend" / "tests" / "fixtures"
GEN.mkdir(parents=True, exist_ok=True)
FIX.mkdir(parents=True, exist_ok=True)


def enc(pose):
    if pose is None:
        return None
    return {"x": [round(float(v), 6) for v in pose.points[:, 0]], "y": [round(float(v), 6) for v in pose.points[:, 1]],
            "vis": [round(float(v), 4) for v in pose.visibility]}


def scenario(name, exercise, poses, preset="standard", overrides=None, bar_y=None):
    cfg = build_config(exercise, preset, overrides, bar_y)
    a = create_analyzer(exercise, cfg)
    reps, last = [], 0.0
    times = []
    for i, p in enumerate(poses):
        t = i * 1000.0 / FPS
        times.append(t)
        reps += a.update(p, t).new_reps
        last = t
    reps += a.finish(last)
    return {
        "name": name, "exercise": exercise, "config": cfg.model_dump(), "aspect": ASPECT,
        "frames": [{"t": round(t, 3), "pose": enc(p)} for t, p in zip(times, poses)],
        "expected": [{"classification": r.classification, "start_ms": r.start_ms, "end_ms": r.end_ms,
                      "min_angle": r.measurements.get("min_angle"), "codes": [f.code for f in r.feedback],
                      "measurement_confidence": r.measurement_confidence,
                      "top_clearance": r.criteria.get("top_clearance")} for r in reps],
    }


def main() -> None:
    (GEN / "exercise-configs.json").write_text(json.dumps(
        {e: {p: build_config(e, p).model_dump() for p in PRESETS} for e in EXERCISES}, indent=1))
    (GEN / "feedback-catalog.json").write_text(json.dumps(
        {"catalog": {k: {"severity": v[0], "template": v[1]} for k, v in CATALOG.items()}, "disclaimer": DISCLAIMER}, indent=1))

    sq = lambda ang, **k: seq(squat_pose, ang, **k)  # noqa: E731
    pu = lambda ang, **k: seq(pushup_pose, ang, **k)  # noqa: E731
    pl = lambda ang, **k: seq(pullup_pose, ang, **k)  # noqa: E731
    gap = sq(lead_in(172) + rep_profile(172, 80))
    for i in range(len(gap) // 2 - 20, len(gap) // 2 + 20):
        gap[i] = None
    full_pullup = lead_in(172) + rep_profile(172, 40, 1.2, 0.3, 1.2)
    sc = [
        scenario("squat_two_full", "squat", sq(lead_in(172) + rep_profile(172, 80) * 2)),
        scenario("squat_partial_depth", "squat", sq(lead_in(172) + rep_profile(172, 120))),
        scenario("squat_incomplete_extension", "squat", sq(lead_in(172) + ease(36, 172, 80) + [80] * 9 + ease(20, 80, 140)
                                                         + ease(20, 140, 80) + [80] * 5 + ease(36, 80, 172) + [172] * 30)),
        scenario("squat_tracking_loss", "squat", gap),
        scenario("squat_strict_borderline", "squat", sq(lead_in(172) + rep_profile(172, 95)), preset="strict"),
        scenario("squat_high_lean", "squat", sq(lead_in(172) + rep_profile(172, 80), lean_deg=70)),
        scenario("pushup_full_then_partial", "pushup", pu(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9)
                                                          + rep_profile(168, 120, 0.9, 0.2, 0.9))),
        scenario("pushup_sag", "pushup", pu(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9), sag=0.15)),
        scenario("pushup_pike", "pushup", pu(lead_in(168) + rep_profile(168, 70, 0.9, 0.2, 0.9), sag=-0.18)),
        scenario("pullup_full_with_bar", "pullup", pl(full_pullup, bar_y=0.20), bar_y=0.20),
        scenario("pullup_clearance_not_met", "pullup", pl(full_pullup, bar_y=0.20, head_up=0.06), bar_y=0.20),
        scenario("pullup_no_bar_uncertain", "pullup", pl(full_pullup, bar_y=0.20)),
        scenario("pullup_bent_start", "pullup", pl(lead_in(135, 1.5) + ease(30, 135, 40) + [40] * 9 + ease(36, 40, 172)
                                                   + [172] * 30, bar_y=0.20), bar_y=0.20),
        scenario("pullup_stalled_return", "pullup", pl(lead_in(172) + ease(36, 172, 40) + [40] * 9 + ease(30, 40, 125)
                                                       + [125] * 70, bar_y=0.20), bar_y=0.20),
    ]
    (FIX / "parity.json").write_text(json.dumps(sc, separators=(",", ":")))
    print("exported", len(sc), "scenarios;", sum(len(s["expected"]) for s in sc), "expected reps")


if __name__ == "__main__":
    main()
