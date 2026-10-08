// Port of backend/app/exercises/*.py. Same rules, same thresholds (from generated configs).
import { LM } from "@/lib/engine/landmarks";
import type { ExerciseConfig, ExerciseId, RepEvent, FeedbackItem } from "@/types";
import {
  Pose, LandmarkSmoother, angleDeg, distance, lineAngleFromHorizontalDeg, lineDeviation, mean, median, minVis,
  torsoInclinationDeg, weightedMean, xy,
} from "./geometry";
import { makeFeedback as fb } from "./feedback";
import { Cycle, RepStateMachine } from "./machine";

type Aux = Record<string, number>;
export interface Features {
  signal: number; confidence: number; angles: Record<string, number>; aux: Aux;
  drawAngles: [number, number, number, number][]; joints: number[];
}
interface FrameRec { t: number; valid: boolean; signal: number; confidence: number; aux: Aux }
interface Evaluation {
  classification: "full" | "partial" | "uncertain"; feedback: FeedbackItem[];
  criteria: Record<string, boolean | string | null>; measurements: Record<string, number | null>;
  rom: Record<string, number | null>; margins: number[];
}
export interface FrameResult {
  tMs: number; status: "ok" | "no_pose" | "low_confidence"; phase: string; signal: number; angles: Record<string, number>;
  confidence: number; newReps: RepEvent[]; pose: Pose | null; messages: string[];
  drawAngles: [number, number, number, number][]; joints: number[];
}

const num = (x: number | null | undefined, nd = 3): number | null =>
  x == null || !isFinite(x) ? null : Math.round(x * 10 ** nd) / 10 ** nd;
const clip01 = (x: number) => Math.max(0, Math.min(1, x));
const fin = (x: number) => isFinite(x);

const PHASES: Record<ExerciseId, Record<string, string>> = {
  squat: { REST: "STANDING", FLEXING: "DESCENDING", PEAK: "BOTTOM", EXTENDING: "ASCENDING" },
  pushup: { REST: "TOP", FLEXING: "DESCENDING", PEAK: "BOTTOM", EXTENDING: "ASCENDING" },
  pullup: { REST: "DEAD_HANG", FLEXING: "ASCENDING", PEAK: "TOP", EXTENDING: "DESCENDING" },
};

export abstract class Analyzer {
  machine: RepStateMachine;
  reps: RepEvent[] = [];
  private smoother: LandmarkSmoother;
  private frames: FrameRec[] = [];
  private prev: [number, number] | null = null;
  private rejects = 0;

  constructor(public cfg: ExerciseConfig, public name: ExerciseId) {
    this.machine = new RepStateMachine(cfg.machine);
    this.smoother = new LandmarkSmoother(cfg.smoothing_tau_ms);
  }
  abstract extract(p: Pose): Features | null;
  abstract evaluate(c: Cycle, frames: FrameRec[]): Evaluation;

  reset() { this.machine.reset(); this.smoother.reset(); this.reps = []; this.frames = []; this.prev = null; this.rejects = 0; }
  get phaseName() { return PHASES[this.name][this.machine.phase]; }
  get summary() {
    const s = { total: this.reps.length, full: 0, partial: 0, uncertain: 0 };
    for (const r of this.reps) s[r.classification] += 1;
    return s;
  }

