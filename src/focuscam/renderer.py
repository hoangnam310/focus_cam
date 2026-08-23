from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .camera import build_camera_windows, parse_aspect
from .storage import write_json
from .video import even

ProgressCallback = Callable[[int, int, str], None]


def _output_size(width: int, height: int, aspect: float) -> tuple[int, int]:
    output_height = even(min(height, 1280))
    output_width = even(round(output_height * aspect))
    if output_width > width:
        output_width = even(width)
        output_height = even(round(output_width / aspect))
    return output_width, output_height


def render_focus_cam(
    video_path: Path,
    analysis: dict[str, Any],
    anchors: list[dict[str, Any]],
    output_path: Path,
    *,
    aspect_name: str = "9:16",
    padding: float = 1.3,
    progress: ProgressCallback | None = None,
) -> Path:
    import cv2

    source = analysis["source"]
    fps = float(source["fps"])
    frame_width = int(source["width"])
    frame_height = int(source["height"])
    frames = analysis["frames"]
    aspect = parse_aspect(aspect_name)
    windows = build_camera_windows(
        frames,
        anchors,
        frame_width=frame_width,
        frame_height=frame_height,
        fps=fps,
        aspect=aspect,
        padding=padding,
    )
    output_width, output_height = _output_size(frame_width, frame_height, aspect)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{output_width}x{output_height}",
        "-r",
        f"{fps:.8f}",
        "-i",
        "-",
        "-i",
        str(video_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    capture = cv2.VideoCapture(str(video_path))
    processed = 0
    try:
        while processed < len(windows):
            ok, frame = capture.read()
            if not ok:
                break
            left, top, width, height = windows[processed]
            crop = frame[top : top + height, left : left + width]
            resized = cv2.resize(
                crop,
                (output_width, output_height),
                interpolation=cv2.INTER_LANCZOS4 if width < output_width else cv2.INTER_AREA,
            )
            if encoder.stdin is None:
                raise RuntimeError("FFmpeg input pipe is unavailable")
            encoder.stdin.write(resized.tobytes())
            processed += 1
            if progress and (processed % 15 == 0 or processed == len(windows)):
                progress(processed, len(windows), "Rendering the focus cam")
    except Exception:
        encoder.kill()
        raise
    finally:
        capture.release()
        if encoder.stdin:
            encoder.stdin.close()

    stderr = encoder.stderr.read().decode("utf-8", errors="replace") if encoder.stderr else ""
    return_code = encoder.wait()
    if return_code != 0:
        raise RuntimeError(f"FFmpeg failed: {stderr.strip() or f'exit code {return_code}'}")
    if processed == 0:
        raise RuntimeError("No frames were rendered")

    write_json(
        output_path.with_suffix(".json"),
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": video_path.name,
            "analysis_id": analysis["analysis_id"],
            "anchors": anchors,
            "aspect": aspect_name,
            "padding": padding,
            "output": {
                "path": output_path.name,
                "width": output_width,
                "height": output_height,
                "frames": processed,
            },
        },
    )
    return output_path
