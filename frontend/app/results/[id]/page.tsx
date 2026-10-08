"use client";
import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleAlert, Download, FileJson, HelpCircle, Loader2 } from "lucide-react";
import { ApiError, getResult, videoUrl } from "@/lib/api";
import { CLASS_STYLE, EXERCISE_META } from "@/lib/exercises";
import type { AnalysisResult, ExerciseConfig, Severity } from "@/types";
import { AngleChart } from "@/components/AngleChart";
import { RepTimeline } from "@/components/RepTimeline";
import { RomTable } from "@/components/RomTable";

const SEV_ICON: Record<Severity, typeof CheckCircle2> = { success: CheckCircle2, info: HelpCircle, warning: CircleAlert, error: AlertTriangle };
const SEV_COLOR: Record<Severity, string> = { success: "text-ok", info: "text-muted", warning: "text-warn", error: "text-bad" };

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [res, setRes] = useState<AnalysisResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let stop = false, timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await getResult(id);
        if (stop) return;
        setRes(r); setErr(null);
        if (r.status === "queued" || r.status === "processing") timer = setTimeout(tick, 1000);
      } catch (e) {
        if (stop) return;
        setErr(e instanceof ApiError ? e.message : String(e));
        if (!(e instanceof ApiError) || e.status === 0) timer = setTimeout(tick, 3000);
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [id]);

  if (err && !res) return <Notice tone="bad" title="Could not load analysis" body={err} />;
  if (!res) return <p className="text-muted flex gap-2 items-center"><Loader2 className="animate-spin" size={16} aria-hidden />Loading…</p>;
  if (res.status === "failed") return <Notice tone="bad" title="Analysis failed" body={res.error ?? "Unknown error"} />;
  if (res.status !== "completed") {
    return (
      <div className="card p-8 max-w-xl mx-auto text-center space-y-3" role="status">
        <Loader2 className="animate-spin mx-auto text-accent" aria-hidden />
        <p className="font-semibold">{res.status === "queued" ? "Queued…" : "Analyzing video…"}</p>
        <div className="h-2 rounded bg-surface2 overflow-hidden" role="progressbar" aria-valuenow={Math.round(res.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-accent transition-all" style={{ width: `${Math.max(3, res.progress * 100)}%` }} />
        </div>
        <p className="text-xs text-muted">{Math.round(res.progress * 100)}% — pose estimation runs locally and keeps the page updated.</p>
      </div>
    );
  }

  const meta = EXERCISE_META[res.exercise];
  const cfg = res.config as unknown as ExerciseConfig;
  const durationMs = Math.max((res.video?.duration_s ?? 0) * 1000, res.series.at(-1)?.t ?? 0, ...res.reps.map((r) => r.end_ms), 1);
  const seek = (ms: number) => { const v = videoRef.current; if (v) { v.currentTime = Math.max(0, ms / 1000 - 0.3); void v.play().catch(() => {}); } };
  const exportJson = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(res, null, 2)], { type: "application/json" }));
    Object.assign(document.createElement("a"), { href: url, download: `repvision-${res.exercise}-${res.id.slice(0, 8)}.json` }).click();
    URL.revokeObjectURL(url);
  };
  const s = res.summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-mono text-accent">{meta.label} analysis</p>
          <h1 className="text-2xl font-bold tracking-tight">{res.video?.filename ?? res.id}</h1>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn btn-ghost text-sm" onClick={exportJson}><FileJson size={14} aria-hidden />Export JSON</button>
          {res.output_video?.available && <a className="btn btn-ghost text-sm" href={videoUrl(res.id, true)} download><Download size={14} aria-hidden />Download video</a>}
          <Link href="/" className="btn text-sm">New analysis</Link>
        </div>
      </div>

      {res.warnings.map((w) => <Notice key={w} tone="warn" title="Heads up" body={w} />)}

      <div className="grid lg:grid-cols-[1.4fr_1fr] gap-6 items-start">
        <div className="card p-3">
          {res.output_video?.available ? (
            <video ref={videoRef} src={videoUrl(res.id)} controls playsInline className="w-full rounded-lg bg-black" aria-label="Annotated video" />
          ) : <p className="p-6 text-muted text-sm">No annotated video was produced. {res.output_video?.warning}</p>}
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Total reps" value={s.total} color="var(--text)" />
            <Stat label="Full" value={s.full} color={CLASS_STYLE.full.color} />
            <Stat label="Partial" value={s.partial} color={CLASS_STYLE.partial.color} />
            <Stat label="Uncertain" value={s.uncertain} color={CLASS_STYLE.uncertain.color} />
          </div>
          <div className="card p-4">
            <h2 className="font-semibold mb-2">Feedback</h2>
            {res.feedback_summary.length === 0
              ? <p className="text-sm text-muted">{s.full === s.total && s.total > 0 ? "All detected reps met the configured criteria." : "No technique deviations were measured."}</p>
              : <ul className="space-y-2">{res.feedback_summary.map((f) => {
                const I = SEV_ICON[f.severity];
                return <li key={f.code} className="flex gap-2 text-sm"><I size={16} className={`shrink-0 mt-0.5 ${SEV_COLOR[f.severity]}`} aria-hidden />
                  <span>{f.message} <span className="text-muted">×{f.count}</span></span></li>;
              })}</ul>}
            <p className="text-xs text-muted mt-3">{res.disclaimer}</p>
          </div>
        </div>
      </div>

      <Section title="Repetition timeline"><RepTimeline reps={res.reps} durationMs={durationMs} onSeek={seek} />
        <ul className="mt-4 grid md:grid-cols-2 gap-x-6 gap-y-1 text-sm">
          {res.reps.map((r) => (
            <li key={r.index} className="flex gap-2"><span className="font-mono text-muted w-6">#{r.index}</span>
              <span style={{ color: CLASS_STYLE[r.classification].color }} className="w-20 shrink-0">{CLASS_STYLE[r.classification].label}</span>
              <span className="text-muted">{r.feedback.map((f) => f.message).join(" ")}</span></li>))}
        </ul>
      </Section>
      <Section title="Joint angles"><AngleChart exercise={res.exercise} series={res.series} reps={res.reps} config={cfg} /></Section>
      <Section title="Range of motion"><RomTable exercise={res.exercise} reps={res.reps} /></Section>

      <Section title="Run details">
        <dl className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          <Detail k="Pose coverage" v={res.tracking ? `${(res.tracking.pose_coverage * 100).toFixed(0)}% of frames` : "—"} />
          <Detail k="Valid for this exercise" v={res.tracking ? `${(res.tracking.valid_coverage * 100).toFixed(0)}% of frames` : "—"} />
          <Detail k="Processing" v={res.performance ? `${res.performance.processing_seconds}s · ${res.performance.processing_fps} fps` : "—"} />
          <Detail k="Hardware" v={res.performance?.hardware ?? "—"} />
          <Detail k="Preset" v={cfg.preset} /><Detail k="Full depth at ≤" v={`${cfg.machine.full_depth_deg}°`} />
          <Detail k="Rest at ≥" v={`${cfg.machine.rest_enter_deg}°`} />
          <Detail k="Video" v={res.video ? `${res.video.width}×${res.video.height} @ ${res.video.fps} fps` : "—"} />
        </dl>
      </Section>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return <div className="card p-4"><p className="text-xs text-muted">{label}</p><p className="text-4xl font-bold font-mono mt-1" style={{ color }}>{value}</p></div>;
}
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card p-5"><h2 className="font-semibold mb-4">{title}</h2>{children}</section>;
}
function Detail({ k, v }: { k: string; v: string }) { return <div><dt className="text-xs text-muted">{k}</dt><dd className="font-mono">{v}</dd></div>; }
function Notice({ tone, title, body }: { tone: "bad" | "warn"; title: string; body: string }) {
  return (
    <div role="alert" className={`card p-4 flex gap-3 ${tone === "bad" ? "!border-bad/60" : "!border-warn/50"}`}>
      <AlertTriangle className={tone === "bad" ? "text-bad" : "text-warn"} size={18} aria-hidden />
      <div><p className="font-medium">{title}</p><p className="text-sm text-muted">{body}</p><Link href="/" className="text-sm underline">Back to start</Link></div>
    </div>
  );
}
