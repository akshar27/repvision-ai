import type { ExerciseId, RepEvent } from "@/types";

const EXTRA: Record<ExerciseId, { label: string; get: (r: RepEvent) => number | null | undefined }[]> = {
  squat: [{ label: "Hip drop (× thigh)", get: (r) => r.rom.hip_drop_ratio }, { label: "Peak torso lean (°)", get: (r) => r.measurements.max_torso_inclination_deg }],
  pushup: [{ label: "Shoulder drop (× torso)", get: (r) => r.rom.shoulder_drop_ratio }, { label: "Max hip sag", get: (r) => r.measurements.max_hip_sag_ratio }, { label: "Max hip pike", get: (r) => r.measurements.max_hip_pike_ratio }],
  pullup: [{ label: "Shoulder travel (× arm)", get: (r) => r.rom.shoulder_travel_ratio }, { label: "Clearance margin (× arm)", get: (r) => r.measurements.clearance_margin_ratio }],
};
const f = (v: number | null | undefined, d = 1) => (v == null ? "—" : v.toFixed(d));

export function RomTable({ exercise, reps }: { exercise: ExerciseId; reps: RepEvent[] }) {
  if (!reps.length) return null;
  const extra = EXTRA[exercise];
  const roms = reps.map((r) => r.rom.angle_rom_deg).filter((v): v is number => v != null);
  const avg = roms.length ? roms.reduce((a, b) => a + b, 0) / roms.length : null;
  return (
    <div>
      <p className="text-sm text-muted mb-3">
        Angle range of motion — mean {f(avg)}°{roms.length ? ` · min ${f(Math.min(...roms))}° · max ${f(Math.max(...roms))}°` : ""} across {reps.length} detected movement cycle(s).
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-muted text-xs">
            {["#", "Result", "Duration (s)", "Start °", "Min °", "ROM °", ...extra.map((e) => e.label), "Confidence"].map((h) => <th key={h} className="py-2 pr-4 font-medium whitespace-nowrap">{h}</th>)}
          </tr></thead>
          <tbody className="font-mono">
            {reps.map((r) => (
              <tr key={r.index} className="border-t border-line/60">
                <td className="py-2 pr-4">{r.index}</td><td className="pr-4 capitalize">{r.classification}</td>
                <td className="pr-4">{(r.duration_ms / 1000).toFixed(1)}</td><td className="pr-4">{f(r.measurements.start_angle)}</td>
                <td className="pr-4">{f(r.measurements.min_angle)}</td><td className="pr-4">{f(r.rom.angle_rom_deg)}</td>
                {extra.map((e) => <td key={e.label} className="pr-4">{f(e.get(r), 2)}</td>)}
                <td className="pr-4" title="measurement / classification confidence (heuristic, not calibrated probabilities)">{r.measurement_confidence.toFixed(2)} / {r.classification_confidence.toFixed(2)}</td>
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
