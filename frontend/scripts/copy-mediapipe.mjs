// Copies the MediaPipe WASM runtime from node_modules into public/ so webcam mode works offline (no CDN).
import { cpSync, mkdirSync, existsSync } from "node:fs";
const src = "node_modules/@mediapipe/tasks-vision/wasm";
if (existsSync(src)) {
  mkdirSync("public/mediapipe/wasm", { recursive: true });
  cpSync(src, "public/mediapipe/wasm", { recursive: true });
  console.log("copied mediapipe wasm -> public/mediapipe/wasm");
} else console.warn("tasks-vision not installed; run npm install");
