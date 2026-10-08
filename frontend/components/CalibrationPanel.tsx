"use client";
import { useMemo, useRef, useState } from "react";
import { Download, RotateCcw, Upload } from "lucide-react";
import { CalibrationError, buildConfig, configFromCalibration, parseCalibration, PRESETS } from "@/lib/engine/config";
import type { Calibration, ExerciseId, Preset } from "@/types";

type Spec = { key: string; label: string; kind: "num" | "bool" | "select"; step?: number; options?: string[]; hint?: string };

const COMMON: Spec[] = [
  { key: "machine.rest_enter_deg", label: "Rest / extended at ≥ (°)", kind: "num", step: 1, hint: "Joint angle that counts as the start/end position." },
  { key: "machine.full_depth_deg", label: "Full depth at ≤ (°)", kind: "num", step: 1, hint: "Joint angle that must be reached for a full rep." },
  { key: "machine.partial_min_deg", label: "Partial attempt at ≤ (°)", kind: "num", step: 1, hint: "Movement must reach this to count as a partial rep." },
];
const BY_EXERCISE: Record<ExerciseId, Spec[]> = {
  squat: [
    { key: "require_hip_below_knee", label: "Also require hips below knees", kind: "bool" },
    { key: "torso_lean_warn_deg", label: "Torso lean warning at > (°)", kind: "num", step: 1 },
  ],
  pushup: [
    { key: "min_shoulder_drop_ratio", label: "Min shoulder drop (× torso)", kind: "num", step: 0.01 },
    { key: "sag_warn_ratio", label: "Hip sag warning (× body length)", kind: "num", step: 0.01 },
    { key: "pike_warn_ratio", label: "Hip pike warning (× body length)", kind: "num", step: 0.01 },
  ],
  pullup: [
    { key: "min_travel_ratio", label: "Min shoulder travel (× arm length)", kind: "num", step: 0.01 },
    { key: "top_reference", label: "Head landmark for bar clearance", kind: "select", options: ["mouth", "nose"], hint: "MediaPipe has no chin landmark; mouth is the conservative proxy." },
    { key: "clearance_margin_ratio", label: "Clearance margin (× arm length)", kind: "num", step: 0.01 },
    { key: "require_bar_for_full", label: "Require bar calibration for 'full'", kind: "bool", hint: "Off: reps without a bar line can be 'full' but clearance stays unverified." },
  ],
};

function getPath(o: unknown, key: string): unknown {
  return key.split(".").reduce<unknown>((a, k) => (a as Record<string, unknown>)?.[k], o);
}

export function CalibrationPanel({ exercise, value, onChange }: { exercise: ExerciseId; value: Calibration; onChange: (c: Calibration) => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const { cfg, error } = useMemo(() => {
    try { return { cfg: configFromCalibration(exercise, { ...value, exercise }), error: null }; }
    catch (e) { return { cfg: buildConfig(exercise, value.preset), error: e instanceof CalibrationError ? e.message : String(e) }; }
  }, [exercise, value]);
  const defaults = useMemo(() => buildConfig(exercise, value.preset), [exercise, value.preset]);

  const setOverride = (key: string, v: number | boolean | string | undefined) => {
    const o = { ...value.overrides };
    if (v === undefined || v === getPath(defaults, key)) delete o[key]; else o[key] = v;
    onChange({ ...value, overrides: o });
  };

  const save = () => {
    const payload: Calibration = { ...value, exercise };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `repvision-${exercise}-calibration.json` });
    a.click();
    URL.revokeObjectURL(url);
  };
  const load = async (f: File) => {
    try {
      const cal = parseCalibration(await f.text());
      configFromCalibration(exercise, cal);                                   // validate against this exercise
      onChange({ ...cal, exercise });
      setMsg(`Loaded ${f.name}`);
    } catch (e) { setMsg(`Could not load: ${e instanceof Error ? e.message : e}`); }
  };

  return (
    <section aria-labelledby="calib-h" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="calib-h" className="font-semibold">Calibration</h3>
        <div className="flex gap-2">
          <button type="button" className="btn btn-ghost text-sm" onClick={() => fileRef.current?.click()}><Upload size={14} aria-hidden />Load JSON</button>
          <button type="button" className="btn btn-ghost text-sm" onClick={save}><Download size={14} aria-hidden />Save JSON</button>
          <button type="button" className="btn btn-ghost text-sm" onClick={() => { onChange({ preset: value.preset, overrides: {}, bar_y: value.bar_y }); setMsg(null); }}><RotateCcw size={14} aria-hidden />Reset</button>
          <input ref={fileRef} type="file" accept="application/json,.json" hidden aria-label="Load calibration JSON"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) load(f); e.target.value = ""; }} />
        </div>
      </div>
      <div>
        <label className="label" htmlFor="preset">Sensitivity preset</label>
        <select id="preset" className="field" value={value.preset} onChange={(e) => onChange({ ...value, preset: e.target.value as Preset, overrides: {} })}>
          {PRESETS.map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
        </select>
        <p className="text-xs text-muted mt-1">Lenient accepts shallower reps; strict demands more depth/extension. Changing preset clears manual overrides.</p>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {[...COMMON, ...BY_EXERCISE[exercise]].map((s) => {
          const id = `cal-${s.key}`;
          const cur = getPath(cfg, s.key);
          return (
            <div key={s.key}>
              {s.kind === "bool" ? (
                <label className="flex items-center gap-2 text-sm pt-5"><input type="checkbox" checked={Boolean(cur)} onChange={(e) => setOverride(s.key, e.target.checked)} />{s.label}</label>
              ) : s.kind === "select" ? (
                <><label className="label" htmlFor={id}>{s.label}</label>
                  <select id={id} className="field" value={String(cur)} onChange={(e) => setOverride(s.key, e.target.value)}>{s.options!.map((o) => <option key={o}>{o}</option>)}</select></>
              ) : (
                <><label className="label" htmlFor={id}>{s.label}</label>
                  <input id={id} type="number" className="field" step={s.step} value={Number(cur)}
                    onChange={(e) => setOverride(s.key, e.target.value === "" ? undefined : Number(e.target.value))} /></>
              )}
              {s.hint && <p className="text-xs text-muted mt-1">{s.hint}</p>}
            </div>
          );
        })}
      </div>
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {msg && <p role="status" className="text-sm text-muted">{msg}</p>}
    </section>
  );
}

export const emptyCalibration = (): Calibration => ({ preset: "standard", overrides: {}, bar_y: null });
