from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import VIDEO_SUFFIXES, Settings


def analysis_id(video_path: Path) -> str:
    stat = video_path.stat()
    identity = f"{video_path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:10]
    stem = "".join(character if character.isalnum() else "-" for character in video_path.stem)
    return f"{stem.strip('-').lower()}-{digest}"


def list_videos(settings: Settings) -> list[Path]:
    candidates: list[Path] = []
    roots = [settings.project_root, settings.project_root / "media"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES:
                candidates.append(path.resolve())
    return sorted(set(candidates), key=lambda item: item.name.lower())


def resolve_video(settings: Settings, name: str) -> Path:
    matches = {path.name: path for path in list_videos(settings)}
    if name not in matches:
        raise FileNotFoundError(f"Unknown video: {name}")
    return matches[name]


def run_dir(settings: Settings, identifier: str) -> Path:
    safe_identifier = "".join(
        character for character in identifier if character.isalnum() or character in {"-", "_"}
    )
    if not safe_identifier or safe_identifier != identifier:
        raise ValueError("Invalid analysis identifier")
    return settings.runs_dir / safe_identifier


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
