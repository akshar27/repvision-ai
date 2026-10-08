from .config import EXERCISES, CalibrationInput, build_config, config_from_calibration
from .pullup import PullupAnalyzer
from .pushup import PushupAnalyzer
from .squat import SquatAnalyzer

ANALYZERS = {"squat": SquatAnalyzer, "pushup": PushupAnalyzer, "pullup": PullupAnalyzer}


def create_analyzer(exercise: str, cfg=None, preset: str = "standard"):
    cfg = cfg or build_config(exercise, preset)
    return ANALYZERS[exercise](cfg)


__all__ = ["EXERCISES", "ANALYZERS", "CalibrationInput", "build_config", "config_from_calibration", "create_analyzer"]
