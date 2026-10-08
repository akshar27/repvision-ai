from __future__ import annotations

import numpy as np

from ..models.schemas import num
from ..tracking import feedback as fb
from ..tracking.state_machine import Cycle, Phase
from ..vision import geometry as g
from ..vision.landmarks import LM, Pose
from .base import Evaluation, ExerciseAnalyzer, Features, FrameRec, clip01
from .config import PushupConfig

_SIDES = {
    "left": (LM.LEFT_SHOULDER, LM.LEFT_ELBOW, LM.LEFT_WRIST, LM.LEFT_HIP, LM.LEFT_ANKLE),
    "right": (LM.RIGHT_SHOULDER, LM.RIGHT_ELBOW, LM.RIGHT_WRIST, LM.RIGHT_HIP, LM.RIGHT_ANKLE),
}


class PushupAnalyzer(ExerciseAnalyzer):
    name = "pushup"
    phase_names = {Phase.REST: "TOP", Phase.FLEXING: "DESCENDING", Phase.PEAK: "BOTTOM", Phase.EXTENDING: "ASCENDING"}
    cfg: PushupConfig

    def extract(self, pose: Pose) -> Features | None:
        thr = self.cfg.min_visibility
        elb, w, angles, draws, joints = [], [], {}, [], []
        sh_y, hip_y, torso, dev, bodyang = [], [], [], [], []
        posture_ok = True
        for side, (sh, el, wr, hip, an) in _SIDES.items():
            if pose.min_vis(sh, el, wr) >= thr:
                a = g.angle_deg(pose.xy(sh), pose.xy(el), pose.xy(wr))
                if np.isfinite(a):
                    elb.append(a)
                    w.append(pose.min_vis(sh, el, wr))
                    angles[f"elbow_{side}"] = a
                    draws.append((sh, el, wr, a))
                    joints += [sh, el, wr]
            if pose.min_vis(sh, hip) >= thr:
                far = an if pose.vis(an) >= thr else hip      # sagging hips must not break the posture check
                ang = g.line_angle_from_horizontal_deg(pose.xy(sh), pose.xy(far))
                if np.isfinite(ang):
                    bodyang.append(ang)
                    sh_y.append(pose.xy(sh)[1])
                    hip_y.append(pose.xy(hip)[1])
                    torso.append(g.distance(pose.xy(sh), pose.xy(hip)))
                    joints += [sh, hip]
                    if pose.vis(an) >= thr:
                        d = g.line_deviation(pose.xy(hip), pose.xy(sh), pose.xy(an))
                        if np.isfinite(d):
                            dev.append(d)
                            joints.append(an)
        if not elb or not bodyang:
            return None
        if float(np.mean(bodyang)) > self.cfg.plank_max_angle_deg:
            return None     # not in a plank-like posture: do not count (e.g. standing or kneeling)
        signal = g.weighted_mean(elb, w)
        angles["elbow"] = signal
        aux = {"shoulder_y": float(np.mean(sh_y)), "hip_y": float(np.mean(hip_y)), "torso_len": float(np.mean(torso)),
               "body_angle": float(np.mean(bodyang))}
        aux["hip_rel_shoulder"] = (aux["hip_y"] - aux["shoulder_y"]) / aux["torso_len"] if aux["torso_len"] > 1e-6 else float("nan")
        if dev:
            aux["line_dev"] = float(np.mean(dev))
        return Features(signal, float(np.mean(w)), angles, aux, draws, joints)

    def evaluate(self, cyc: Cycle, frames: list[FrameRec]) -> Evaluation:
        cfg, m = self.cfg, self.cfg.machine
        valid = [f for f in frames if f.valid]
        torso = float(np.median([f.aux["torso_len"] for f in valid])) if valid else float("nan")
        sy = [f.aux["shoulder_y"] for f in valid]
        drop = (max(sy) - sy[0]) / torso if sy and torso > 1e-6 else float("nan")
        devs = [f.aux["line_dev"] for f in valid if "line_dev" in f.aux]
        max_sag = max(devs) if len(devs) >= 3 else float("nan")
        max_pike = -min(devs) if len(devs) >= 3 else float("nan")
        drop_ok = (not np.isfinite(drop)) or drop >= cfg.min_shoulder_drop_ratio

        criteria: dict = {"started_extended": cyc.started_from_rest, "depth_elbow_angle": cyc.reached_depth,
                          "shoulder_drop": bool(drop_ok), "returned_extended": cyc.returned_to_rest,
                          "alignment_measured": len(devs) >= 3}
        items = []
        if not cyc.started_from_rest:
            items.append(fb.make("PUSHUP_START_NOT_EXTENDED"))
        if not cyc.reached_depth:
            items.append(fb.make("PUSHUP_DEPTH", min_angle=cyc.min_signal, target=m.full_depth_deg))
        elif not drop_ok:
            items.append(fb.make("PUSHUP_SHOULDER"))
        if not cyc.returned_to_rest:
            items.append(fb.make("PUSHUP_NO_LOCKOUT"))
        full = cyc.started_from_rest and cyc.reached_depth and drop_ok and cyc.returned_to_rest
        if np.isfinite(max_sag) and max_sag > cfg.sag_warn_ratio:
            items.append(fb.make("PUSHUP_SAG", dev=max_sag))
        if np.isfinite(max_pike) and max_pike > cfg.pike_warn_ratio:
            items.append(fb.make("PUSHUP_PIKE", dev=max_pike))
        if full:
            items.insert(0, fb.make("REP_FULL"))
        return Evaluation("full" if full else "partial", items, criteria,
                          {"max_hip_sag_ratio": num(max_sag), "max_hip_pike_ratio": num(max_pike)},
                          {"shoulder_drop_ratio": num(drop)}, [clip01(abs(m.full_depth_deg - cyc.min_signal) / 20.0)])
