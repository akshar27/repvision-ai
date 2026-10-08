"use client";
import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CLASS_STYLE } from "@/lib/exercises";
import type { ExerciseConfig, RepEvent, SeriesPoint } from "@/types";

const KEYS = { squat: "knee", pushup: "elbow", pullup: "elbow" } as const;

export function AngleChart({ exercise, series, reps, config }: { exercise: keyof typeof KEYS; series: SeriesPoint[]; reps: RepEvent[]; config: ExerciseConfig }) {
  const [table, setTable] = useState(false);
  const k = KEYS[exercise];
  const lines = [
    { key: "combined", label: `${k} (used for counting)`, color: "var(--s1)", width: 2 },
    { key: `${k}_left`, label: "left", color: "var(--s2)", width: 1.5 },
    { key: `${k}_right`, label: "right", color: "var(--s3)", width: 1.5 },
  ];
  const data = useMemo(() => series.map((p) => ({
    t: +(p.t / 1000).toFixed(2), combined: p.angles[k] ?? null, [`${k}_left`]: p.angles[`${k}_left`] ?? null, [`${k}_right`]: p.angles[`${k}_right`] ?? null,
  })), [series, k]);
  const m = config.machine;

  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <p className="text-xs text-muted">Joint angle (°, 2D image plane). Dashed lines: configured rest and depth thresholds. Shaded bands: detected reps.</p>
        <button type="button" className="text-xs underline text-muted shrink-0 ml-3" onClick={() => setTable(!table)}>{table ? "Show chart" : "Show data table"}</button>
      </div>
      {table ? (
        <div className="max-h-80 overflow-auto border border-line rounded-lg">
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-surface2"><tr><th className="text-left p-2">t (s)</th>{lines.map((l) => <th key={l.key} className="text-right p-2">{l.label}</th>)}</tr></thead>
            <tbody>{data.filter((_, i) => i % Math.max(1, Math.floor(data.length / 150)) === 0).map((d) => (
              <tr key={d.t} className="border-t border-line/60"><td className="p-2">{d.t}</td>
                {lines.map((l) => <td key={l.key} className="p-2 text-right">{(d as Record<string, number | null>)[l.key]?.toFixed(1) ?? "—"}</td>)}</tr>))}</tbody>
          </table>
        </div>
      ) : (
        <div className="h-72" role="img" aria-label={`${k} joint angle over time with detected repetitions`}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
              <CartesianGrid stroke="var(--border)" strokeOpacity={0.5} vertical={false} />
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--border)" }} unit="s" />
              <YAxis domain={[0, 190]} ticks={[0, 45, 90, 135, 180]} tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false} unit="°" />
              {reps.map((r) => <ReferenceArea key={r.index} x1={r.start_ms / 1000} x2={r.end_ms / 1000} fill={CLASS_STYLE[r.classification].color} fillOpacity={0.12} />)}
              <ReferenceLine y={m.rest_enter_deg} stroke="var(--muted)" strokeDasharray="4 4" />
              <ReferenceLine y={m.full_depth_deg} stroke="var(--muted)" strokeDasharray="4 4" />
              <Tooltip contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} labelFormatter={(v) => `${v}s`}
                formatter={(v) => (typeof v === "number" ? `${v.toFixed(1)}°` : "—")} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {lines.map((l) => <Line key={l.key} dataKey={l.key} name={l.label} stroke={l.color} strokeWidth={l.width} dot={false} connectNulls={false} isAnimationActive={false} />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