  update(pose: Pose | null, t: number): FrameResult {
    let smoothed: Pose | null = null;
    let feats: Features | null = null;
    let status: FrameResult["status"] = "no_pose";
    if (pose && !pose.x.some(Number.isNaN) && !pose.y.some(Number.isNaN)) {
      smoothed = this.smoother.update(pose);
      feats = this.extract(smoothed);
      status = feats ? "ok" : "low_confidence";
    } else if (!pose) this.smoother.reset();

    if (feats && !this.plausible(t, feats.signal)) { feats = null; status = "low_confidence"; }
    const sig = feats ? feats.signal : NaN;
    this.frames.push({ t, valid: !!feats, signal: sig, confidence: feats?.confidence ?? 0, aux: feats ? { ...feats.aux } : {} });
    const newReps = this.machine.update(t, feats ? sig : null).map((c) => this.finalize(c));
    this.trim(t);
    const messages: string[] = [];
    if (status === "no_pose") messages.push("No person detected");
    else if (status === "low_confidence") messages.push("Body not clearly visible – check camera position");
    return { tMs: t, status, phase: this.phaseName, signal: sig, angles: feats ? { ...feats.angles } : {},
      confidence: feats?.confidence ?? 0, newReps, pose: smoothed, messages,
      drawAngles: feats?.drawAngles ?? [], joints: feats?.joints ?? [] };
  }

  finish(t: number): RepEvent[] { return this.machine.flush(t).map((c) => this.finalize(c)); }

  private plausible(t: number, s: number) {
    if (!fin(s)) return false;
    if (this.prev && t > this.prev[0]) {
      const dps = Math.abs(s - this.prev[1]) / ((t - this.prev[0]) / 1000);
      if (dps > this.cfg.max_signal_speed_dps && this.rejects < 5) { this.rejects += 1; return false; }
    }
    this.prev = [t, s]; this.rejects = 0;
    return true;
  }
  private trim(t: number) {
    let keep = t - 4000;
    if (this.machine.cycle) keep = Math.min(keep, this.machine.cycle.startMs - 200);
    let i = 0;
    while (i < this.frames.length && this.frames[i].t < keep) i++;
    if (i) this.frames.splice(0, i);
  }

  private finalize(c: Cycle): RepEvent {
    const frames = this.frames.filter((f) => f.t >= c.startMs && f.t <= c.endMs);
    const valid = frames.filter((f) => f.valid);
    const coverage = frames.length ? valid.length / frames.length : 0;
    const conf = valid.length ? mean(valid.map((f) => f.confidence)) : 0;
    const measConf = conf * coverage;
    let ev: Evaluation;
    const uncertain = (code: string): Evaluation => ({ classification: "uncertain", feedback: [fb(code)], criteria: { validated: false },
      measurements: {}, rom: {}, margins: [0] });
    if (c.abandoned || c.gaps > 0 || coverage < this.cfg.min_rep_coverage) ev = uncertain(c.abandoned || c.gaps > 0 ? "TRACKING_GAP" : "LOW_VISIBILITY");
    else if (c.truncated) ev = uncertain("VIDEO_ENDED");
    else if (!c.startedFromRest && !c.everArmed && c.leadMs < this.cfg.machine.start_lead_ms) ev = uncertain("INVALID_START");
    else ev = this.evaluate(c, frames);

    ev.measurements = { ...ev.measurements, start_angle: num(c.startSignal, 1), min_angle: num(c.minSignal, 1), end_angle: num(c.endSignal, 1), coverage: num(coverage) };
    if (!("angle_rom_deg" in ev.rom)) ev.rom.angle_rom_deg = num(c.startSignal - c.minSignal, 1);
    const margin = ev.margins.length ? Math.min(...ev.margins) : 0;
    let cls = measConf * (0.5 + 0.5 * clip01(margin));
    if (ev.classification === "uncertain") cls = Math.min(cls, 0.4);
    const rep: RepEvent = {
      index: this.reps.length + 1, start_ms: Math.round(c.startMs * 10) / 10, end_ms: Math.round(c.endMs * 10) / 10,
      duration_ms: Math.round((c.endMs - c.startMs) * 10) / 10, classification: ev.classification,
      measurements: ev.measurements, rom: ev.rom, criteria: ev.criteria, feedback: ev.feedback,
      measurement_confidence: Math.round(measConf * 1000) / 1000, classification_confidence: Math.round(cls * 1000) / 1000,
    };
    this.reps.push(rep);
    return rep;
  }
}

