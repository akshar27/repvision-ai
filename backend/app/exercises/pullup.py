from __future__ import annotations

import numpy as np

from ..models.schemas import num
from ..tracking import feedback as fb
from ..tracking.state_machine import Cycle, Phase
from ..vision import geometry as g
from ..vision.landmarks import LM, Pose
from .base import Evaluation, ExerciseAnalyzer, Features, FrameRec, clip01
from .config import PullupConfig

_SIDES = {
    "left": (LM.LEFT_SHOULDER, LM.LEFT_ELBOW, LM.LEFT_WRIST),
    "right": (LM.RIGHT_SHOULDER, LM.RIGHT_ELBOW, LM.RIGHT_WRIST),
}


class PullupAnalyzer(ExerciseAnalyzer):
    """Pull-up analysis.

    MediaPipe has no chin landmark and does not detect the bar. Top clearance is
    therefore only judged against a user-calibrated bar height using the mouth
    (conservative) or nose landmark as a proxy; otherwise it is "unverified".
    """
    name = "pullup"
    phase_names = {Phase.REST: "DEAD_HANG", Phase.FLEXING: "ASCENDING", Phase.PEAK: "TOP", Phase.EXTENDING: "DESCENDING"}
    cfg: PullupConfig

    def extract(self, pose: Pose) -> Features | None:
        thr = self.cfg.min_visibility
        elb, w, angles, draws, joints, sh_y, arm = [], [], {}, [], [], [], []
        for side, (sh, el, wr) in _SIDES.items():
            if pose.min_vis(sh, el, wr) < thr:
                continue
            a = g.angle_deg(pose.xy(sh), pose.xy(el), pose.xy(wr))
            if not np.isfinite(a):
                continue
            length = g.distance(pose.xy(sh), pose.xy(el)) + g.distance(pose.xy(el), pose.xy(wr))
            # hanging posture: wrists above shoulders (small tolerance for arm length)
            if pose.xy(wr)[1] > pose.xy(sh)[1] + 0.05 * length:
                continue
            elb.append(a)
            w.append(pose.min_vis(sh, el, wr))
            angles[f"elbow_{side}"] = a
            draws.append((sh, el, wr, a))
            joints += [sh, el, wr]
            sh_y.append(pose.xy(sh)[1])
            arm.append(length)
        if not elb:
            return None
        signal = g.weighted_mean(elb, w)
        angles["elbow"] = signal
        aux = {"shoulder_y": float(np.mean(sh_y)), "arm_len": float(np.mean(arm))}
        for key, idxs in (("nose_y", [LM.NOSE]), ("mouth_y", [LM.MOUTH_LEFT, LM.MOUTH_RIGHT])):
            if pose.min_vis(*idxs) >= thr:
                aux[key] = float(np.mean([pose.xy(i)[1] for i in idxs]))
        if "nose_y" in aux:
            joints.append(LM.NOSE)
        return Features(signal, float(np.mean(w)), angles, aux, draws, joints)

    def evaluate(self, cyc: Cycle, frames: list[FrameRec]) -> Evaluation:
        cfg, m = self.cfg, self.cfg.machine
        valid = [f for f in frames if f.valid]
        arm = float(np.median([f.aux["arm_len"] for f in valid])) if valid else float("nan")
        head = cfg.top_reference + "_y"
        start = valid[:3]
        sy0 = float(np.mean([f.aux["shoulder_y"] for f in start])) if start else float("nan")
        sy_min = min(f.aux["shoulder_y"] for f in valid) if valid else float("nan")
        travel = (sy0 - sy_min) / arm if arm > 1e-6 else float("nan")
        ny = [f.aux["nose_y"] for f in valid if "nose_y" in f.aux]
        head_travel = (ny[0] - min(ny)) / arm if ny and arm > 1e-6 else float("nan")

        # top clearance: only frames near the peak, only if the bar is calibrated and the head is visible
        clearance, margin = "unverified", float("nan")
        near_top = [f for f in valid if f.signal <= cyc.min_signal + 15 and head in f.aux]
        if cfg.bar_y is not None and near_top and arm > 1e-6:
            margin = (cfg.bar_y - min(f.aux[head] for f in near_top)) / arm
            clearance = "met" if margin >= cfg.clearance_margin_ratio else "not_met"

        rom_ok = cyc.reached_depth and bool(np.isfinite(travel)) and travel >= cfg.min_travel_ratio
        criteria: dict = {"started_dead_hang": cyc.started_from_rest, "rom_elbow_and_travel": rom_ok,
                          "returned_dead_hang": cyc.returned_to_rest, "top_clearance": clearance}
        items = []
        if not cyc.started_from_rest:
            items.append(fb.make("PULLUP_START_BENT"))
        if not rom_ok:
            items.append(fb.make("PULLUP_ROM", min_angle=cyc.min_signal, travel=0.0 if not np.isfinite(travel) else travel))
        if not cyc.returned_to_rest:
            items.append(fb.make("PULLUP_NO_HANG"))
        if clearance == "not_met":
            items.append(fb.make("PULLUP_CLEARANCE_NOT_MET"))
        elif clearance == "unverified":
            items.append(fb.make("PULLUP_CLEARANCE_UNVERIFIED"))

        basics = cyc.started_from_rest and rom_ok and cyc.returned_to_rest
        if not basics or clearance == "not_met":
            cls = "partial"
        elif clearance == "unverified" and cfg.require_bar_for_full:
            cls = "uncertain"
        else:
            cls = "full"
        if cls == "full":
            items.insert(0, fb.make("REP_FULL"))
        margins = [clip01(abs(m.full_depth_deg - cyc.min_signal) / 20.0)]
        if clearance in ("met", "not_met"):
            margins.append(clip01(abs(margin) / 0.15))
        return Evaluation(cls, items, criteria,
                          {"clearance_margin_ratio": num(margin), "head_travel_ratio": num(head_travel)},
                          {"shoulder_travel_ratio": num(travel)}, margins)
