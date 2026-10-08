"use client";
import { CheckCircle2, CircleAlert, HelpCircle } from "lucide-react";
import { CLASS_STYLE } from "@/lib/exercises";
import type { RepEvent } from "@/types";

const ICON = { full: CheckCircle2, partial: CircleAlert, uncertain: HelpCircle } as const;

export function RepTimeline({ reps, durationMs, onSeek }: { reps: RepEvent[]; durationMs: number; onSeek: (ms: number) => void }) {
  if (!reps.length) return <p className="text-sm text-muted">No repetitions were detected.</p>;
  return (
    <div>
      <div className="relative h-12 rounded-lg bg-surface2 border border-line overflow-hidden" role="list" aria-label="Repetition timeline">
        {reps.map((r) => {
          const Icon = ICON[r.classification];
          const left = (r.start_ms / durationMs) * 100, width = Math.max(((r.end_ms - r.start_ms) / durationMs) * 100, 1.2);
          const c = CLASS_STYLE[r.classification];
          return (
            <button key={r.index} role="listitem" type="button" onClick={() => onSeek(r.start_ms)}
              title={`#${r.index} ${c.label} · ${(r.start_ms / 1000).toFixed(1)}–${(r.end_ms / 1000).toFixed(1)}s`}
              aria-label={`Repetition ${r.index}, ${c.label}, at ${(r.start_ms / 1000).toFixed(1)} seconds`}
              className="absolute top-1.5 bottom-1.5 rounded-md flex items-center justify-center text-[11px] font-semibold text-black/80 hover:brightness-125 overflow-hidden"
              style={{ left: `${left}%`, width: `${width}%`, background: c.color }}>
              {width > 4 && <><Icon size={12} aria-hidden className="mr-0.5 shrink-0" />{r.index}</>}
            </button>
          );
        })}
      </div>
      <div className="flex justify-between text-xs text-muted mt-1 font-mono"><span>0s</span><span>{(durationMs / 2000).toFixed(0)}s</span><span>{(durationMs / 1000).toFixed(0)}s</span></div>
    </div>
  );
}
