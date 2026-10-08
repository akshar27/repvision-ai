// Port of backend/app/tracking/state_machine.py
import type { MachineConfig } from "@/types";

export type Phase = "REST" | "FLEXING" | "PEAK" | "EXTENDING";

export interface Cycle {
  startMs: number; startSignal: number; minSignal: number; minMs: number;
  startedFromRest: boolean; everArmed: boolean;
  reachedDepth: boolean; returnedToRest: boolean;
  endMs: number; endSignal: number;
  gaps: number; maxGapMs: number;
  reason: "returned" | "reversed" | "abandoned" | "flush" | "stalled";
  truncated: boolean; abandoned: boolean; leadMs: number;
}

export class RepStateMachine {
  phase: Phase = "REST";
  cycle: Cycle | null = null;
  armed = false;
  private window: [number, number][] = [];
  private belowSince: number | null = null;
  private restSince: number | null = null;
  private maxUp = NaN; private maxUpT = 0; private progressT = 0;
  private lastValidT: number | null = null;
  private lastSignal = NaN;
  private firstValidT: number | null = null;

  constructor(private cfg: MachineConfig) {}

  reset() {
    this.phase = "REST"; this.cycle = null; this.armed = false; this.window = [];
    this.belowSince = this.restSince = null; this.maxUp = NaN; this.maxUpT = this.progressT = 0;
    this.lastValidT = null; this.lastSignal = NaN; this.firstValidT = null;
  }

  private ref(): [number, number] {
    let bestT = 0, best = -Infinity;
    for (const [t, s] of this.window) if (s >= best) { best = s; bestT = t; }
    return [best, bestT];
  }
  private push(t: number, s: number) {
    this.window.push([t, s]);
    while (this.window.length && t - this.window[0][0] > this.cfg.ref_window_ms) this.window.shift();
  }
  private emit(c: Cycle, out: Cycle[]) {
    if (c.endMs - c.startMs >= this.cfg.min_rep_ms && c.minSignal <= this.cfg.partial_min_deg) out.push(c);
  }
  private begin(tStart: number, sStart: number, sNow: number, tNow: number, fromRest: boolean) {
    this.cycle = {
      startMs: tStart, startSignal: sStart, minSignal: sNow, minMs: tNow, startedFromRest: fromRest, everArmed: this.armed,
      reachedDepth: false, returnedToRest: false, endMs: 0, endSignal: NaN, gaps: 0, maxGapMs: 0, reason: "returned",
      truncated: false, abandoned: false, leadMs: this.firstValidT !== null ? tStart - this.firstValidT : 1e9,
    };
    this.phase = "FLEXING"; this.belowSince = null; this.restSince = null;
  }
  private toRest(t: number, s: number) {
    this.phase = "REST"; this.cycle = null; this.belowSince = this.restSince = null; this.window = []; this.push(t, s);
  }
  private abandon(out: Cycle[]) {
    const c = this.cycle;
    if (c) {
      c.endMs = this.lastValidT ?? c.startMs; c.endSignal = this.lastSignal; c.reason = "abandoned"; c.abandoned = true;
      this.emit(c, out);
    }
    this.phase = "REST"; this.cycle = null; this.armed = false; this.window = []; this.belowSince = this.restSince = null;
  }

  update(t: number, s: number | null): Cycle[] {
    const out: Cycle[] = [];
    const c = this.cfg;
    if (s === null || !isFinite(s)) {
      if (this.cycle && this.lastValidT !== null && t - this.lastValidT > c.abandon_ms) this.abandon(out);
      return out;
    }
    if (this.lastValidT !== null && this.cycle) {
      const gap = t - this.lastValidT;
      if (gap > c.abandon_ms) this.abandon(out);
      else if (gap > c.max_gap_ms) { this.cycle.gaps += 1; this.cycle.maxGapMs = Math.max(this.cycle.maxGapMs, gap); }
    }
    if (this.firstValidT === null) this.firstValidT = t;
    this.lastValidT = t; this.lastSignal = s;

    if (this.phase === "REST") {
      this.push(t, s);
      if (s >= c.rest_enter_deg) this.armed = true;
      const [ref, refT] = this.ref();
      if (s < ref - c.leave_delta_deg) this.begin(refT, ref, s, t, ref >= c.rest_enter_deg && this.armed);
      return out;
    }

    const cyc = this.cycle!;
    if (s < cyc.minSignal) { cyc.minSignal = s; cyc.minMs = t; }

    if (this.phase === "FLEXING") {
      if (s <= c.full_depth_deg) {
        if (this.belowSince === null) this.belowSince = t;
        if (t - this.belowSince >= c.min_phase_ms) { this.phase = "PEAK"; cyc.reachedDepth = true; }
      } else this.belowSince = null;
      if (this.phase === "FLEXING" && s > cyc.minSignal + c.reverse_delta_deg) {
        this.phase = "EXTENDING"; this.maxUp = s; this.maxUpT = t; this.progressT = t; this.restSince = null;
      } else if (this.phase === "FLEXING" && cyc.minSignal > c.partial_min_deg && s >= c.rest_enter_deg) {
        this.toRest(t, s);
        return out;
      }
    } else if (this.phase === "PEAK") {
      if (s > cyc.minSignal + c.reverse_delta_deg) {
        this.phase = "EXTENDING"; this.maxUp = s; this.maxUpT = t; this.progressT = t; this.restSince = null;
      }
    }

    if (this.phase === "EXTENDING") {
      if (s >= this.maxUp) {
        if (s > this.maxUp + 1.5) this.progressT = t;
        this.maxUp = s; this.maxUpT = t;
      }
      if (s >= c.rest_enter_deg) {
        if (this.restSince === null) this.restSince = t;
        if (t - this.restSince >= c.min_phase_ms) {
          cyc.returnedToRest = true; cyc.endMs = this.restSince; cyc.endSignal = s; cyc.reason = "returned";
          this.emit(cyc, out);
          this.toRest(t, s);
        }
      } else {
        this.restSince = null;
        if (t - this.progressT >= c.stall_ms) {
          cyc.endMs = this.maxUpT; cyc.endSignal = this.maxUp; cyc.reason = "stalled";
          this.emit(cyc, out);
          this.toRest(t, s);
        } else if (s < this.maxUp - c.reverse_delta_deg) {
          cyc.endMs = this.maxUpT; cyc.endSignal = this.maxUp; cyc.reason = "reversed";
          this.emit(cyc, out);
          this.begin(this.maxUpT, this.maxUp, s, t, false);
        }
      }
    }
    return out;
  }

  flush(t: number): Cycle[] {
    const out: Cycle[] = [];
    const cyc = this.cycle;
    if (cyc) {
      if (this.phase === "EXTENDING" && this.restSince !== null) {
        cyc.returnedToRest = true; cyc.endMs = this.restSince; cyc.reason = "returned"; cyc.endSignal = this.lastSignal;
      } else {
        cyc.endMs = this.lastValidT ?? t; cyc.endSignal = this.lastSignal; cyc.reason = "flush"; cyc.truncated = true;
      }
      this.emit(cyc, out);
    }
    this.phase = "REST"; this.cycle = null;
    return out;
  }
}
