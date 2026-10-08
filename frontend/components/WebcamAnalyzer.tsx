"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, Camera, CameraOff, Download, Loader2, RotateCcw, Square } from "lucide-react";
import type { PoseLandmarker } from "@mediapipe/tasks-vision";
import { createAnalyzer, DISCLAIMER, LM, SKELETON_EDGES, configFromCalibration, EXERCISE_IDS } from "@/lib/engine";
import type { Analyzer, FrameResult, Pose } from "@/lib/engine";
import { EXERCISE_META, CLASS_STYLE } from "@/lib/exercises";
import type { Calibration, ExerciseId, RepEvent } from "@/types";
import { BarLine } from "./BarLine";
import { CalibrationPanel, emptyCalibration } from "./CalibrationPanel";

type Status = "idle" | "loading" | "running" | "error";
const BLUE = "#3987e5", YELLOW = "#e3a008", RED = "#f0605d";

function cameraErrorMessage(e: unknown): string {
  const name = (e as DOMException)?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "Camera permission was denied. Allow camera access in the browser's site settings and try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No camera was found. Connect a camera and try again.";
  if (name === "NotReadableError") return "The camera is in use by another application. Close it and try again.";
  return `Could not start the camera: ${(e as Error)?.message ?? e}`;
}

export function WebcamAnalyzer() {
  const params = useSearchParams();
  const initial = params.get("exercise");
  const [exercise, setExercise] = useState<ExerciseId>(EXERCISE_IDS.includes(initial as ExerciseId) ? (initial as ExerciseId) : "squat");
  const [cal, setCal] = useState<Calibration>(emptyCalibration());
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState({ phase: "—", full: 0, partial: 0, uncertain: 0, tracking: "ok" as FrameResult["status"], angle: NaN, fps: 0, msg: "" });
  const [reps, setReps] = useState<RepEvent[]>([]);
  const [banner, setBanner] = useState<{ text: string; cls: RepEvent["classification"] } | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const analyzerRef = useRef<Analyzer | null>(null);
  const landmarkerRef = useRef<PoseLandmarker | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number>(0);
  const runningRef = useRef(false);

  const { cfg, cfgError } = useMemo(() => {
    try { return { cfg: configFromCalibration(exercise, { ...cal, exercise, bar_y: exercise === "pullup" ? cal.bar_y : null }), cfgError: null }; }
    catch (e) { return { cfg: null, cfgError: e instanceof Error ? e.message : String(e) }; }
  }, [exercise, cal]);

  const resetSession = useCallback(() => {
    analyzerRef.current?.reset();
    setReps([]); setBanner(null);
    setLive((l) => ({ ...l, phase: "—", full: 0, partial: 0, uncertain: 0 }));
  }, []);

  // Changing rules/calibration starts a fresh session (state reset during render, per React guidance)
  const [prevCfg, setPrevCfg] = useState(cfg);
  if (cfg !== prevCfg) {
    setPrevCfg(cfg); setReps([]); setBanner(null);
    setLive((l) => ({ ...l, phase: "—", full: 0, partial: 0, uncertain: 0 }));
  }
  useEffect(() => { if (cfg) analyzerRef.current = createAnalyzer(cfg); }, [cfg]);

  const stop = useCallback(() => {
    runningRef.current = false;
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    landmarkerRef.current?.close();
    landmarkerRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    const c = canvasRef.current; c?.getContext("2d")?.clearRect(0, 0, c.width, c.height);
    setStatus((s) => (s === "error" ? s : "idle"));
  }, []);
  useEffect(() => stop, [stop]);

  const fail = useCallback((msg: string) => { stop(); setError(msg); setStatus("error"); }, [stop]);

  const start = async () => {
    if (!cfg) return;
    setError(null); setStatus("loading");
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser does not support camera access (needs HTTPS or localhost).");
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 960 }, height: { ideal: 540 }, facingMode: "user" }, audio: false }).catch((e) => { throw Object.assign(new Error(cameraErrorMessage(e)), { handled: true }); });
      streamRef.current = stream;
      stream.getVideoTracks()[0].addEventListener("ended", () => fail("The camera was disconnected. Reconnect it and press Start."));
      const video = videoRef.current!;
      video.srcObject = stream;
      await video.play();

      const { FilesetResolver, PoseLandmarker } = await import("@mediapipe/tasks-vision");
      const fileset = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
      const make = (delegate: "GPU" | "CPU") => PoseLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: "/models/pose_landmarker_lite.task", delegate }, runningMode: "VIDEO", numPoses: 1,
      });
      try { landmarkerRef.current = await make("GPU"); } catch { landmarkerRef.current = await make("CPU"); }
      analyzerRef.current = createAnalyzer(cfg);
      setReps([]);
      runningRef.current = true;
      setStatus("running");
      loop();
    } catch (e) {
      fail((e as { handled?: boolean }).handled || e instanceof Error ? (e as Error).message : String(e));
    }
  };

  const loop = () => {
    const video = videoRef.current, canvas = canvasRef.current, lm = landmarkerRef.current, analyzer = analyzerRef.current;
    if (!runningRef.current || !video || !canvas || !lm || !analyzer) return;
    let lastVideoTime = -1, t0 = -1, fpsEma = 0, lastTick = performance.now(), noPoseSince: number | null = null;
    const ctx = canvas.getContext("2d")!;

    const frame = () => {
      if (!runningRef.current) return;
      rafRef.current = requestAnimationFrame(frame);
      if (video.readyState < 2 || video.currentTime === lastVideoTime) return;   // only process new camera frames
      lastVideoTime = video.currentTime;
      const now = performance.now();
      if (t0 < 0) t0 = now;
      const t = now - t0;
      if (canvas.width !== video.videoWidth) { canvas.width = video.videoWidth; canvas.height = video.videoHeight; }

      const result = lm.detectForVideo(video, now);
      let pose: Pose | null = null;
      const l = result.landmarks[0];
      if (l && l.length === 33) pose = { x: l.map((p) => p.x), y: l.map((p) => p.y), vis: l.map((p) => p.visibility ?? 0), t, aspect: video.videoWidth / video.videoHeight };
      const res = analyzer.update(pose, t);

      noPoseSince = pose ? null : noPoseSince ?? now;
      const dt = now - lastTick; lastTick = now;
      fpsEma = fpsEma ? fpsEma * 0.9 + (1000 / dt) * 0.1 : 1000 / dt;
      draw(ctx, canvas, res, cfg?.bar_y ?? null);

      const s = analyzer.summary;
      setLive({ phase: res.phase, full: s.full, partial: s.partial, uncertain: s.uncertain, tracking: res.status, angle: res.signal, fps: Math.round(fpsEma),
        msg: noPoseSince && now - noPoseSince > 2000 ? "Tracking lost – step back so your whole body is in view." : res.messages[0] ?? "" });
      if (res.newReps.length) {
        const r = res.newReps[res.newReps.length - 1];
        setReps([...analyzer.reps]);
        setBanner({ text: r.feedback.find((f) => f.severity !== "success")?.message ?? r.feedback[0]?.message ?? r.classification, cls: r.classification });
      }
    };
    rafRef.current = requestAnimationFrame(frame);
  };

  const exportSession = () => {
    const doc = { exercise, config: cfg, summary: analyzerRef.current?.summary, reps, disclaimer: DISCLAIMER, source: "webcam (client-side, estimated)" };
    const url = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" }));
    Object.assign(document.createElement("a"), { href: url, download: `repvision-webcam-${exercise}.json` }).click();
    URL.revokeObjectURL(url);
  };

  const running = status === "running";
  const trackColor = live.tracking === "ok" ? "text-ok" : "text-bad";

  return (
    <div className="grid lg:grid-cols-[1.5fr_1fr] gap-6 items-start">
      <div className="space-y-4">
        <div role="radiogroup" aria-label="Exercise" className="flex gap-2 flex-wrap">
          {EXERCISE_IDS.map((id) => (
            <button key={id} type="button" role="radio" aria-checked={id === exercise} disabled={status === "loading"}
              onClick={() => { setExercise(id); setCal({ ...emptyCalibration(), preset: cal.preset }); }}
              className={`btn btn-ghost text-sm ${id === exercise ? "!border-accent text-accent" : ""}`}>{EXERCISE_META[id].label}</button>
          ))}
        </div>

        <div className="card p-3">
          <BarLine value={exercise === "pullup" ? cal.bar_y ?? null : null} onChange={(v) => exercise === "pullup" && setCal({ ...cal, bar_y: v })}>
            <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
              <video ref={videoRef} className="absolute inset-0 w-full h-full object-contain" muted playsInline aria-label="Camera preview" />
              <canvas ref={canvasRef} className="absolute inset-0 w-full h-full object-contain pointer-events-none" />
              {status !== "running" && (
                <div className="absolute inset-0 grid place-items-center text-center p-6 text-muted">
                  {status === "loading" ? <div className="space-y-2"><Loader2 className="animate-spin mx-auto" aria-hidden /><p>Starting camera and loading pose model…</p></div>
                    : <div className="space-y-2"><CameraOff className="mx-auto" aria-hidden /><p>Camera is off. Nothing is recorded or uploaded — analysis runs in your browser.</p></div>}
                </div>
              )}
              {running && <div className="absolute top-2 left-2 text-xs font-mono bg-black/60 rounded px-2 py-1 space-y-0.5">
                <div>{EXERCISE_META[exercise].label.toUpperCase()} · {live.phase}</div>
                <div className={trackColor}>{live.tracking === "ok" ? "TRACKING OK" : live.tracking === "no_pose" ? "NO PERSON" : "LOW CONFIDENCE"} · {live.fps} fps</div></div>}
              {running && banner && <div className="absolute bottom-0 inset-x-0 bg-black/70 px-3 py-2 text-sm" style={{ borderLeft: `6px solid ${CLASS_STYLE[banner.cls].color}` }}>{banner.cls === "partial" ? "Partial rep: " : ""}{banner.text}</div>}
            </div>
          </BarLine>
          {exercise === "pullup" && <p className="text-xs text-muted mt-2">Click/drag on the preview to mark the bar height{cal.bar_y == null ? " (needed to verify top clearance; otherwise reps are “uncertain”)." : "."}</p>}
        </div>

        <div className="flex flex-wrap gap-3">
          {!running ? <button type="button" className="btn" onClick={start} disabled={status === "loading" || !cfg}><Camera size={16} aria-hidden />Start camera</button>
            : <button type="button" className="btn" onClick={() => { stop(); }}><Square size={16} aria-hidden />Stop</button>}
          <button type="button" className="btn btn-ghost" onClick={resetSession}><RotateCcw size={14} aria-hidden />Reset session</button>
          <button type="button" className="btn btn-ghost" onClick={exportSession} disabled={!reps.length}><Download size={14} aria-hidden />Export session JSON</button>
        </div>
        {(error || cfgError) && <p role="alert" className="text-sm text-bad flex gap-2"><AlertTriangle size={16} className="shrink-0 mt-0.5" aria-hidden />{error ?? cfgError}</p>}
        {running && live.msg && <p role="status" className="text-sm text-warn">{live.msg}</p>}
        <p className="text-xs text-muted">Camera tip: {EXERCISE_META[exercise].camera}</p>
      </div>

      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-3" aria-live="polite">
          <Stat label="Full" value={live.full} color={CLASS_STYLE.full.color} />
          <Stat label="Partial" value={live.partial} color={CLASS_STYLE.partial.color} />
          <Stat label="Uncertain" value={live.uncertain} color={CLASS_STYLE.uncertain.color} />
        </div>
        <div className="card p-4 max-h-64 overflow-auto">
          <h2 className="font-semibold mb-2 text-sm">Repetitions</h2>
          {reps.length === 0 ? <p className="text-sm text-muted">Reps appear here as they complete.</p> : (
            <ul className="space-y-1 text-sm">{[...reps].reverse().map((r) => (
              <li key={r.index}><span className="font-mono text-muted">#{r.index}</span>{" "}
                <span style={{ color: CLASS_STYLE[r.classification].color }}>{CLASS_STYLE[r.classification].label}</span>{" "}
                <span className="text-muted">{r.feedback.map((f) => f.message).join(" ")}</span></li>))}</ul>)}
        </div>
        <div className="card p-4"><CalibrationPanel exercise={exercise} value={cal} onChange={setCal} />
          <p className="text-xs text-muted mt-3">Changing calibration restarts the session.</p></div>
        <p className="text-xs text-muted">{DISCLAIMER}</p>
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return <div className="card p-3"><p className="text-xs text-muted">{label}</p><p className="text-3xl font-bold font-mono" style={{ color }}>{value}</p></div>;
}

