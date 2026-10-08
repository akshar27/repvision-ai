import { HomeClient } from "@/components/HomeClient";

export default function Home() {
  return (
    <div className="space-y-10">
      <section className="max-w-3xl">
        <p className="text-sm font-mono text-accent">Computer-vision fitness tracking</p>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mt-2">Count reps from movement, not guesses.</h1>
        <p className="mt-4 text-muted text-lg">
          RepVision AI estimates your skeleton with MediaPipe, tracks joint angles over time, and runs an exercise-specific
          state machine to separate <span className="text-ok">full</span>, <span className="text-warn">partial</span> and{" "}
          <span className="text-bad">uncertain</span> repetitions — with measurable, explainable feedback.
        </p>
      </section>
      <HomeClient />
    </div>
  );
}
