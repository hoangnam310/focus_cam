from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Anchor:
    frame: int
    track_id: int


def parse_aspect(value: str) -> float:
    try:
        width, height = (float(part) for part in value.split(":", maxsplit=1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Aspect ratio must look like 9:16") from exc
    if width <= 0 or height <= 0:
        raise ValueError("Aspect ratio values must be positive")
    return width / height


def normalize_anchors(raw_anchors: list[dict[str, Any]], frame_count: int) -> list[Anchor]:
    if not raw_anchors:
        raise ValueError("Select at least one performer before rendering")

    by_frame: dict[int, Anchor] = {}
    for raw in raw_anchors:
        frame = int(raw["frame"])
        track_id = int(raw["track_id"])
        if frame < 0 or frame >= frame_count:
            raise ValueError(f"Anchor frame {frame} is outside the analyzed video")
        if track_id < 0:
            raise ValueError("Track IDs must be non-negative")
        by_frame[frame] = Anchor(frame=frame, track_id=track_id)

    anchors = sorted(by_frame.values(), key=lambda anchor: anchor.frame)
    first = anchors[0]
    if first.frame != 0:
        anchors[0] = Anchor(frame=0, track_id=first.track_id)
    return anchors


def selected_boxes(
    frames: list[dict[str, Any]], raw_anchors: list[dict[str, Any]]
) -> list[list[float] | None]:
    anchors = normalize_anchors(raw_anchors, len(frames))
    output: list[list[float] | None] = []
    anchor_index = 0
    active_track = anchors[0].track_id

    for frame_index, frame in enumerate(frames):
        while anchor_index + 1 < len(anchors) and anchors[anchor_index + 1].frame <= frame_index:
            anchor_index += 1
            active_track = anchors[anchor_index].track_id
        match = next(
            (
                detection["bbox"]
                for detection in frame.get("detections", [])
                if int(detection["track_id"]) == active_track
            ),
            None,
        )
        output.append(match)
    return output


def _blend(start: float, end: float, fraction: float) -> float:
    eased = fraction * fraction * (3.0 - 2.0 * fraction)
    return start + (end - start) * eased


def _fill_missing(values: np.ndarray, fallback: float, max_gap: int) -> np.ndarray:
    observed = np.flatnonzero(~np.isnan(values))
    if not len(observed):
        raise ValueError("The selected track does not appear in the analysis")

    filled = values.copy()
    first, last = int(observed[0]), int(observed[-1])
    for index in range(first):
        fraction = (index + 1) / (first + 1)
        filled[index] = _blend(fallback, values[first], fraction)
    for index in range(last + 1, len(values)):
        fraction = (index - last) / max(1, len(values) - 1 - last)
        filled[index] = _blend(values[last], fallback, fraction)

    for left, right in pairwise(observed):
        left = int(left)
        right = int(right)
        gap = right - left - 1
        if gap <= 0:
            continue
        if gap <= max_gap:
            for offset in range(1, gap + 1):
                filled[left + offset] = _blend(values[left], values[right], offset / (gap + 1))
            continue

        midpoint = left + (right - left) // 2
        for index in range(left + 1, midpoint + 1):
            fraction = (index - left) / max(1, midpoint - left)
            filled[index] = _blend(values[left], fallback, fraction)
        for index in range(midpoint + 1, right):
            fraction = (index - midpoint) / max(1, right - midpoint)
            filled[index] = _blend(fallback, values[right], fraction)
    return filled


def _smooth(values: np.ndarray, alpha: float) -> np.ndarray:
    forward = values.copy()
    for index in range(1, len(forward)):
        forward[index] = alpha * forward[index] + (1.0 - alpha) * forward[index - 1]
    backward = values.copy()
    for index in range(len(backward) - 2, -1, -1):
        backward[index] = alpha * backward[index] + (1.0 - alpha) * backward[index + 1]
    return (forward + backward) / 2.0


def build_camera_windows(
    frames: list[dict[str, Any]],
    raw_anchors: list[dict[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
    fps: float,
    aspect: float,
    padding: float = 1.3,
) -> list[tuple[int, int, int, int]]:
    if not 1.0 <= padding <= 2.5:
        raise ValueError("Padding must be between 1.0 and 2.5")

    boxes = selected_boxes(frames, raw_anchors)
    count = len(boxes)
    center_x = np.full(count, np.nan, dtype=np.float64)
    center_y = np.full(count, np.nan, dtype=np.float64)
    crop_height = np.full(count, np.nan, dtype=np.float64)
    maximum_height = min(float(frame_height), float(frame_width) / aspect)
    minimum_height = maximum_height * 0.34

    for index, bbox in enumerate(boxes):
        if bbox is None:
            continue
        x1, y1, x2, y2 = (float(value) for value in bbox)
        person_height = max(1.0, y2 - y1)
        extra_padding = max(0.0, padding - 1.0)
        center_x[index] = (x1 + x2) / 2.0
        # Put roughly two-thirds of the extra vertical room above the performer.
        # Faces are visually less forgiving than feet when detections move quickly.
        center_y[index] = (y1 + y2) / 2.0 - person_height * extra_padding * 0.18
        crop_height[index] = np.clip(person_height * padding, minimum_height, maximum_height)

    max_gap = max(1, round(fps * 1.2))
    center_x = _fill_missing(center_x, frame_width / 2.0, max_gap)
    center_y = _fill_missing(center_y, frame_height / 2.0, max_gap)
    crop_height = _fill_missing(crop_height, maximum_height, max_gap)
    center_x = _smooth(center_x, alpha=0.18)
    center_y = _smooth(center_y, alpha=0.18)
    crop_height = _smooth(crop_height, alpha=0.10)

    windows: list[tuple[int, int, int, int]] = []
    for index, (cx, cy, height) in enumerate(zip(center_x, center_y, crop_height, strict=True)):
        height = float(np.clip(height, minimum_height, maximum_height))
        width = height * aspect

        # Smoothing must never lag far enough to cut off the current head. Expand
        # and reposition the window to contain a small safety envelope whenever a
        # real detection is available. If the full envelope cannot fit, prioritize
        # the top/head edge.
        bbox = boxes[index]
        if bbox is not None:
            x1, y1, x2, y2 = (float(value) for value in bbox)
            person_height = max(1.0, y2 - y1)
            person_width = max(1.0, x2 - x1)
            safe_top = max(0.0, y1 - person_height * 0.12)
            safe_bottom = min(float(frame_height), y2 + person_height * 0.04)
            safe_left = max(0.0, x1 - person_width * 0.06)
            safe_right = min(float(frame_width), x2 + person_width * 0.06)
            required_height = max(safe_bottom - safe_top, (safe_right - safe_left) / aspect)
            height = float(np.clip(max(height, required_height), minimum_height, maximum_height))
            width = height * aspect

            vertical_lower = safe_bottom - height / 2.0
            vertical_upper = safe_top + height / 2.0
            cy = (
                float(np.clip(cy, vertical_lower, vertical_upper))
                if vertical_lower <= vertical_upper
                else safe_top + height / 2.0
            )
            horizontal_lower = safe_right - width / 2.0
            horizontal_upper = safe_left + width / 2.0
            cx = (
                float(np.clip(cx, horizontal_lower, horizontal_upper))
                if horizontal_lower <= horizontal_upper
                else (safe_left + safe_right) / 2.0
            )

        cx = float(np.clip(cx, width / 2.0, frame_width - width / 2.0))
        cy = float(np.clip(cy, height / 2.0, frame_height - height / 2.0))
        left = round(cx - width / 2.0)
        top = round(cy - height / 2.0)
        windows.append((left, top, max(2, round(width)), max(2, round(height))))
    return windows
