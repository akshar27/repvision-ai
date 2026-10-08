"""OpenCV annotation: skeleton, joint angles, HUD, feedback banner, bar line."""
from __future__ import annotations

import cv2
import numpy as np

from ..exercises.base import FrameResult
from ..models.schemas import RepEvent, RepSummary
from ..vision.landmarks import SKELETON_EDGES

BLUE = (235, 150, 40)      # BGR: skeleton
GREEN = (80, 200, 60)      # validated full rep
YELLOW = (0, 200, 255)     # partial / warning
RED = (60, 60, 235)        # tracking error / invalid
WHITE = (245, 245, 245)
PANEL = (28, 24, 22)
FONT = cv2.FONT_HERSHEY_SIMPLEX

CLS_COLOR = {"full": GREEN, "partial": YELLOW, "uncertain": RED}
BANNER_HOLD_MS = 2500.0


_ASCII = {"°": " deg", "≤": "<=", "≥": ">=", "–": "-", "—": "-", "×": "x", "…": "...", "’": "'"}


def _ascii(s: str) -> str:
    """Hershey fonts only draw ASCII; map common symbols instead of drawing '?' glyphs."""
    for k, v in _ASCII.items():
        s = s.replace(k, v)
    return s.encode("ascii", "replace").decode()


def _text(img, s, org, scale, color, thick=1):
    s = _ascii(s)
    cv2.putText(img, s, org, FONT, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


class Annotator:
    def __init__(self, exercise: str, bar_y: float | None = None) -> None:
        self.exercise, self.bar_y = exercise, bar_y
        self._banner: tuple[float, str, tuple[int, int, int]] | None = None
        self._flash: tuple[float, tuple[int, int, int]] | None = None

    def on_rep(self, rep: RepEvent, t_ms: float) -> None:
        color = CLS_COLOR[rep.classification]
        msg = next((f.message for f in rep.feedback if f.severity in ("error", "warning")), None) \
            or (rep.feedback[0].message if rep.feedback else rep.classification)
        if rep.classification == "partial":
            msg = "Partial rep: " + msg
        self._banner = (t_ms, msg, color)
        self._flash = (t_ms, color)

    def draw(self, frame: np.ndarray, res: FrameResult, summary: RepSummary, t_ms: float) -> np.ndarray:
        h, w = frame.shape[:2]
        s = max(0.5, min(w, h) / 900.0)
        ok = res.status == "ok"
        skel_color = BLUE
        if self._flash and t_ms - self._flash[0] < 700:
            skel_color = self._flash[1]
        if not ok:
            skel_color = RED

        if self.bar_y is not None and self.exercise == "pullup":
            y = int(self.bar_y * h)
            cv2.line(frame, (0, y), (w, y), YELLOW, max(1, int(2 * s)), cv2.LINE_AA)
            _text(frame, "bar (calibrated)", (10, max(14, y - 6)), 0.5 * s, YELLOW)

        pose = res.pose
        if pose is not None:
            pts = [(int(p[0] * w), int(p[1] * h)) for p in pose.points]
            for a, b in SKELETON_EDGES:
                if pose.vis(a) > 0.3 and pose.vis(b) > 0.3:
                    cv2.line(frame, pts[a], pts[b], skel_color, max(2, int(3 * s)), cv2.LINE_AA)
            key = set(res.joints)
            for i, p in enumerate(pts):
                if pose.vis(i) > 0.3 and (i in key or i in (11, 12, 23, 24)):
                    cv2.circle(frame, p, max(3, int(5 * s)), WHITE if i in key else skel_color, -1, cv2.LINE_AA)
            for _a, vtx, _c, val in res.draw_angles:
                if np.isfinite(val):
                    x, y = pts[vtx]
                    _text(frame, f"{val:.0f} deg", (x + 8, y - 8), 0.55 * s, WHITE, 1)

        # HUD
        pw, ph = int(300 * s + 20), int(150 * s + 20)
        overlay = frame.copy()
        cv2.rectangle(overlay, (8, 8), (8 + pw, 8 + ph), PANEL, -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
        y0 = int(34 * s) + 8
        _text(frame, self.exercise.upper(), (18, y0), 0.8 * s, WHITE, 2)
        _text(frame, f"Phase: {res.phase}", (18, y0 + int(30 * s)), 0.6 * s, BLUE)
        _text(frame, f"Full {summary.full}", (18, y0 + int(62 * s)), 0.7 * s, GREEN, 2)
        _text(frame, f"Partial {summary.partial}", (18 + int(110 * s), y0 + int(62 * s)), 0.7 * s, YELLOW, 2)
        if summary.uncertain:
            _text(frame, f"Uncertain {summary.uncertain}", (18, y0 + int(90 * s)), 0.55 * s, RED, 1)
        status = {"ok": ("TRACKING OK", GREEN), "low_confidence": ("LOW CONFIDENCE", RED),
                  "no_pose": ("NO PERSON", RED)}[res.status]
        _text(frame, f"{status[0]}  conf {res.confidence:.2f}", (18, y0 + int(118 * s)), 0.5 * s, status[1])

        # banner: last rep feedback, else live warning
        banner = None
        if self._banner and t_ms - self._banner[0] < BANNER_HOLD_MS:
            banner = (self._banner[1], self._banner[2])
        elif res.messages:
            banner = (res.messages[0], RED)
        if banner:
            overlay = frame.copy()
            bh = int(46 * s)
            cv2.rectangle(overlay, (0, h - bh), (w, h), PANEL, -1)
            cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
            cv2.rectangle(frame, (0, h - bh), (int(8 * s) + 4, h), banner[1], -1)
            _text(frame, banner[0][:110], (int(20 * s) + 6, h - int(16 * s)), 0.6 * s, WHITE, 1)
        return frame
