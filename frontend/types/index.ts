export type ExerciseId = "squat" | "pushup" | "pullup";
export type Preset = "lenient" | "standard" | "strict";
export type Classification = "full" | "partial" | "uncertain";
export type Severity = "success" | "info" | "warning" | "error";

export interface FeedbackItem { code: string; severity: Severity; message: string }

export interface RepEvent {
  index: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  classification: Classification;
  measurements: Record<string, number | null>;
  rom: Record<string, number | null>;
  criteria: Record<string, boolean | string | null>;
  feedback: FeedbackItem[];
  measurement_confidence: number;
  classification_confidence: number;
}

export interface RepSummary { total: number; full: number; partial: number; uncertain: number }

export interface SeriesPoint {
  t: number;
  signal: number | null;
  angles: Record<string, number | null>;
  phase: string;
  valid: boolean;
}

export interface AnalysisResult {
  id: string;
  status: "queued" | "processing" | "completed" | "failed";
  exercise: ExerciseId;
  created_at: string;
  progress: number;
  error: string | null;
  video: { filename: string | null; width: number; height: number; fps: number; duration_s: number; frame_count: number } | null;
  summary: RepSummary;
  reps: RepEvent[];
  series: SeriesPoint[];
  tracking: { frames_processed: number; frames_with_pose: number; frames_valid: number; pose_coverage: number; valid_coverage: number } | null;
  performance: { processing_seconds: number; processing_fps: number; pose_model: string; inference_max_side: number; hardware: string; note: string } | null;
  config: Record<string, unknown>;
  warnings: string[];
  feedback_summary: { code: string; severity: Severity; message: string; count: number }[];
  output_video: { available: boolean; codec: string | null; browser_compatible: boolean; warning: string | null } | null;
  disclaimer: string;
}

export interface MachineConfig {
  rest_enter_deg: number; leave_delta_deg: number; full_depth_deg: number; partial_min_deg: number;
  reverse_delta_deg: number; min_phase_ms: number; min_rep_ms: number; max_gap_ms: number; abandon_ms: number;
  ref_window_ms: number; stall_ms: number; start_lead_ms: number;
}

export interface ExerciseConfig {
  exercise: ExerciseId;
  preset: Preset;
  machine: MachineConfig;
  min_visibility: number;
  smoothing_tau_ms: number;
  min_rep_coverage: number;
  max_signal_speed_dps: number;
  // exercise specific (optional by exercise)
  require_hip_below_knee?: boolean; hip_below_knee_ratio?: number; torso_lean_warn_deg?: number;
  min_shoulder_drop_ratio?: number; sag_warn_ratio?: number; pike_warn_ratio?: number; plank_max_angle_deg?: number;
  min_travel_ratio?: number; bar_y?: number | null; top_reference?: "mouth" | "nose";
  clearance_margin_ratio?: number; require_bar_for_full?: boolean;
}

export interface Calibration {
  exercise?: ExerciseId | null;
  preset: Preset;
  overrides: Record<string, number | boolean | string | null>;
  bar_y?: number | null;
  notes?: string | null;
}
