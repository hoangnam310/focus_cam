from __future__ import annotations

import pytest

from focuscam.camera import build_camera_windows, normalize_anchors, parse_aspect, selected_boxes


def _frames() -> list[dict]:
    return [
        {
            "index": index,
            "detections": [
                {"track_id": 3, "bbox": [10 + index, 20, 30 + index, 80]},
                {"track_id": 7, "bbox": [70 - index, 30, 90 - index, 90]},
            ],
        }
        for index in range(8)
    ]


def test_parse_aspect() -> None:
    assert parse_aspect("9:16") == pytest.approx(9 / 16)
    assert parse_aspect("1:1") == 1
    with pytest.raises(ValueError):
        parse_aspect("portrait")


def test_first_anchor_applies_to_start() -> None:
    anchors = normalize_anchors([{"frame": 4, "track_id": 7}], frame_count=8)
    assert anchors[0].frame == 0
    assert anchors[0].track_id == 7


def test_selected_boxes_switch_at_correction_anchor() -> None:
    boxes = selected_boxes(
        _frames(),
        [{"frame": 0, "track_id": 3}, {"frame": 5, "track_id": 7}],
    )
    assert boxes[4] == [14, 20, 34, 80]
    assert boxes[5] == [65, 30, 85, 90]


def test_camera_windows_stay_inside_source() -> None:
    windows = build_camera_windows(
        _frames(),
        [{"frame": 0, "track_id": 3}],
        frame_width=100,
        frame_height=120,
        fps=30,
        aspect=9 / 16,
        padding=1.3,
    )
    assert len(windows) == 8
    for left, top, width, height in windows:
        assert left >= 0
        assert top >= 0
        assert left + width <= 100
        assert top + height <= 120


def test_missing_track_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not appear"):
        build_camera_windows(
            _frames(),
            [{"frame": 0, "track_id": 999}],
            frame_width=100,
            frame_height=120,
            fps=30,
            aspect=9 / 16,
        )
