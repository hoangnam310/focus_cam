from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .storage import analysis_id, run_dir, write_json
from .video import probe_video

ProgressCallback = Callable[[int, int, str], None]


def _device(settings: Settings) -> str | None:
    if settings.device:
        return settings.device
    try:
        import torch

        if torch.cuda.is_available():
            return "0"
        if torch.backends.mps.is_available():
            return "mps"
    except (ImportError, AttributeError):
        pass
    return "cpu"


def analyze_video(
    video_path: Path,
    settings: Settings,
    progress: ProgressCallback | None = None,
    *,
    max_frames: int | None = None,
) -> dict[str, Any]:
    """Detect and track every person in a video with persistent track IDs."""
    import cv2
    from ultralytics import YOLO

    info = probe_video(video_path)
    expected_frames = min(info.frame_count, max_frames) if max_frames else info.frame_count
    identifier = analysis_id(video_path)
    destination = run_dir(settings, identifier)
    thumbnails_dir = destination / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress(0, expected_frames, f"Loading {settings.model}")

    model = YOLO(settings.model)
    device = _device(settings)
    results = model.track(
        source=str(video_path),
        stream=True,
        persist=True,
        classes=[0],
        conf=0.18,
        iou=0.55,
        tracker=settings.tracker,
        device=device,
        imgsz=settings.image_size,
        verbose=False,
    )

    frames: list[dict[str, Any]] = []
    track_summaries: dict[int, dict[str, Any]] = {}
    best_samples: dict[int, tuple[float, Any]] = {}

    for frame_index, result in enumerate(results):
        if max_frames is not None and frame_index >= max_frames:
            break
        detections: list[dict[str, Any]] = []
        boxes = result.boxes
        if boxes is not None and boxes.id is not None:
            ids = boxes.id.int().cpu().tolist()
            coordinates = boxes.xyxy.cpu().tolist()
            confidences = boxes.conf.cpu().tolist()
            for track_id, bbox, confidence in zip(ids, coordinates, confidences, strict=True):
                rounded_box = [round(float(value), 2) for value in bbox]
                detection = {
                    "track_id": int(track_id),
                    "bbox": rounded_box,
                    "confidence": round(float(confidence), 4),
                }
                detections.append(detection)

                summary = track_summaries.setdefault(
                    int(track_id),
                    {
                        "track_id": int(track_id),
                        "first_frame": frame_index,
                        "last_frame": frame_index,
                        "observations": 0,
                        "thumbnail_frame": frame_index,
                        "max_bbox_height": 0.0,
                        "max_bbox_area": 0.0,
                    },
                )
                summary["last_frame"] = frame_index
                summary["observations"] += 1

                x1, y1, x2, y2 = rounded_box
                area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
                summary["max_bbox_height"] = max(summary["max_bbox_height"], max(0.0, y2 - y1))
                summary["max_bbox_area"] = max(summary["max_bbox_area"], area)
                sample_score = area * float(confidence)
                if sample_score > best_samples.get(int(track_id), (-1.0, None))[0]:
                    height, width = result.orig_img.shape[:2]
                    left = max(0, int(x1))
                    top = max(0, int(y1))
                    right = min(width, int(x2))
                    bottom = min(height, int(y2))
                    if right > left and bottom > top:
                        best_samples[int(track_id)] = (
                            sample_score,
                            result.orig_img[top:bottom, left:right].copy(),
                        )
                        summary["thumbnail_frame"] = frame_index

        frames.append(
            {
                "index": frame_index,
                "timestamp": round(frame_index / info.fps, 4),
                "detections": detections,
            }
        )
        if progress and (frame_index % 10 == 0 or frame_index + 1 == expected_frames):
            progress(frame_index + 1, expected_frames, "Tracking every performer")

    for track_id, (_, image) in best_samples.items():
        thumbnail_path = thumbnails_dir / f"track-{track_id}.jpg"
        cv2.imwrite(str(thumbnail_path), image)
        track_summaries[track_id]["thumbnail"] = f"thumbnails/{thumbnail_path.name}"

    for summary in track_summaries.values():
        summary["gallery"] = bool(
            summary["observations"] >= max(8, round(info.fps * 0.5))
            and summary["max_bbox_height"] >= info.height * 0.12
        )
        summary["max_bbox_height"] = round(summary["max_bbox_height"], 2)
        summary["max_bbox_area"] = round(summary["max_bbox_area"], 2)

    payload: dict[str, Any] = {
        "version": 1,
        "analysis_id": identifier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": info.to_dict(),
        "model": settings.model,
        "tracker": settings.tracker,
        "image_size": settings.image_size,
        "device": device,
        "processed_frames": len(frames),
        "tracks": sorted(track_summaries.values(), key=lambda item: item["track_id"]),
        "frames": frames,
    }
    write_json(destination / "tracks.json", payload)
    if progress:
        progress(len(frames), len(frames), f"Found {len(track_summaries)} tracks")
    return payload
