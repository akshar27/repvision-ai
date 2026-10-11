#!/usr/bin/env python3
"""Start backend (FastAPI :8000) and frontend (Next.js :3000) together. Ctrl-C stops both.

  python3 scripts/run_local.py [--setup]      # --setup creates the venv, installs deps, downloads models

macOS / Linux. Requires Python 3.11+, Node 20+, and (recommended) ffmpeg for browser-playable annotated video.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACK, FRONT = ROOT / "backend", ROOT / "frontend"
VENV_PY = BACK / ".venv" / "bin" / "python"


def run(cmd, cwd):
    print("+", " ".join(map(str, cmd)))
    subprocess.check_call(cmd, cwd=cwd)


def setup() -> None:
    py = next((p for p in ("python3.12", "python3.11", "python3") if shutil.which(p)), None)
    if not VENV_PY.exists():
        run([py, "-m", "venv", ".venv"], BACK)
    run([str(VENV_PY), "-m", "pip", "install", "-q", "-r", "requirements.txt"], BACK)
    run([str(VENV_PY), str(ROOT / "scripts" / "download_models.py")], ROOT)
    run(["npm", "install"], FRONT)
    if not shutil.which("ffmpeg"):
        print("WARNING: ffmpeg not found - annotated video will not be browser-playable. "
              "Install: `brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Linux).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--backend-port", default="8000")
    ap.add_argument("--frontend-port", default="3000")
    ap.add_argument("--lan", action="store_true", help="bind the backend to 0.0.0.0 so the phone app can reach it")
    a = ap.parse_args()
    if a.setup:
        setup()
    if not VENV_PY.exists() or not (FRONT / "node_modules").exists():
        sys.exit("Not set up yet. Run: python3 scripts/run_local.py --setup")
    if not (BACK / "assets" / "pose_landmarker_full.task").exists():
        sys.exit("Pose model missing. Run: python3 scripts/download_models.py")

    env = {**os.environ, "NEXT_PUBLIC_API_URL": f"http://localhost:{a.backend_port}"}
    procs = [
        subprocess.Popen([str(VENV_PY), "-m", "uvicorn", "app.main:app", "--port", a.backend_port,
                          "--host", "0.0.0.0" if a.lan else "127.0.0.1"], cwd=BACK, env=env),
        subprocess.Popen(["npm", "run", "dev", "--", "--port", a.frontend_port], cwd=FRONT, env=env),
    ]
    print(f"\nBackend  http://localhost:{a.backend_port}/docs\nFrontend http://localhost:{a.frontend_port}\n(Ctrl-C to stop)\n")

    def stop(*_):
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while all(p.poll() is None for p in procs):
        time.sleep(0.5)
    print("A process exited; shutting down.")
    stop()


if __name__ == "__main__":
    main()
