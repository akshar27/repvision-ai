import { Dumbbell, MoveDown, PersonStanding } from "lucide-react";
import type { ExerciseId } from "@/types";

export const EXERCISE_META: Record<ExerciseId, { label: string; blurb: string; camera: string; icon: typeof Dumbbell; phases: string[] }> = {
  squat: { label: "Squat", icon: PersonStanding, phases: ["Standing", "Descending", "Bottom", "Ascending"],
    blurb: "Knee/hip angles, depth criterion and torso inclination.",
    camera: "Side or 45° view, head-to-feet in frame, camera at hip height, 2–3 m away." },
  pushup: { label: "Push-up", icon: MoveDown, phases: ["Top", "Descending", "Bottom", "Ascending"],
    blurb: "Elbow angles, shoulder travel and shoulder–hip–ankle alignment.",
    camera: "Side view at floor/hip height, whole body visible." },
  pullup: { label: "Pull-up", icon: Dumbbell, phases: ["Dead hang", "Ascending", "Top", "Descending"],
    blurb: "Elbow angles, shoulder travel and top clearance against a calibrated bar.",
    camera: "Front or slightly off-axis, level camera, arms and head visible. Mark the bar height." },
};

export const CLASS_STYLE = {
  full: { label: "Full", color: "var(--ok)" },
  partial: { label: "Partial", color: "var(--warn)" },
  uncertain: { label: "Uncertain", color: "var(--bad)" },
} as const;
