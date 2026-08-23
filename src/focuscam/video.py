from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class VideoInfo:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration: float
    has_audio: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _fps(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    return float(Fraction(value))


def probe_video(path: Path) -> VideoInfo:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,avg_frame_rate,r_frame_rate,nb_frames",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    video_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError(f"No video stream found in {path.name}")

    duration = float(payload.get("format", {}).get("duration") or 0.0)
    fps = _fps(video_stream.get("avg_frame_rate")) or _fps(video_stream.get("r_frame_rate"))
    raw_count = video_stream.get("nb_frames")
    frame_count = int(raw_count) if raw_count not in (None, "N/A") else round(duration * fps)
    return VideoInfo(
        path=path.name,
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=fps,
        frame_count=frame_count,
        duration=duration,
        has_audio=any(stream.get("codec_type") == "audio" for stream in payload.get("streams", [])),
    )


def even(value: int) -> int:
    """Return the closest positive even integer at or below value."""
    return max(2, value - (value % 2))
