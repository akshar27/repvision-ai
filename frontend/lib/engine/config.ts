import configs from "@/lib/generated/exercise-configs.json";
import type { Calibration, ExerciseConfig, ExerciseId, Preset } from "@/types";

export const EXERCISE_IDS: ExerciseId[] = ["squat", "pushup", "pullup"];
export const PRESETS: Preset[] = ["lenient", "standard", "strict"];

export class CalibrationError extends Error {}

type Dict = Record<string, unknown>;

function setDotted(obj: Dict, key: string, value: unknown) {
  const parts = key.split(".");
  let cur = obj;
  for (const p of parts.slice(0, -1)) cur = (cur[p] ??= {}) as Dict;
  const last = parts[parts.length - 1];
  if (!(last in cur)) throw new CalibrationError(`Unknown setting '${key}'.`);
  cur[last] = value;
}

/** Preset config (generated from the Python source of truth) + user overrides. */
export function buildConfig(exercise: ExerciseId, preset: Preset = "standard", overrides: Calibration["overrides"] = {}, barY?: number | null): ExerciseConfig {
  const base = structuredClone((configs as unknown as Record<string, Record<string, ExerciseConfig>>)[exercise][preset]);
  for (const [k, v] of Object.entries(overrides)) setDotted(base as unknown as Dict, k, v);
  if (barY != null) {
    if (exercise !== "pullup") throw new CalibrationError("bar_y only applies to pull-ups.");
    base.bar_y = barY;
  }
  const m = base.machine;
  if (!(m.full_depth_deg < m.partial_min_deg && m.partial_min_deg < m.rest_enter_deg))
    throw new CalibrationError("Require full depth < partial minimum < rest threshold.");
  base.preset = preset;
  return base;
}

export function configFromCalibration(exercise: ExerciseId, cal: Calibration | null, preset?: Preset): ExerciseConfig {
  if (!cal) return buildConfig(exercise, preset ?? "standard");
  if (cal.exercise && cal.exercise !== exercise) throw new CalibrationError(`Calibration was saved for '${cal.exercise}', not '${exercise}'.`);
  return buildConfig(exercise, preset ?? cal.preset, cal.overrides, cal.bar_y);
}

export function parseCalibration(text: string): Calibration {
  let j: Dict;
  try { j = JSON.parse(text); } catch { throw new CalibrationError("Not valid JSON."); }
  const allowed = new Set(["exercise", "preset", "overrides", "bar_y", "notes"]);
  for (const k of Object.keys(j)) if (!allowed.has(k)) throw new CalibrationError(`Unknown field '${k}'.`);
  const preset = (j.preset ?? "standard") as Preset;
  if (!PRESETS.includes(preset)) throw new CalibrationError(`Unknown preset '${preset}'.`);
  return { exercise: (j.exercise as ExerciseId) ?? null, preset, overrides: (j.overrides as Calibration["overrides"]) ?? {},
    bar_y: (j.bar_y as number | null) ?? null, notes: (j.notes as string | null) ?? null };
}