function draw(ctx: CanvasRenderingContext2D, canvas: HTMLCanvasElement, res: FrameResult, barY: number | null) {
  const { width: w, height: h } = canvas;
  ctx.clearRect(0, 0, w, h);
  if (barY != null) {
    ctx.strokeStyle = YELLOW; ctx.setLineDash([10, 8]); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(0, barY * h); ctx.lineTo(w, barY * h); ctx.stroke(); ctx.setLineDash([]);
  }
  const p = res.pose;
  if (!p) return;
  const color = res.status === "ok" ? BLUE : RED;
  ctx.lineWidth = Math.max(2, w / 300); ctx.strokeStyle = color; ctx.lineCap = "round";
  for (const [a, b] of SKELETON_EDGES) {
    if (p.vis[a] > 0.3 && p.vis[b] > 0.3) { ctx.beginPath(); ctx.moveTo(p.x[a] * w, p.y[a] * h); ctx.lineTo(p.x[b] * w, p.y[b] * h); ctx.stroke(); }
  }
  const key = new Set(res.joints);
  for (let i = 0; i < 33; i++) {
    if (p.vis[i] > 0.3 && (key.has(i) || i === LM.LEFT_SHOULDER || i === LM.RIGHT_SHOULDER)) {
      ctx.fillStyle = key.has(i) ? "#fff" : color; ctx.beginPath(); ctx.arc(p.x[i] * w, p.y[i] * h, Math.max(3, w / 220), 0, 7); ctx.fill();
    }
  }
  ctx.font = `${Math.max(12, Math.round(w / 55))}px sans-serif`; ctx.fillStyle = "#fff"; ctx.strokeStyle = "#000"; ctx.lineWidth = 3;
  for (const [, v, , val] of res.drawAngles) {
    if (!isFinite(val)) continue;
    const x = p.x[v] * w + 8, y = p.y[v] * h - 8, s = `${val.toFixed(0)}°`;
    ctx.strokeText(s, x, y); ctx.fillText(s, x, y);
  }
}
