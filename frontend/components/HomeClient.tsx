"use client";
import { useState } from "react";
import Link from "next/link";
import { Camera } from "lucide-react";
import { EXERCISE_META } from "@/lib/exercises";
import type { ExerciseId } from "@/types";
import { UploadPanel } from "./UploadPanel";

export function HomeClient() {
  const [exercise, setExercise] = useState<ExerciseId>("squat");
  return (
    <div className="space-y-8">
      <div role="radiogroup" aria-label="Exercise" className="grid sm:grid-cols-3 gap-4">
        {(Object.keys(EXERCISE_META) as ExerciseId[]).map((id) => {
          const m = EXERCISE_META[id];
          const on = id === exercise;
          return (
            <button key={id} type="button" role="radio" aria-checked={on} onClick={() => setExercise(id)}
              className={`card p-5 text-left transition ${on ? "!border-accent ring-1 ring-accent" : "hover:border-muted"}`}>
              <m.icon className={on ? "text-accent" : "text-muted"} aria-hidden />
              <p className="mt-3 font-semibold">{m.label}</p>
              <p className="text-sm text-muted mt-1">{m.blurb}</p>
              <p className="text-xs text-muted mt-3 font-mono">{m.phases.join(" → ")}</p>
            </button>
          );
        })}
      </div>
      <div className="grid lg:grid-cols-[1fr_320px] gap-6 items-start">
        <UploadPanel exercise={exercise} />
        <aside className="card p-5 space-y-3">
          <Camera className="text-accent" aria-hidden />
          <h2 className="font-semibold">Live webcam mode</h2>
          <p className="text-sm text-muted">Runs pose estimation <em>in your browser</em> (nothing is uploaded) with the same rep rules and calibration as video mode.</p>
          <Link href={`/webcam?exercise=${exercise}`} className="btn w-full justify-center">Open webcam — {EXERCISE_META[exercise].label}</Link>
        </aside>
      </div>
    </div>
  );
}
