// Replays synthetic landmark scenarios (exported from the Python engine by scripts/export_shared.py)
// through the TypeScript engine used by webcam mode and compares with what the Python engine produced.
// This establishes rule parity between the two implementations. It is NOT a pose-accuracy test.
import { describe, expect, it } from "vitest";
import fixtures from "./fixtures/parity.json";
import { createAnalyzer } from "@/lib/engine";
import { buildConfig, parseCalibration, configFromCalibration, CalibrationError } from "@/lib/engine/config";
import { makeFeedback } from "@/lib/engine/feedback";
import type { Pose } from "@/lib/engine";
import type { ExerciseConfig } from "@/types";

interface Scenario {
  name: string; exercise: string; config: ExerciseConfig; aspect: number;
  frames: { t: number; pose: { x: number[]; y: number[]; vis: number[] } | null }[];
  expected: { classification: string; start_ms: number; end_ms: number; min_angle: number; codes: string[]; measurement_confidence: number; top_clearance: string | null }[];
}

describe("TS engine matches Python engine", () => {
  for (const sc of fixtures as unknown as Scenario[]) {
    it(sc.name, () => {
      const a = createAnalyzer(sc.config);
      let last = 0;
      for (const f of sc.frames) {
        const pose: Pose | null = f.pose ? { ...f.pose, t: f.t, aspect: sc.aspect } : null;
        a.update(pose, f.t);
        last = f.t;
      }
      a.finish(last);
      const got = a.reps;
      expect(got.map((r) => r.classification)).toEqual(sc.expected.map((e) => e.classification));
      got.forEach((r, i) => {
        const e = sc.expected[i];
        expect(Math.abs(r.start_ms - e.start_ms)).toBeLessThan(1);
        expect(Math.abs(r.end_ms - e.end_ms)).toBeLessThan(1);
        expect(Math.abs((r.measurements.min_angle ?? 0) - e.min_angle)).toBeLessThan(0.3);
        expect(r.feedback.map((f) => f.code)).toEqual(e.codes);
        expect(Math.abs(r.measurement_confidence - e.measurement_confidence)).toBeLessThan(0.01);
        expect(r.criteria.top_clearance ?? null).toEqual(e.top_clearance);
      });
    });
  }
});

describe("config + feedback helpers", () => {
  it("applies presets and overrides like the backend", () => {
    expect(buildConfig("squat", "strict").machine.full_depth_deg).toBe(90);
    expect(buildConfig("squat", "standard", { "machine.full_depth_deg": 95 }).machine.full_depth_deg).toBe(95);
    expect(buildConfig("pullup", "standard", {}, 0.2).bar_y).toBe(0.2);
  });
  it("rejects invalid calibrations", () => {
    expect(() => buildConfig("squat", "standard", { "machine.full_depth_deg": 170 })).toThrow(CalibrationError);
    expect(() => buildConfig("squat", "standard", { "machine.bogus": 1 })).toThrow(CalibrationError);
    expect(() => buildConfig("squat", "standard", {}, 0.2)).toThrow(CalibrationError);
    expect(() => configFromCalibration("squat", parseCalibration('{"exercise":"pushup"}'))).toThrow(CalibrationError);
    expect(() => parseCalibration("{nope")).toThrow(CalibrationError);
  });
  it("formats python-style templates", () => {
    expect(makeFeedback("SQUAT_DEPTH", { min_angle: 103.4, target: 100 }).message).toContain("knee angle 103°");
    expect(makeFeedback("PUSHUP_SAG", { dev: 0.153 }).message).toContain("15%");
  });
});
