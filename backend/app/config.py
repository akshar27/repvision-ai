from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REPVISION_", env_file=str(ROOT / ".env"), extra="ignore")

    data_dir: Path = ROOT / "data"
    assets_dir: Path = ROOT / "backend" / "assets"
    pose_model: str = "full"               # lite | full | heavy
    max_upload_mb: int = 300
    max_video_seconds: int = 600
    inference_max_side: int = 640          # frames are downscaled for the pose model only
    frame_stride: int = 1
    smoothing_tau_ms: float = 60.0
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    worker_threads: int = 1                # analysis jobs run in-process; keep small
    allowed_extensions: str = ".mp4,.mov,.m4v,.avi,.mkv,.webm"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def annotations_dir(self) -> Path:
        return self.data_dir / "annotations"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}


settings = Settings()