// ------------------------------------------------------------------ squat
const SQ_SIDES = {
  left: [LM.LEFT_SHOULDER, LM.LEFT_HIP, LM.LEFT_KNEE, LM.LEFT_ANKLE],
  right: [LM.RIGHT_SHOULDER, LM.RIGHT_HIP, LM.RIGHT_KNEE, LM.RIGHT_ANKLE],
} as const;

export class SquatAnalyzer extends Analyzer {
  constructor(cfg: ExerciseConfig) { super(cfg, "squat"); }
  extract(p: Pose): Features | null {
    const thr = this.cfg.min_visibility;
    const knee: number[] = [], w: number[] = [], hipY: number[] = [], kneeY: number[] = [], thigh: number[] = [], torso: number[] = [], hipAng: number[] = [];
    const angles: Record<string, number> = {}, draws: Features["drawAngles"] = [], joints: number[] = [];
    for (const [side, [sh, hip, kn, an]] of Object.entries(SQ_SIDES)) {
      const v = minVis(p, hip, kn, an);
      if (v < thr) continue;
      const a = angleDeg(xy(p, hip), xy(p, kn), xy(p, an));
      if (!fin(a)) continue;
      knee.push(a); w.push(v); angles[`knee_${side}`] = a; draws.push([hip, kn, an, a]); joints.push(hip, kn, an);
      hipY.push(xy(p, hip)[1]); kneeY.push(xy(p, kn)[1]); thigh.push(distance(xy(p, hip), xy(p, kn)));
      if (p.vis[sh] >= thr) {
        torso.push(torsoInclinationDeg(xy(p, sh), xy(p, hip)));
        const ha = angleDeg(xy(p, sh), xy(p, hip), xy(p, kn));
        if (fin(ha)) { hipAng.push(ha); angles[`hip_${side}`] = ha; draws.push([sh, hip, kn, ha]); joints.push(sh); }
      }
    }
    if (!knee.length) return null;
    const signal = weightedMean(knee, w);
    const aux: Aux = { hip_y: mean(hipY), knee_y: mean(kneeY), thigh_len: mean(thigh) };
    aux.hip_rel_knee = aux.thigh_len > 1e-6 ? (aux.hip_y - aux.knee_y) / aux.thigh_len : NaN;
    if (torso.length) aux.torso_incl = mean(torso);
    if (hipAng.length) aux.hip_angle = mean(hipAng);
    angles.knee = signal;
    return { signal, confidence: mean(w), angles, aux, drawAngles: draws, joints };
  }
  evaluate(c: Cycle, frames: FrameRec[]): Evaluation {
    const cfg = this.cfg, m = cfg.machine;
    const valid = frames.filter((f) => f.valid);
    const hrk = valid.map((f) => f.aux.hip_rel_knee).filter(fin);
    const incl = valid.filter((f) => "torso_incl" in f.aux).map((f) => f.aux.torso_incl);
    const maxHrk = hrk.length ? Math.max(...hrk) : NaN;
    const lean = incl.length ? Math.max(...incl) : NaN;
    const scale = valid.length ? median(valid.map((f) => f.aux.thigh_len)) : NaN;
    const hips = valid.map((f) => f.aux.hip_y);
    const hipDrop = hips.length && scale > 1e-6 ? (Math.max(...hips) - hips[0]) / scale : NaN;
    const depthKnee = c.reachedDepth;
    const depthHip = fin(maxHrk) && maxHrk >= (cfg.hip_below_knee_ratio ?? 0);
    const depthOk = depthKnee && (depthHip || !cfg.require_hip_below_knee);
    const items: FeedbackItem[] = [];
    if (!c.startedFromRest) items.push(fb("SQUAT_START_NOT_STANDING"));
    if (!depthKnee) items.push(fb("SQUAT_DEPTH", { min_angle: c.minSignal, target: m.full_depth_deg }));
    else if (!depthOk) items.push(fb("SQUAT_HIP_ABOVE_KNEE"));
    if (!c.returnedToRest) items.push(fb("SQUAT_NO_STAND"));
    const full = c.startedFromRest && depthOk && c.returnedToRest;
    if (fin(lean) && lean > (cfg.torso_lean_warn_deg ?? 60)) items.push(fb("SQUAT_TORSO", { lean }));
    if (full) items.unshift(fb("REP_FULL"));
    return { classification: full ? "full" : "partial", feedback: items,
      criteria: { started_standing: c.startedFromRest, depth_knee_angle: depthKnee,
        depth_hip_below_knee: cfg.require_hip_below_knee ? depthHip : null, returned_standing: c.returnedToRest },
      measurements: { max_hip_below_knee_ratio: num(maxHrk), max_torso_inclination_deg: num(lean, 1) },
      rom: { hip_drop_ratio: num(hipDrop) }, margins: [clip01(Math.abs(m.full_depth_deg - c.minSignal) / 20)] };
  }
}

