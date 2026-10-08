# RepVision AI

Pose-based exercise analysis for **squats, push-ups and pull-ups**. Upload a video (or use your webcam) and RepVision
estimates your skeleton, tracks joint angles over time, runs an exercise-specific repetition state machine, and reports
**full / partial / uncertain** reps with measurable feedback, an annotated video, charts and exportable JSON.

> **Not a medical tool.** RepVision gives *estimated* movement feedback from 2D pose estimation. It is not a medical
> assessment, an injury-risk diagnosis, or a guarantee of exercise safety or technique quality. Feedback strings describe
> measured deviations only.

No LLM or vision-language model is used to guess counts. Repetitions come from pose landmarks → smoothed joint angles →
a hysteresis state machine.

## Architecture

```
Video / webcam → frame decode → PoseEstimator (MediaPipe Tasks API) → validation + smoothing
  → exercise features (angles, ratios) → RepStateMachine → per-rep evaluation (full/partial/uncertain + feedback)
  → OpenCV overlay + ffmpeg H.264 → JSON result → FastAPI → Next.js dashboard
```

| Piece | Where | Notes |
|---|---|---|
| Pose interface | `backend/app/vision/pose_estimator.py` | Exercise code only sees `Pose` (33-point BlazePose topology, normalized image coords). Swap in ViTPose/RTMPose by writing one adapter. |
| MediaPipe adapter | `vision/mediapipe_estimator.py` | Pose Landmarker **Tasks API**, VIDEO mode, one instance per session. |
| Geometry/smoothing | `vision/geometry.py`, `smoothing.py` | NaN-safe angles, aspect-corrected coordinates, time-constant EMA (frame-rate independent). |
| State machine | `tracking/state_machine.py` | REST → FLEXING → PEAK → EXTENDING → REST with hysteresis, dwell times, min rep duration, reversal handling, stall/gap handling. |
| Analyzers | `exercises/{squat,pushup,pullup}.py` | Feature extraction + rep rules. Thresholds/presets in `exercises/config.py`. |
| Pipeline | `vision/video_processor.py`, `rendering/overlay.py` | Decode → analyze → annotate → encode (ffmpeg libx264 pipe; falls back to OpenCV with a warning). |
| API / jobs | `api/routes.py`, `services/` | FastAPI; analysis on an in-process thread pool; JSON file store behind a `ResultStore` seam (swap for SQLite/Postgres). |
| Frontend | `frontend/` | Next.js (App Router), Tailwind, Recharts, lucide. |
| Webcam | `frontend/lib/engine/`, `components/WebcamAnalyzer.tsx` | MediaPipe Tasks **in the browser** (WASM, no upload) + a TypeScript port of the same rules. |

**Rules are shared, not guessed twice.** The TS engine reads thresholds from `frontend/lib/generated/exercise-configs.json`
(exported from the Python configs). `scripts/export_shared.py` also replays 14 synthetic scenarios through the Python
engine and stores the expected output; `npm test` replays them through the TS engine and requires identical
classifications, timings, feedback codes and confidences. That is a *rule-parity* test, not an accuracy test.

## Exercises & rules (summary)

Primary signal = a joint angle that is large at rest and small at the peak. All thresholds are **defaults to calibrate**.

| | Signal | Full rep requires | Extra feedback |
|---|---|---|---|
| Squat | knee angle (hip-knee-ankle) | standing start (≥160°), depth ≤100°, return to standing. Strict preset also requires hips at/below knee. | torso lean, incomplete extension, shallow depth |
| Push-up | elbow angle | top start (≥155°), elbow ≤95° and shoulder drop, return to lockout; plank posture required | hip sag / pike vs shoulder–ankle line |
| Pull-up | elbow angle | dead-hang start, elbow ≤90° + shoulder travel, return to hang, **top clearance vs calibrated bar** | bent-elbow start, no return to hang, clearance not met |

