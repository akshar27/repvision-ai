import json
import shutil
import subprocess

import cv2
import pytest

from app.config import settings
from tests.conftest import make_video, wait_done
from tests.synth import FPS, lead_in, rep_profile

SQUAT_FRAMES = len(lead_in(172) + rep_profile(172, 80, 1.0, 0.2, 1.0) * 3)
PUSHUP_FRAMES = len(lead_in(168) + rep_profile(168, 70, 0.8, 0.1, 0.8) * 2)


def post(client, path, exercise, **extra):
    with open(path, "rb") as f:
        return client.post("/api/analyze", data={"exercise": exercise, **extra},
                           files={"video": (path.name, f, "video/mp4")})


def test_health_and_exercises(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and "ffmpeg" in h
    ex = client.get("/api/exercises").json()
    assert {e["id"] for e in ex["exercises"]} == {"squat", "pushup", "pullup"}
    sq = next(e for e in ex["exercises"] if e["id"] == "squat")
    assert sq["presets"]["strict"]["machine"]["full_depth_deg"] < sq["presets"]["lenient"]["machine"]["full_depth_deg"]
    assert "not a medical" in ex["disclaimer"].lower()


def test_openapi_published(client):
    spec = client.get("/openapi.json").json()
    assert "/api/analyze" in spec["paths"] and "/api/results/{analysis_id}" in spec["paths"]


def test_upload_process_and_retrieve(client, tmp_path):
    v = make_video(tmp_path / "sq.mp4", 60, SQUAT_FRAMES)
    r = post(client, v, "squat")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] in ("queued", "processing", "completed")
    res = wait_done(client, body["analysis_id"])
    assert res["status"] == "completed", res.get("error")
    assert res["summary"] == {"total": 3, "full": 3, "partial": 0, "uncertain": 0}
    assert res["video"]["width"] == 640 and res["video"]["height"] == 360
    assert res["tracking"]["frames_processed"] == SQUAT_FRAMES
    assert res["series"] and res["performance"]["pose_model"] == "fake-synthetic"
    assert [x["index"] for x in res["reps"]] == [1, 2, 3]
    assert "not a medical" in res["disclaimer"].lower()
    # persisted JSON equals API response
    saved = json.loads(client.store.result_path(body["analysis_id"]).read_text())
    assert saved["summary"] == res["summary"]
    # annotated video is a playable file
    vr = client.get(f"/api/videos/{body['analysis_id']}")
    assert vr.status_code == 200 and vr.headers["content-type"] == "video/mp4"
    out = tmp_path / "out.mp4"
    out.write_bytes(vr.content)
    cap = cv2.VideoCapture(str(out))
    assert cap.isOpened() and int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) >= SQUAT_FRAMES - 2
    ok, frame = cap.read()
    assert ok and frame.shape[:2] == (360, 640)
    cap.release()
    if shutil.which("ffprobe") and res["output_video"]["browser_compatible"]:
        codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
        assert codec == "h264"
    # range request support (browser seeking)
    rr = client.get(f"/api/videos/{body['analysis_id']}", headers={"Range": "bytes=0-99"})
    assert rr.status_code == 206 and len(rr.content) == 100
    dl = client.get(f"/api/videos/{body['analysis_id']}?download=1")
    assert "attachment" in dl.headers["content-disposition"]


def test_concurrent_sessions_are_isolated(client, tmp_path):
    a = make_video(tmp_path / "a.mp4", 60, SQUAT_FRAMES)
    b = make_video(tmp_path / "b.mp4", 140, PUSHUP_FRAMES)
    ida = post(client, a, "squat").json()["analysis_id"]
    idb = post(client, b, "pushup").json()["analysis_id"]
    ra, rb = wait_done(client, ida), wait_done(client, idb)
    assert ida != idb
    assert ra["exercise"] == "squat" and ra["summary"]["full"] == 3
    assert rb["exercise"] == "pushup" and rb["summary"]["full"] == 2


