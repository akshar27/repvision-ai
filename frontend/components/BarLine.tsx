"use client";
import { useCallback, useRef } from "react";

/** Wraps a video/canvas and overlays a draggable horizontal line = pull-up bar height (fraction of frame height). */
export function BarLine({ value, onChange, children }: { value: number | null; onChange: (v: number) => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const setFromEvent = useCallback((clientY: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r || r.height === 0) return;
    onChange(Math.min(1, Math.max(0, (clientY - r.top) / r.height)));
  }, [onChange]);

  return (
    <div ref={ref} className="relative inline-block w-full select-none touch-none"
      onPointerDown={(e) => { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); setFromEvent(e.clientY); }}
      onPointerMove={(e) => { if (e.buttons) setFromEvent(e.clientY); }}>
      {children}
      {value !== null && (
        <div role="slider" tabIndex={0} aria-label="Pull-up bar height" aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={Math.round(value * 100)} aria-valuetext={`${Math.round(value * 100)}% from top of frame`}
          className="absolute left-0 right-0 h-0 border-t-2 border-dashed border-warn cursor-ns-resize"
          style={{ top: `${value * 100}%` }}
          onKeyDown={(e) => {
            if (e.key === "ArrowUp") { e.preventDefault(); onChange(Math.max(0, value - 0.005)); }
            if (e.key === "ArrowDown") { e.preventDefault(); onChange(Math.min(1, value + 0.005)); }
          }}>
          <span className="absolute -top-6 left-2 text-xs bg-black/70 text-warn px-1.5 py-0.5 rounded">bar · {Math.round(value * 100)}%</span>
        </div>
      )}
    </div>
  );
}
