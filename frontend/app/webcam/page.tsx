import { Suspense } from "react";
import { WebcamAnalyzer } from "@/components/WebcamAnalyzer";

export const metadata = { title: "Webcam — RepVision AI" };

export default function WebcamPage() {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-mono text-accent">Live mode</p>
        <h1 className="text-3xl font-bold tracking-tight">Webcam analysis</h1>
        <p className="text-muted mt-2 max-w-2xl">Pose estimation (MediaPipe Pose Landmarker, lite model) and the rep state machine run entirely in your browser,
          using the same thresholds and rules as uploaded-video mode.</p>
      </div>
      <Suspense fallback={<p className="text-muted">Loading…</p>}><WebcamAnalyzer /></Suspense>
    </div>
  );
}