// ------------------------------------------------------------------ push-up
const PU_SIDES = {
  left: [LM.LEFT_SHOULDER, LM.LEFT_ELBOW, LM.LEFT_WRIST, LM.LEFT_HIP, LM.LEFT_ANKLE],
  right: [LM.RIGHT_SHOULDER, LM.RIGHT_ELBOW, LM.RIGHT_WRIST, LM.RIGHT_HIP, LM.RIGHT_ANKLE],
} as const;

export class PushupAnalyzer extends Analyzer {
  constructor(cfg: ExerciseConfig) { super(cfg, "pushup"); }
  extract(p: Pose): Features | null {
    const thr = this.cfg.min_visibility;
    const elb: number[] = [], w: number[] = [], shY: number[] = [], hipY: number[] = [], torso: number[] = [], dev: number[] = [], body: number[] = [];
    const angles: Record<string, number> = {}, draws: Features["drawAngles"] = [], joints: number[] = [];
    for (const [side, [sh, el, wr, hip, an]] of Object.entries(PU_SIDES)) {
      if (minVis(p, sh, el, wr) >= thr) {
        const a = angleDeg(xy(p, sh), xy(p, el), xy(p, wr));
        if (fin(a)) { elb.push(a); w.push(minVis(p, sh, el, wr)); angles[`elbow_${side}`] = a; draws.push([sh, el, wr, a]); joints.push(sh, el, wr); }
      }
      if (minVis(p, sh, hip) >= thr) {
        const far = p.vis[an] >= thr ? an : hip;
        const ang = lineAngleFromHorizontalDeg(xy(p, sh), xy(p, far));
        if (fin(ang)) {
          body.push(ang); shY.push(xy(p, sh)[1]); hipY.push(xy(p, hip)[1]); torso.push(distance(xy(p, sh), xy(p, hip))); joints.push(sh, hip);
          if (p.vis[an] >= thr) {
            const d = lineDeviation(xy(p, hip), xy(p, sh), xy(p, an));
            if (fin(d)) { dev.push(d); joints.push(an); }
          }
        }
      }
    }
    if (!elb.length || !body.length) return null;
    if (mean(body) > this.cfg.plank_max_angle_deg!) return null;
    const signal = weightedMean(elb, w);
    angles.elbow = signal;
    const aux: Aux = { shoulder_y: mean(shY), hip_y: mean(hipY), torso_len: mean(torso), body_angle: mean(body) };
    aux.hip_rel_shoulder = aux.torso_len > 1e-6 ? (aux.hip_y - aux.shoulder_y) / aux.torso_len : NaN;
    if (dev.length) aux.line_dev = mean(dev);
    return { signal, confidence: mean(w), angles, aux, drawAngles: draws, joints };
  }
  evaluate(c: Cycle, frames: FrameRec[]): Evaluation {
    const cfg = this.cfg, m = cfg.machine;
    const valid = frames.filter((f) => f.valid);
    const torso = valid.length ? median(valid.map((f) => f.aux.torso_len)) : NaN;
    const sy = valid.map((f) => f.aux.shoulder_y);
    const drop = sy.length && torso > 1e-6 ? (Math.max(...sy) - sy[0]) / torso : NaN;
    const devs = valid.filter((f) => "line_dev" in f.aux).map((f) => f.aux.line_dev);
    const maxSag = devs.length >= 3 ? Math.max(...devs) : NaN;
    const maxPike = devs.length >= 3 ? -Math.min(...devs) : NaN;
    const dropOk = !fin(drop) || drop >= cfg.min_shoulder_drop_ratio!;
    const items: FeedbackItem[] = [];
    if (!c.startedFromRest) items.push(fb("PUSHUP_START_NOT_EXTENDED"));
    if (!c.reachedDepth) items.push(fb("PUSHUP_DEPTH", { min_angle: c.minSignal, target: m.full_depth_deg }));
    else if (!dropOk) items.push(fb("PUSHUP_SHOULDER"));
    if (!c.returnedToRest) items.push(fb("PUSHUP_NO_LOCKOUT"));
    const full = c.startedFromRest && c.reachedDepth && dropOk && c.returnedToRest;
    if (fin(maxSag) && maxSag > cfg.sag_warn_ratio!) items.push(fb("PUSHUP_SAG", { dev: maxSag }));
    if (fin(maxPike) && maxPike > cfg.pike_warn_ratio!) items.push(fb("PUSHUP_PIKE", { dev: maxPike }));
    if (full) items.unshift(fb("REP_FULL"));
    return { classification: full ? "full" : "partial", feedback: items,
      criteria: { started_extended: c.startedFromRest, depth_elbow_angle: c.reachedDepth, shoulder_drop: dropOk,
        returned_extended: c.returnedToRest, alignment_measured: devs.length >= 3 },
      measurements: { max_hip_sag_ratio: num(maxSag), max_hip_pike_ratio: num(maxPike) },
      rom: { shoulder_drop_ratio: num(drop) }, margins: [clip01(Math.abs(m.full_depth_deg - c.minSignal) / 20)] };
  }
}

