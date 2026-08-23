from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


@dataclass(frozen=True)
class Settings:
    project_root: Path
    runs_dir: Path
    model: str
    tracker: str
    device: str | None
    image_size: int

    @classmethod
    def from_environment(cls) -> Settings:
        default_root = Path(__file__).resolve().parents[2]
        project_root = Path(os.getenv("FOCUSCAM_ROOT", default_root)).resolve()
        runs_dir = Path(os.getenv("FOCUSCAM_RUNS_DIR", project_root / "runs")).resolve()
        return cls(
            project_root=project_root,
            runs_dir=runs_dir,
            model=os.getenv("FOCUSCAM_MODEL", "yolo11n.pt"),
            tracker=os.getenv("FOCUSCAM_TRACKER", "botsort.yaml"),
            device=os.getenv("FOCUSCAM_DEVICE") or None,
            image_size=int(os.getenv("FOCUSCAM_IMAGE_SIZE", "512")),
        )