Pull-up honesty: MediaPipe has **no chin landmark and does not detect the bar**. Top clearance is judged only against a
bar height you mark, using the *mouth* landmark (conservative proxy) or nose. Without a bar line, or when the head is not
visible at the top, clearance is reported as **unverified** and the rep is labelled **uncertain** (switchable via
`require_bar_for_full`). Bar-line calibration assumes a level camera and the person near the bar's plane.

Each rep records index, start/end/duration, classification, angle measurements, ROM features, criteria, feedback,
`measurement_confidence` (landmark visibility × frame coverage) and `classification_confidence` (heuristic from distance to
decision boundaries — **not** a calibrated probability).

## Install (macOS / Linux)

Requires Python 3.11+, Node 20+, and ffmpeg (recommended: browser-playable annotated video).

```bash
brew install ffmpeg            # macOS   |   sudo apt install ffmpeg   # Linux
python3 scripts/run_local.py --setup   # venv + deps + model download + npm install, then starts both servers
```

Afterwards just `python3 scripts/run_local.py`. Backend: <http://localhost:8000/docs> · Frontend: <http://localhost:3000>.

Manual:

```bash
cd backend && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
python3 scripts/download_models.py          # from repo root; backend models + copies for the browser
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev   # postinstall copies the MediaPipe WASM into public/
```

Config: copy `.env.example` → `.env` (backend, `REPVISION_*`) and set `NEXT_PUBLIC_API_URL` for the frontend if not 8000.

## Usage

**Video:** pick an exercise → drop a video → (pull-ups: click the frame to mark the bar) → *Analyze*. Use *Check camera
setup* to run a 5 s pose check that reports hidden/cropped body parts and suggests a rest threshold. Results page: annotated
video (click a timeline rep to seek), counts, feedback, angle chart (+ data-table view), ROM table, *Export JSON*, *Download video*.

**Webcam:** `/webcam` — Start camera. Handles denied permission, no/busy camera, mid-session disconnect, model loading,
tracking loss messages, *Reset session*, and session JSON export. Calibration changes restart the session. Uses the
`lite` model (WASM, GPU delegate with CPU fallback).

**CLI:**
```bash
backend/.venv/bin/python scripts/analyze_video.py squat clip.mp4 --sensitivity strict --out data/outputs/cli
backend/.venv/bin/python scripts/analyze_video.py pullup clip.mp4 --bar-y 0.18      # or --calibration file.json
```

**API:**
```bash
curl -F exercise=squat -F sensitivity=standard -F video=@clip.mp4 localhost:8000/api/analyze   # 202 {analysis_id,...}
curl localhost:8000/api/results/<id>        # status/progress, then full result
curl -OJ "localhost:8000/api/videos/<id>?download=1"
curl -F exercise=pullup -F calibration='{"bar_y":0.2}' -F video=@clip.mp4 localhost:8000/api/calibrate
curl localhost:8000/api/exercises           # defaults + presets (single source of truth)
```
Errors: `{"error":{"code","message"}}` with 413/415/422/404/400 as appropriate. Uploads are validated by extension, content
type, size (streamed; default 300 MB), decodability and duration; ids are 32-hex and every path is derived from a validated id.

## Calibration

`data/annotations/sample_calibration.json` shows the format: `preset` (lenient/standard/strict), dotted `overrides`
(e.g. `machine.full_depth_deg`), and `bar_y` (fraction of frame height, 0 = top). The UI can load/save this JSON for both
video and webcam. Invalid values are rejected (ordering `full_depth < partial_min < rest_enter` etc.) by both backend and
frontend. Don't assume one threshold fits everyone: camera angle changes apparent joint angles (side/45° views recommended).

## Tests

```bash
cd backend && .venv/bin/python -m pytest -q     # 72 tests
cd frontend && npm test && npx tsc --noEmit && npx eslint . && npm run build
```
Python: geometry, smoothing, squat/push-up/pull-up scenarios (full, partial, no motion, threshold oscillation, missing
landmarks, tracking loss, bent start, stalled return, uncertain clearance), evaluation metrics, and API integration
(valid upload → processing → result → H.264 video with range requests, unsupported/oversized/fake/empty uploads, bad
calibration, path traversal, failed jobs, concurrent isolated sessions, CORS). Integration tests replay synthetic skeletons
through a fake estimator but use the real decode/annotate/encode/API path.

