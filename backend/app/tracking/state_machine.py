"""Generic flexion/extension repetition state machine.

One machine serves all exercises: each analyzer feeds it a scalar joint-angle
signal that is large at rest and small at the movement peak. A repetition is a
full cycle REST -> FLEXING -> (PEAK) -> EXTENDING -> REST, never a single
threshold crossing. Key properties:

* hysteresis on every transition (``leave_delta``, ``reverse_delta``)
* dwell times (``min_phase_ms``) to enter PEAK and to re-enter REST
* cycles shorter than ``min_rep_ms`` or that never dip to ``partial_min_deg`` are
  discarded as noise (duplicate/oscillation prevention)
* a direction reversal before reaching REST closes the cycle as "did not return"
  and immediately starts the next one from the turning point
* tracking gaps are recorded; long loss abandons the cycle
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum

from ..exercises.config import MachineConfig


class Phase(str, Enum):
    REST = "REST"
    FLEXING = "FLEXING"
    PEAK = "PEAK"
    EXTENDING = "EXTENDING"


@dataclass
class Cycle:
    start_ms: float
    start_signal: float
    min_signal: float
    min_ms: float
    started_from_rest: bool
    ever_armed: bool
    reached_depth: bool = False
    returned_to_rest: bool = False
    end_ms: float = 0.0
    end_signal: float = float("nan")
    gaps: int = 0
    max_gap_ms: float = 0.0
    reason: str = "returned"      # returned | reversed | abandoned | flush
    truncated: bool = False       # video/stream ended before the cycle closed
    lead_ms: float = 1e9          # time between first valid frame and cycle start
    abandoned: bool = False


class RepStateMachine:
    def __init__(self, cfg: MachineConfig) -> None:
        self.cfg = cfg
        self.reset()

    def reset(self) -> None:
        self.phase = Phase.REST
        self.cycle: Cycle | None = None
        self.armed = False
        self._window: deque[tuple[float, float]] = deque()
        self._below_since: float | None = None
        self._rest_since: float | None = None
        self._max_up = float("nan")
        self._max_up_t = 0.0
        self._progress_t = 0.0
        self._last_valid_t: float | None = None
        self._last_signal = float("nan")
        self._first_valid_t: float | None = None

    # ---------------------------------------------------------------- helpers
    def _ref(self) -> tuple[float, float]:
        best_t, best = 0.0, -math.inf
        for t, s in self._window:
            if s >= best:
                best, best_t = s, t
        return best, best_t

    def _push_window(self, t: float, s: float) -> None:
        self._window.append((t, s))
        while self._window and t - self._window[0][0] > self.cfg.ref_window_ms:
            self._window.popleft()

    def _emit(self, cyc: Cycle, out: list[Cycle]) -> None:
        if cyc.end_ms - cyc.start_ms >= self.cfg.min_rep_ms and cyc.min_signal <= self.cfg.partial_min_deg:
            out.append(cyc)

    def _begin(self, t_start: float, s_start: float, s_now: float, t_now: float, from_rest: bool) -> None:
        self.cycle = Cycle(t_start, s_start, s_now, t_now, from_rest, self.armed)
        if self._first_valid_t is not None:
            self.cycle.lead_ms = t_start - self._first_valid_t
        self.phase = Phase.FLEXING
        self._below_since = None
        self._rest_since = None

    # ----------------------------------------------------------------- update
    def update(self, t: float, s: float | None) -> list[Cycle]:
        out: list[Cycle] = []
        c = self.cfg
        valid = s is not None and math.isfinite(s)
        if not valid:
            if (self.cycle is not None and self._last_valid_t is not None
                    and t - self._last_valid_t > c.abandon_ms):
                self._abandon(out)
            return out

        s = float(s)  # type: ignore[arg-type]
        if self._last_valid_t is not None and self.cycle is not None:
            gap = t - self._last_valid_t
            if gap > c.abandon_ms:
                self._abandon(out)
            elif gap > c.max_gap_ms:
                self.cycle.gaps += 1
                self.cycle.max_gap_ms = max(self.cycle.max_gap_ms, gap)
        if self._first_valid_t is None:
            self._first_valid_t = t
        self._last_valid_t, self._last_signal = t, s

        if self.phase == Phase.REST:
            self._push_window(t, s)
            if s >= c.rest_enter_deg:
                self.armed = True
            ref, ref_t = self._ref()
            if s < ref - c.leave_delta_deg:
                self._begin(ref_t, ref, s, t, from_rest=ref >= c.rest_enter_deg and self.armed)
            return out

        cyc = self.cycle
        assert cyc is not None
        if s < cyc.min_signal:
            cyc.min_signal, cyc.min_ms = s, t

        if self.phase == Phase.FLEXING:
            if s <= c.full_depth_deg:
                if self._below_since is None:
                    self._below_since = t
                if t - self._below_since >= c.min_phase_ms:
                    self.phase = Phase.PEAK
                    cyc.reached_depth = True
            else:
                self._below_since = None
            if self.phase == Phase.FLEXING and s > cyc.min_signal + c.reverse_delta_deg:
                self.phase = Phase.EXTENDING
                self._max_up, self._max_up_t, self._progress_t, self._rest_since = s, t, t, None
            elif self.phase == Phase.FLEXING and cyc.min_signal > c.partial_min_deg and s >= c.rest_enter_deg:
                self._to_rest(t, s)       # shallow wobble that never became a rep
                return out
        elif self.phase == Phase.PEAK:
            if s > cyc.min_signal + c.reverse_delta_deg:
                self.phase = Phase.EXTENDING
                self._max_up, self._max_up_t, self._progress_t, self._rest_since = s, t, t, None

        if self.phase == Phase.EXTENDING:
            if s >= self._max_up:
                if s > self._max_up + 1.5:
                    self._progress_t = t      # real progress, not sub-degree creep
                self._max_up, self._max_up_t = s, t
            if s >= c.rest_enter_deg:
                if self._rest_since is None:
                    self._rest_since = t
                if t - self._rest_since >= c.min_phase_ms:
                    cyc.returned_to_rest, cyc.end_ms, cyc.end_signal, cyc.reason = True, self._rest_since, s, "returned"
                    self._emit(cyc, out)
                    self._to_rest(t, s)
            else:
                self._rest_since = None
                if t - self._progress_t >= c.stall_ms:
                    # stopped part-way back up and stayed there: did not return
                    cyc.end_ms, cyc.end_signal, cyc.reason = self._max_up_t, self._max_up, "stalled"
                    self._emit(cyc, out)
                    self._to_rest(t, s)
                elif s < self._max_up - c.reverse_delta_deg:
                    # turned back down before reaching rest: close as not-returned, start next cycle here
                    cyc.end_ms, cyc.end_signal, cyc.reason = self._max_up_t, self._max_up, "reversed"
                    self._emit(cyc, out)
                    self._begin(self._max_up_t, self._max_up, s, t, from_rest=False)
        return out

    def _to_rest(self, t: float, s: float) -> None:
        self.phase, self.cycle = Phase.REST, None
        self._below_since = self._rest_since = None
        self._window.clear()
        self._push_window(t, s)

    def _abandon(self, out: list[Cycle]) -> None:
        cyc = self.cycle
        if cyc is not None:
            cyc.end_ms = self._last_valid_t or cyc.start_ms
            cyc.end_signal = self._last_signal
            cyc.reason, cyc.abandoned = "abandoned", True
            self._emit(cyc, out)
        self.phase, self.cycle, self.armed = Phase.REST, None, False
        self._window.clear()
        self._below_since = self._rest_since = None

    def flush(self, t: float) -> list[Cycle]:
        """End of stream: close any open cycle (marked truncated unless it had already returned to rest)."""
        out: list[Cycle] = []
        cyc = self.cycle
        if cyc is not None:
            if self.phase == Phase.EXTENDING and self._rest_since is not None:
                cyc.returned_to_rest, cyc.end_ms, cyc.reason = True, self._rest_since, "returned"
                cyc.end_signal = self._last_signal
            else:
                cyc.end_ms = self._last_valid_t or t
                cyc.end_signal = self._last_signal
                cyc.reason, cyc.truncated = "flush", True
            self._emit(cyc, out)
        self.phase, self.cycle = Phase.REST, None
        return out