def test_reject_unsupported_extension(client, tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hi")
    r = client.post("/api/analyze", data={"exercise": "squat"}, files={"video": ("x.txt", p.read_bytes(), "text/plain")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_media"


def test_reject_fake_video_content(client):
    r = client.post("/api/analyze", data={"exercise": "squat"},
                    files={"video": ("fake.mp4", b"this is not a video" * 100, "video/mp4")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unreadable_video"
    assert list(client.store.uploads.iterdir()) == []         # temp upload cleaned up


def test_reject_invalid_exercise_sensitivity_and_empty(client, tmp_path):
    v = make_video(tmp_path / "s.mp4", 60, 40)
    assert post(client, v, "burpee").status_code == 422
    assert post(client, v, "squat", sensitivity="extreme").status_code == 422
    r = client.post("/api/analyze", data={"exercise": "squat"}, files={"video": ("e.mp4", b"", "video/mp4")})
    assert r.status_code == 422


def test_reject_oversized_upload(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    r = client.post("/api/analyze", data={"exercise": "squat"},
                    files={"video": ("big.mp4", b"\0" * (2 * 1024 * 1024), "video/mp4")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    assert list(client.store.uploads.iterdir()) == []


def test_invalid_calibration_rejected(client, tmp_path):
    v = make_video(tmp_path / "s.mp4", 60, 40)
    bad = json.dumps({"overrides": {"machine.full_depth_deg": 170}})        # violates ordering
    assert post(client, v, "squat", calibration=bad).status_code == 422
    assert post(client, v, "squat", calibration="{not json").status_code == 422
    wrong_ex = json.dumps({"exercise": "pushup"})
    assert post(client, v, "squat", calibration=wrong_ex).status_code == 422
    unknown = json.dumps({"overrides": {"machine.bogus": 1}})
    assert post(client, v, "squat", calibration=unknown).status_code == 422


def test_calibration_changes_result(client, tmp_path):
    v = make_video(tmp_path / "sq.mp4", 60, SQUAT_FRAMES)
    strict = json.dumps({"overrides": {"machine.full_depth_deg": 60}})        # impossible depth -> partial
    res = wait_done(client, post(client, v, "squat", calibration=strict).json()["analysis_id"])
    assert res["summary"]["full"] == 0 and res["summary"]["partial"] == 3
    assert res["config"]["machine"]["full_depth_deg"] == 60


def test_calibrate_endpoint(client):
    r = client.post("/api/calibrate", data={"exercise": "pullup", "sensitivity": "strict"})
    assert r.status_code == 200
    j = r.json()
    assert j["config"]["preset"] == "strict" and any("bar" in w.lower() for w in j["warnings"])
    cal = json.dumps({"bar_y": 0.3})
    r = client.post("/api/calibrate", data={"exercise": "pullup", "calibration": cal})
    assert r.json()["config"]["bar_y"] == 0.3 and not r.json()["warnings"]
    assert client.post("/api/calibrate", data={"exercise": "squat", "calibration": cal}).status_code == 422   # bar_y on squat


def test_path_traversal_and_unknown_ids(client):
    assert client.get("/api/results/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)
    assert client.get("/api/results/not-a-valid-id").status_code == 400
    assert client.get("/api/videos/../../etc/passwd").status_code in (400, 404)
    assert client.get("/api/videos/" + "a" * 32).status_code == 404
    assert client.get("/api/results/" + "a" * 32).status_code == 404


def test_failed_job_reports_error(client, tmp_path, monkeypatch):
    import app.services.analysis_service as svc
    def boom(*a, **k):
        raise RuntimeError("model exploded")
    monkeypatch.setattr(svc, "process_video", boom)
    v = make_video(tmp_path / "s.mp4", 60, 40)
    res = wait_done(client, post(client, v, "squat").json()["analysis_id"])
    assert res["status"] == "failed" and "model exploded" in res["error"]
    assert list(client.store.uploads.iterdir()) == []


def test_cors_allows_local_frontend(client):
    r = client.options("/api/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
