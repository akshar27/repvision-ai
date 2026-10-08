"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, ScanSearch, UploadCloud, Wand2 } from "lucide-react";
import { analyze, calibrate, ApiError, type CalibrateResponse } from "@/lib/api";
import { configFromCalibration } from "@/lib/engine/config";
import { EXERCISE_META } from "@/lib/exercises";
import type { Calibration, ExerciseId } from "@/types";
import { BarLine } from "./BarLine";
import { CalibrationPanel, emptyCalibration } from "./CalibrationPanel";

export function UploadPanel({ exercise }: { exercise: ExerciseId }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [cal, setCal] = useState<Calibration>(emptyCalibration());
  const [busy, setBusy] = useState<"analyze" | "check" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkState, setCheck] = useState<{ key: string; data: CalibrateResponse } | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const checkKey = `${exercise}|${file?.name}|${file?.size}`;
  const check = checkState?.key === checkKey ? checkState.data : null;   // stale checks (other exercise/file) are ignored

  const pick = (f: File | undefined) => { if (f) { setFile(f); setError(null); } };
  const payload = (): Calibration => ({ ...cal, exercise, bar_y: exercise === "pullup" ? cal.bar_y : null });

  const run = async (kind: "analyze" | "check") => {
    if (!file) return;
    setBusy(kind); setError(null);
    try {
      configFromCalibration(exercise, payload());                           // fail fast on invalid calibration
      if (kind === "analyze") {
        const r = await analyze({ exercise, video: file, sensitivity: cal.preset, calibration: payload() });
        router.push(`/results/${r.analysis_id}`);
        return;
      }
      setCheck({ key: checkKey, data: await calibrate(exercise, cal.preset, payload(), file) });
    } catch (e) {
      setError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
    } finally { setBusy(null); }
  };

  return (
    <div className="card p-5 space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Analyze a recorded video — {EXERCISE_META[exercise].label}</h2>
        <p className="text-sm text-muted mt-1">Camera tip: {EXERCISE_META[exercise].camera}</p>
      </div>

      {!file ? (
        <div role="button" tabIndex={0} aria-label="Choose a video file"
          onClick={() => inputRef.current?.click()} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
          className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition ${drag ? "border-accent bg-accent/10" : "border-line hover:border-muted"}`}>
          <UploadCloud className="mx-auto text-muted" aria-hidden />
          <p className="mt-2 font-medium">Drop a video here or click to browse</p>
          <p className="text-xs text-muted">MP4 · MOV · WebM · MKV · AVI — processed locally on your machine</p>
        </div>
      ) : (
        <div className="space-y-2">
          {exercise === "pullup" ? (
            <div className="max-w-xl">
              <BarLine value={cal.bar_y ?? null} onChange={(v) => setCal({ ...cal, bar_y: v })}>
                <video src={url!} className="block w-full h-auto rounded-lg bg-black" muted playsInline preload="metadata"
                  onLoadedMetadata={(e) => { e.currentTarget.currentTime = Math.min(0.5, e.currentTarget.duration / 2 || 0); }} />
              </BarLine>
              <p className="text-xs text-muted mt-2">
                {cal.bar_y === null ? "Click the video where the bar is to calibrate top clearance. Without it, pull-up reps are labelled “uncertain”."
                  : "Drag the dashed line (or use ↑/↓) to the bar height. Use a frame where the bar is visible and the camera is level."}
              </p>
              {cal.bar_y !== null && <button type="button" className="text-xs underline text-muted" onClick={() => setCal({ ...cal, bar_y: null })}>Clear bar line</button>}
            </div>
          ) : (
            <video src={url!} className="max-w-xl w-full rounded-lg bg-black" controls muted playsInline preload="metadata" />
          )}
          <p className="text-sm"><strong>{file.name}</strong> <span className="text-muted">({(file.size / 1048576).toFixed(1)} MB)</span>{" "}
            <button type="button" className="underline text-muted text-xs" onClick={() => setFile(null)}>change</button></p>
        </div>
      )}
      <input ref={inputRef} type="file" accept="video/*,.mkv,.mov" hidden aria-label="Video file" onChange={(e) => pick(e.target.files?.[0])} />

      <details className="group">
        <summary className="cursor-pointer text-sm font-medium text-accent">Calibration &amp; sensitivity</summary>
        <div className="pt-4"><CalibrationPanel exercise={exercise} value={cal} onChange={setCal} /></div>
      </details>

      {check && (
        <div className="card p-4 bg-surface2 text-sm space-y-2" role="region" aria-label="Camera setup check">
          <p className="font-medium flex items-center gap-2"><ScanSearch size={16} aria-hidden />Camera setup check (first 5 s)</p>
          {check.setup_check && <p className="text-muted">Person detected in {(check.setup_check.pose_coverage * 100).toFixed(0)}% of frames; landmarks usable in {check.setup_check.valid_frames} frames
            {check.setup_check.extended_position_deg != null && <> · extended position ≈ {check.setup_check.extended_position_deg}°</>}.</p>}
          {check.warnings.length === 0 && <p className="text-ok">No setup problems detected.</p>}
          {check.warnings.map((w) => <p key={w} className="text-warn flex gap-2"><AlertTriangle size={16} className="shrink-0" aria-hidden />{w}</p>)}
          {Object.keys(check.suggested_overrides).length > 0 && (
            <button type="button" className="btn btn-ghost text-sm" onClick={() => setCal({ ...cal, overrides: { ...cal.overrides, ...check.suggested_overrides } })}>
              <Wand2 size={14} aria-hidden />Apply suggested thresholds ({Object.entries(check.suggested_overrides).map(([k, v]) => `${k.split(".").pop()}=${v}`).join(", ")})
            </button>)}
        </div>
      )}

      {error && <p role="alert" className="text-sm text-bad flex gap-2"><AlertTriangle size={16} className="shrink-0 mt-0.5" aria-hidden />{error}</p>}
      <div className="flex flex-wrap gap-3">
        <button type="button" className="btn" disabled={!file || busy !== null} onClick={() => run("analyze")}>
          {busy === "analyze" ? <Loader2 className="animate-spin" size={16} aria-hidden /> : null}Analyze video
        </button>
        <button type="button" className="btn btn-ghost" disabled={!file || busy !== null} onClick={() => run("check")}>
          {busy === "check" ? <Loader2 className="animate-spin" size={16} aria-hidden /> : null}Check camera setup
        </button>
      </div>
    </div>
  );
}
