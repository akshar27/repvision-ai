import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";

export type ExerciseId = "squat" | "pushup" | "pullup";
export type Preset = "lenient" | "standard" | "strict";

export interface FeedbackItem { code: string; severity: string; message: string }
export interface RepEvent {
  index: number; start_ms: number; end_ms: number; duration_ms: number;
  classification: "full" | "partial" | "uncertain";
  feedback: FeedbackItem[]; measurement_confidence: number; classification_confidence: number;
}
export interface AnalysisResult {
  id: string; status: "queued" | "processing" | "completed" | "failed";
  exercise: ExerciseId; progress: number; error: string | null;
  summary: { total: number; full: number; partial: number; uncertain: number };
  reps: RepEvent[]; warnings: string[];
  feedback_summary: { code: string; severity: string; message: string; count: number }[];
  output_video: { available: boolean; browser_compatible: boolean; warning: string | null } | null;
  video: { duration_s: number } | null;
  disclaimer: string;
}

const KEY = "repvision_server_url";

/** Dev default: the machine running Metro is almost always the machine running the backend. */
function guessServer(): string {
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  return host ? `http://${host}:8000` : "http://localhost:8000";
}

export async function getServer(): Promise<string> {
  try {
    const v = await SecureStore.getItemAsync(KEY);
    if (v) return v;
  } catch {}
  return guessServer();
}

export async function setServer(url: string): Promise<void> {
  await SecureStore.setItemAsync(KEY, url.trim().replace(/\/+$/, ""));
}

async function errMessage(r: Response): Promise<string> {
  try {
    const j = await r.json();
    return j?.detail?.message ?? j?.error?.message ?? `Server error ${r.status}`;
  } catch {
    return `Server error ${r.status}`;
  }
}

async function timed(url: string, init?: RequestInit, ms = 8000): Promise<Response> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctl.signal });
  } catch {
    throw new Error(`Can't reach ${url.split("/api")[0]}. Is the backend running with --lan and is your phone on the same Wi-Fi?`);
  } finally {
    clearTimeout(t);
  }
}

export async function health(base: string) {
  const r = await timed(`${base}/api/health`);
  if (!r.ok) throw new Error(await errMessage(r));
  return r.json() as Promise<{ status: string; ffmpeg: boolean; pose_model_present: boolean }>;
}

export async function submitAnalysis(
  exercise: ExerciseId, sensitivity: Preset, video: { uri: string; name: string; type: string },
): Promise<string> {
  const base = await getServer();
  const form = new FormData();
  form.append("exercise", exercise);
  form.append("sensitivity", sensitivity);
  // React Native's FormData accepts a { uri, name, type } file descriptor.
  form.append("video", video as unknown as Blob);
  const r = await timed(`${base}/api/analyze`, { method: "POST", body: form }, 120000);
  if (!r.ok) throw new Error(await errMessage(r));
  return (await r.json()).analysis_id as string;
}

export async function getResult(id: string): Promise<AnalysisResult> {
  const base = await getServer();
  const r = await timed(`${base}/api/results/${id}`);
  if (!r.ok) throw new Error(await errMessage(r));
  return r.json();
}

export async function videoUrl(id: string): Promise<string> {
  return `${await getServer()}/api/videos/${id}`;
}
