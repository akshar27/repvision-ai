"""Exercise configuration, sensitivity presets and calibration payloads.

All angle thresholds are 2D image-plane joint angles (degrees). They are
*defaults to be calibrated*, not universal truths: camera angle, limb
proportions and mobility all change what a "full" repetition looks like.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ExerciseName = Literal["squat", "pushup", "pullup"]
Preset = Literal["lenient", "standard", "strict"]
EXERCISES: tuple[str, ...] = ("squat", "pushup", "pullup")
PRESETS: tuple[str, ...] = ("lenient", "standard", "strict")


class MachineConfig(BaseModel):
    """Thresholds of the generic flexion/extension repetition state machine.

    The tracked signal is a joint angle that is LARGE at rest (extended) and
    SMALL at the peak of the movement (flexed).
    """
    model_config = ConfigDict(extra="forbid")

    rest_enter_deg: float = Field(160, ge=100, le=179)     # >= this means "at rest/extended"
    leave_delta_deg: float = Field(10, ge=2, le=40)        # drop from recent max that starts a movement
    full_depth_deg: float = Field(100, ge=20, le=170)      # <= this means the depth criterion is reached
    partial_min_deg: float = Field(140, ge=30, le=178)     # must dip to <= this to count as a rep attempt
    reverse_delta_deg: float = Field(8, ge=2, le=30)       # hysteresis for direction changes
    min_phase_ms: float = Field(60, ge=0, le=2000)         # dwell required to enter peak / return to rest
    min_rep_ms: float = Field(500, ge=100, le=10000)       # shorter cycles are discarded as noise
    max_gap_ms: float = Field(400, ge=50, le=5000)         # tracking gap inside a rep that voids it (uncertain)
    abandon_ms: float = Field(3000, ge=200, le=60000)      # tracking lost this long => abandon the cycle
    ref_window_ms: float = Field(1500, ge=200, le=10000)   # window for the recent-max reference at rest
    stall_ms: float = Field(1500, ge=300, le=20000)        # stopped part-way back up this long => did not return
    start_lead_ms: float = Field(700, ge=0, le=10000)      # movement this soon after the first valid frame => mid-rep start

    @model_validator(mode="after")
    def _ordered(self) -> "MachineConfig":
        if not (self.full_depth_deg < self.partial_min_deg < self.rest_enter_deg):
            raise ValueError("require full_depth_deg < partial_min_deg < rest_enter_deg")
        return self


class BaseExerciseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: Preset = "standard"
    machine: MachineConfig
    min_visibility: float = Field(0.5, ge=0.1, le=0.99)
    smoothing_tau_ms: float = Field(60, ge=0, le=500)
    min_rep_coverage: float = Field(0.6, ge=0.1, le=1.0)   # share of valid frames needed to trust a rep
    max_signal_speed_dps: float = Field(1500, ge=100, le=20000)  # outlier guard (deg/s)


class SquatConfig(BaseExerciseConfig):
    exercise: Literal["squat"] = "squat"
    machine: MachineConfig = MachineConfig(rest_enter_deg=160, full_depth_deg=100, partial_min_deg=140)
    require_hip_below_knee: bool = False
    hip_below_knee_ratio: float = Field(0.0, ge=-0.5, le=1.0)   # (hip_y-knee_y)/thigh_len needed when required
    torso_lean_warn_deg: float = Field(60, ge=20, le=89)


class PushupConfig(BaseExerciseConfig):
    exercise: Literal["pushup"] = "pushup"
    machine: MachineConfig = MachineConfig(rest_enter_deg=155, full_depth_deg=95, partial_min_deg=135)
    min_shoulder_drop_ratio: float = Field(0.08, ge=0.0, le=1.0)   # shoulder drop / torso length
    sag_warn_ratio: float = Field(0.08, ge=0.01, le=0.5)           # hip below shoulder-ankle line / line length
    pike_warn_ratio: float = Field(0.10, ge=0.01, le=0.5)
    plank_max_angle_deg: float = Field(45, ge=10, le=80)           # shoulder-hip line vs horizontal


class PullupConfig(BaseExerciseConfig):
    exercise: Literal["pullup"] = "pullup"
    machine: MachineConfig = MachineConfig(rest_enter_deg=155, full_depth_deg=90, partial_min_deg=130)
    min_travel_ratio: float = Field(0.30, ge=0.0, le=1.5)          # shoulder rise / arm length
    bar_y: float | None = Field(None, ge=0.0, le=1.0)              # bar height, fraction of frame height (0=top)
    top_reference: Literal["mouth", "nose"] = "mouth"              # no chin landmark exists; mouth is the conservative proxy
    clearance_margin_ratio: float = Field(0.0, ge=-0.5, le=0.5)    # reference must be this far above bar (x arm length)
    require_bar_for_full: bool = True


ExerciseConfig = SquatConfig | PushupConfig | PullupConfig
_CLASSES = {"squat": SquatConfig, "pushup": PushupConfig, "pullup": PullupConfig}

# Preset deltas relative to the standard defaults.
_PRESET_DELTAS: dict[str, dict[str, dict[str, float | bool]]] = {
    "squat": {
        "lenient": {"machine.full_depth_deg": 110, "machine.rest_enter_deg": 155, "machine.partial_min_deg": 145},
        "standard": {},
        "strict": {"machine.full_depth_deg": 90, "machine.rest_enter_deg": 165, "require_hip_below_knee": True},
    },
    "pushup": {
        "lenient": {"machine.full_depth_deg": 105, "machine.rest_enter_deg": 150, "min_shoulder_drop_ratio": 0.05},
        "standard": {},
        "strict": {"machine.full_depth_deg": 85, "machine.rest_enter_deg": 160, "min_shoulder_drop_ratio": 0.12},
    },
    "pullup": {
        "lenient": {"machine.full_depth_deg": 100, "machine.rest_enter_deg": 150, "min_travel_ratio": 0.22},
        "standard": {},
        "strict": {"machine.full_depth_deg": 80, "machine.rest_enter_deg": 165, "min_travel_ratio": 0.38,
                   "clearance_margin_ratio": 0.05},
    },
}


class CalibrationInput(BaseModel):
    """User-supplied calibration. Safe to save/load as JSON."""
    model_config = ConfigDict(extra="forbid")

    exercise: ExerciseName | None = None
    preset: Preset = "standard"
    # flat or dotted overrides, e.g. {"machine.full_depth_deg": 95, "bar_y": 0.2}
    overrides: dict[str, float | bool | str | None] = Field(default_factory=dict)
    bar_y: float | None = Field(None, ge=0.0, le=1.0)
    notes: str | None = Field(None, max_length=500)


class CalibrationError(ValueError):
    pass


def _set_dotted(data: dict, key: str, value) -> None:
    parts = key.split(".")
    cur = data
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def build_config(exercise: str, preset: str = "standard", overrides: dict | None = None,
                 bar_y: float | None = None) -> ExerciseConfig:
    """Defaults -> preset deltas -> user overrides; validated (raises CalibrationError)."""
    if exercise not in _CLASSES:
        raise CalibrationError(f"Unknown exercise '{exercise}'. Choose from {list(EXERCISES)}.")
    if preset not in PRESETS:
        raise CalibrationError(f"Unknown preset '{preset}'. Choose from {list(PRESETS)}.")
    cls = _CLASSES[exercise]
    base = cls().model_dump()
    for k, v in _PRESET_DELTAS[exercise][preset].items():
        _set_dotted(base, k, v)
    for k, v in (overrides or {}).items():
        _set_dotted(base, k, v)
    if bar_y is not None:
        if exercise != "pullup":
            raise CalibrationError("bar_y only applies to pull-ups.")
        base["bar_y"] = bar_y
    base["preset"] = preset
    try:
        return cls.model_validate(base)
    except ValidationError as e:
        msgs = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise CalibrationError(f"Invalid calibration: {msgs}") from e


def config_from_calibration(exercise: str, cal: CalibrationInput | None, preset: str | None = None) -> ExerciseConfig:
    if cal is None:
        return build_config(exercise, preset or "standard")
    if cal.exercise is not None and cal.exercise != exercise:
        raise CalibrationError(f"Calibration was saved for '{cal.exercise}', not '{exercise}'.")
    return build_config(exercise, preset or cal.preset, cal.overrides, cal.bar_y)