// ------------------------------------------------------------------ pull-up
const PL_SIDES = {
  left: [LM.LEFT_SHOULDER, LM.LEFT_ELBOW, LM.LEFT_WRIST],
  right: [LM.RIGHT_SHOULDER, LM.RIGHT_ELBOW, LM.RIGHT_WRIST],
} as const;

export class PullupAnalyzer extends Analyzer {
  constructor(cfg: ExerciseConfig) { super(cfg, "pullup"); }
  extract(p: Pose): Features | null {
    const thr = this.cfg.min_visibility;
    const elb: number[] = [], w: number[] = [], shY: number[] = [], arm: number[] = [];
    const angles: Record<string, number> = {}, draws: Features["drawAngles"] = [], joints: number[] = [];
    for (const [side, [sh, el, wr]] of Object.entries(PL_SIDES)) {
      if (minVis(p, sh, el, wr) < thr) continue;
      const a = angleDeg(xy(p, sh), xy(p, el), xy(p, wr));
      if (!fin(a)) continue;
      const length = distance(xy(p, sh), xy(p, el)) + distance(xy(p, el), xy(p, wr));
      if (xy(p, wr)[1] > xy(p, sh)[1] + 0.05 * length) continue;
      elb.push(a); w.push(minVis(p, sh, el, wr)); angles[`elbow_${side}`] = a; draws.push([sh, el, wr, a]); joints.push(sh, el, wr);
      shY.push(xy(p, sh)[1]); arm.push(length);
    }
    if (!elb.length) return null;
    const signal = weightedMean(elb, w);
    angles.elbow = signal;
    const aux: Aux = { shoulder_y: mean(shY), arm_len: mean(arm) };
    if (minVis(p, LM.NOSE) >= thr) aux.nose_y = xy(p, LM.NOSE)[1];
    if (minVis(p, LM.MOUTH_LEFT, LM.MOUTH_RIGHT) >= thr) aux.mouth_y = mean([xy(p, LM.MOUTH_LEFT)[1], xy(p, LM.MOUTH_RIGHT)[1]]);
    if ("nose_y" in aux) joints.push(LM.NOSE);
    return { signal, confidence: mean(w), angles, aux, drawAngles: draws, joints };
  }
  evaluate(c: Cycle, frames: FrameRec[]): Evaluation {
    const cfg = this.cfg, m = cfg.machine;
    const valid = frames.filter((f) => f.valid);
    const arm = valid.length ? median(valid.map((f) => f.aux.arm_len)) : NaN;
    const head = `${cfg.top_reference ?? "mouth"}_y`;
    const start = valid.slice(0, 3);
    const sy0 = start.length ? mean(start.map((f) => f.aux.shoulder_y)) : NaN;
    const syMin = valid.length ? Math.min(...valid.map((f) => f.aux.shoulder_y)) : NaN;
    const travel = arm > 1e-6 ? (sy0 - syMin) / arm : NaN;
    const ny = valid.filter((f) => "nose_y" in f.aux).map((f) => f.aux.nose_y);
    const headTravel = ny.length && arm > 1e-6 ? (ny[0] - Math.min(...ny)) / arm : NaN;

    let clearance = "unverified", margin = NaN;
    const nearTop = valid.filter((f) => f.signal <= c.minSignal + 15 && head in f.aux);
    if (cfg.bar_y != null && nearTop.length && arm > 1e-6) {
      margin = (cfg.bar_y - Math.min(...nearTop.map((f) => f.aux[head]))) / arm;
      clearance = margin >= cfg.clearance_margin_ratio! ? "met" : "not_met";
    }
    const romOk = c.reachedDepth && fin(travel) && travel >= cfg.min_travel_ratio!;
    const items: FeedbackItem[] = [];
    if (!c.startedFromRest) items.push(fb("PULLUP_START_BENT"));
    if (!romOk) items.push(fb("PULLUP_ROM", { min_angle: c.minSignal, travel: fin(travel) ? travel : 0 }));
    if (!c.returnedToRest) items.push(fb("PULLUP_NO_HANG"));
    if (clearance === "not_met") items.push(fb("PULLUP_CLEARANCE_NOT_MET"));
    else if (clearance === "unverified") items.push(fb("PULLUP_CLEARANCE_UNVERIFIED"));
    const basics = c.startedFromRest && romOk && c.returnedToRest;
    let cls: Evaluation["classification"];
    if (!basics || clearance === "not_met") cls = "partial";
    else if (clearance === "unverified" && cfg.require_bar_for_full) cls = "uncertain";
    else cls = "full";
    if (cls === "full") items.unshift(fb("REP_FULL"));
    const margins = [clip01(Math.abs(m.full_depth_deg - c.minSignal) / 20)];
    if (clearance === "met" || clearance === "not_met") margins.push(clip01(Math.abs(margin) / 0.15));
    return { classification: cls, feedback: items,
      criteria: { started_dead_hang: c.startedFromRest, rom_elbow_and_travel: romOk, returned_dead_hang: c.returnedToRest, top_clearance: clearance },
      measurements: { clearance_margin_ratio: num(margin), head_travel_ratio: num(headTravel) },
      rom: { shoulder_travel_ratio: num(travel) }, margins };
  }
}

export function createAnalyzer(cfg: ExerciseConfig): Analyzer {
  switch (cfg.exercise) {
    case "squat": return new SquatAnalyzer(cfg);
    case "pushup": return new PushupAnalyzer(cfg);
    default: return new PullupAnalyzer(cfg);
  }
}