**Synthetic tests validate rule logic only. They say nothing about real-world pose-estimation accuracy.**

## Evaluation

```bash
python scripts/evaluate.py my_gt.json data/outputs/<id>/result.json --csv report.csv --json report.json
```
Ground truth: `data/annotations/ground_truth_example.json` (format example, **not** a real annotation). Predicted reps are
matched one-to-one to ground truth by interval IoU (default ≥0.3, greedy by IoU) so a missed rep plus a phantom rep can't
cancel out. Reports count error, full-rep precision/recall, partial recall, macro-F1, per-error-category recall, mean matched
IoU, processing latency/fps and tracking coverage. **No accuracy numbers are claimed here because no annotated dataset
exists in this repo yet.**

## What was actually verified (2026-10-08, Apple M3 Pro, macOS)

- Automated: 72 pytest + 17 vitest pass; `tsc`, `eslint`, `next build` clean.
- Real model on a real clip (`data/samples/mixkit_squat.mp4`, 1280×720@24 fps, 7 s, Mixkit free license): pose found in
  100% of frames; **43–44 fps end-to-end** (`full` model, CPU, 640 px inference, includes annotation + H.264 encode). This
  clip shows lunge-like movement from a moving camera, not a clean squat, so its rep labels demonstrate the pipeline, not
  accuracy. Feeding it to the pull-up analyzer produced "uncertain" reps and a low-coverage warning (as it should).
- UI → API → pipeline → results flow driven in Chrome (upload, pull-up bar line, analysis, results/stats/timeline/chart/ROM).
- Browser asset serving for webcam mode (WASM, model) returns 200.

**Implemented but NOT verified:** (1) **live webcam capture** — the camera-permission flow can't be driven by my automation,
so webcam mode is verified only at the rule level (TS parity tests), type/lint/build, and asset serving; expect to debug on
first use. (2) **Inline playback of the annotated video** — the automation browser couldn't load *any* media (even a WebM
from a different server), so I verified the file instead (ffprobe: H.264/yuv420p/faststart; range requests return 206).
(3) No accuracy evaluation on labelled data; no pull-up or push-up footage was tested with the real model.

## Known limitations

- 2D image-plane angles: camera angle, lens distortion and occlusion bias them; single person only (primary pose).
- Squat depth uses a knee-angle criterion (optionally + hip-below-knee); it is a calibrated proxy, not true depth.
- Push-up alignment ratios and torso lean are projection-dependent; sag/pike warnings assume a side view.
- Pull-up clearance needs a manual bar line and a level camera; chin is approximated (see above).
- Analysis jobs run in an in-process thread pool and are **not durable** — in-flight jobs are marked failed after a restart.
- Result store is local JSON files; no auth, no multi-user isolation beyond unguessable ids. Do not expose publicly as-is.
- Webcam mode uses the `lite` model for speed; accuracy is lower than the `full` model used for uploads.

## Troubleshooting

- *"Pose model not found"* → `python3 scripts/download_models.py`.
- *Annotated video doesn't play* → check `/api/health` shows `ffmpeg: true`; without ffmpeg output is MPEG-4 Part 2.
- *"Cannot reach the RepVision backend"* → backend not running or `NEXT_PUBLIC_API_URL`/CORS origin mismatch (`REPVISION_CORS_ORIGINS`).
- *Few/no reps* → run *Check camera setup*; ensure required joints are visible (squat: hips–ankles; push-up: shoulders–ankles; pull-up: arms + head); loosen via the *lenient* preset or lower `rest_enter_deg`.
- *Webcam blocked* → needs HTTPS or `localhost`, and camera permission.
- Apple-silicon log noise (`inference_feedback_manager`, XNNPACK) from MediaPipe is harmless.

## Future work

ViTPose+/RTMPose adapter, automatic exercise classification, more exercises (lunges, curls, deadlifts), SQLite/Postgres history,
durable job queue, multi-person tracking, voice cues, temporal-model classifiers, labelled benchmark + model comparison, Docker.
