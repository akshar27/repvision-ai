from __future__ import annotations

import numpy as np

from ..tracking import feedback as fb
from ..tracking.state_machine import Cycle, Phase
from ..vision import geometry as g
from ..vision.landmarks import LM, Pose
from .base import Evaluation, ExerciseAnalyzer, Features, FrameRec, clip01
from .config import SquatConfig
from ..models.schemas import num

_SIDES = {
    "left": (LM.LEFT_SHOULDER, LM.LEFT_HIP, LM.LEFT_KNEE, LM.LEFT_ANKLE),
    "right": (LM.RIGHT_SHOULDER, LM.RIGHT_HIP, LM.RIGHT_KNEE, LM.RIGHT_ANKLE),
}


class SquatAnalyzer(ExerciseAnalyzer):
    name = "squat"
    phase_names = {Phase.REST: "STANDING", Phase.FLEXING: "DESCENDING", Phase.PEAK: "BOTTOM", Phase.EXTENDING: "ASCENDING"}
    cfg: SquatConfig

    def extract(self, pose: Pose) -> Features | None:
        thr = self.cfg.min_visibility
        knee, weights, angles, draws, joints = [], [], {}, [], []
        hip_y, knee_y, thigh, torso, hip_ang = [], [], [], [], []
        for side, (sh, hip, kn, an) in _SIDES.items():
            v = pose.min_vis(hip, kn, an)
            if v < thr:
                continue
            a = g.angle_deg(pose.xy(hip), pose.xy(kn), pose.xy(an))
            if not np.isfinite(a):
                continue
            knee.append(a)
            weights.append(v)
            angles[f"knee_{side}"] = a
            draws.append((hip, kn, an, a))
            joints += [hip, kn, an]
            hip_y.append(pose.xy(hip)[1])
            knee_y.append(pose.xy(kn)[1])
            thigh.append(g.distance(pose.xy(hip), pose.xy(kn)))
            if pose.vis(sh) >= thr:
                torso.append(g.torso_inclination_deg(pose.xy(sh), pose.xy(hip)))
                ha = g.angle_deg(pose.xy(sh), pose.xy(hip), pose.xy(kn))
                if np.isfinite(ha):
                    hip_ang.append(ha)
                    angles[f"hip_{side}"] = ha
                    draws.append((sh, hip, kn, ha))
                    joints.append(sh)
        if not knee:
            return None
        signal = g.weighted_mean(knee, weights)
        aux = {"hip_y": float(np.mean(hip_y)), "knee_y": float(np.mean(knee_y)), "thigh_len": float(np.mean(thigh))}
        aux["hip_rel_knee"] = (aux["hip_y"] - aux["knee_y"]) / aux["thigh_len"] if aux["thigh_len"] > 1e-6 else float("nan")
        if torso:
            aux["torso_incl"] = float(np.mean(torso))
        if hip_ang:
            aux["hip_angle"] = float(np.mean(hip_ang))
        angles["knee"] = signal
        return Features(signal, float(np.mean(weights)), angles, aux, draws, joints)

    def evaluate(self, cyc: Cycle, frames: list[FrameRec]) -> Evaluation:
        cfg, m = self.cfg, self.cfg.machine
        valid = [f for f in frames if f.valid]
        hrk = [f.aux["hip_rel_knee"] for f in valid if np.isfinite(f.aux.get("hip_rel_knee", np.nan))]
        incl = [f.aux["torso_incl"] for f in valid if "torso_incl" in f.aux]
        hips = [f.aux["hip_y"] for f in valid]
        max_hrk = max(hrk) if hrk else float("nan")
        lean = max(incl) if incl else float("nan")
        scale = float(np.median([f.aux["thigh_len"] for f in valid])) if valid else float("nan")
        hip_drop = (max(hips) - hips[0]) / scale if hips and scale > 1e-6 else float("nan")

        depth_knee = cyc.reached_depth
        depth_hip = bool(np.isfinite(max_hrk) and max_hrk >= cfg.hip_below_knee_ratio)
        depth_ok = depth_knee and (depth_hip or not cfg.require_hip_below_knee)
        criteria: dict = {"started_standing": cyc.started_from_rest, "depth_knee_angle": depth_knee,
                          "depth_hip_below_knee": depth_hip if cfg.require_hip_below_knee else None,
                          "returned_standing": cyc.returned_to_rest}
        items = []
        if not cyc.started_from_rest:
            items.append(fb.make("SQUAT_START_NOT_STANDING"))
        if not depth_knee:
            items.append(fb.make("SQUAT_DEPTH", min_angle=cyc.min_signal, target=m.full_depth_deg))
        elif not depth_ok:
            items.append(fb.make("SQUAT_HIP_ABOVE_KNEE"))
        if not cyc.returned_to_rest:
            items.append(fb.make("SQUAT_NO_STAND"))
        full = cyc.started_from_rest and depth_ok and cyc.returned_to_rest
        if np.isfinite(lean) and lean > cfg.torso_lean_warn_deg:
            items.append(fb.make("SQUAT_TORSO", lean=lean))
        if full:
            items.insert(0, fb.make("REP_FULL"))
        margins = [clip01(abs(m.full_depth_deg - cyc.min_signal) / 20.0)]
        return Evaluation("full" if full else "partial", items, criteria,
                          {"max_hip_below_knee_ratio": num(max_hrk), "max_torso_inclination_deg": num(lean, 1)},
                          {"hip_drop_ratio": num(hip_drop)}, margins)
