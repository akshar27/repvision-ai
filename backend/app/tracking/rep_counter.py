"""Collects RepEvents for a session and exposes running totals."""
from __future__ import annotations

from ..models.schemas import RepEvent, RepSummary


class RepCounter:
    def __init__(self) -> None:
        self.reps: list[RepEvent] = []

    def reset(self) -> None:
        self.reps.clear()

    def add(self, rep: RepEvent) -> None:
        self.reps.append(rep)

    @property
    def summary(self) -> RepSummary:
        s = RepSummary(total=len(self.reps))
        for r in self.reps:
            setattr(s, r.classification, getattr(s, r.classification) + 1)
        return s
