import type { AnalysisResult, Calibration, ExerciseConfig, ExerciseId, Preset } from "@/types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message); }
}

async function parse<T>(r: Response): Promise<T> {
  if (r.ok) return r.json();
  let code = `http_${r.status}`, msg = r.statusText;
  try { const j = await r.json(); code = j.error?.code ?? code; msg = j.error?.message ?? msg; } catch { /* non-JSON error */ }
  throw new ApiError(code, msg, r.status);
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  try { return await parse<T>(await fetch(`${API_URL}${path}`, init)); }
  catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError("network", `Cannot reach the RepVision backend at ${API_URL}. Is it running? (python scripts/run_local.py)`, 0);
  }
}

export interface AnalyzeParams { exercise: ExerciseId; video: File; sensitivity: Preset; calibration?: Calibration }

export async function analyze(p: AnalyzeParams): Promise<{ analysis_id: string; status: string }> {
  const fd = new FormData();
  fd.set("exercise", p.exercise);
  fd.set("video", p.video);
  fd.set("sensitivity", p.sensitivity);
  if (p.calibration) fd.set("calibration", JSON.stringify(p.calibration));
  return req("/api/analyze", { method: "POST", body: fd });
}

export const getResult = (id: string) => req<AnalysisResult>(`/api/results/${id}`);
export const videoUrl = (id: string, download = false) => `${API_URL}/api/videos/${id}${download ? "?download=1" : ""}`;

export interface CalibrateResponse {
  config: ExerciseConfig; warnings: string[]; suggested_overrides: Record<string, number>; camera_guidance: string;
  setup_check: { frames_checked: number; pose_coverage: number; valid_frames: number; mean_visibility: Record<string, number>; extended_position_deg: number | null } | null;
}
export async function calibrate(exercise: ExerciseId, sensitivity: Preset, calibration?: Calibration, video?: File): Promise<CalibrateResponse> {
  const fd = new FormData();
  fd.set("exercise", exercise);
  fd.set("sensitivity", sensitivity);
  if (calibration) fd.set("calibration", JSON.stringify(calibration));
  if (video) fd.set("video", video);
  return req("/api/calibrate", { method: "POST", body: fd });
}
