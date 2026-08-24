from __future__ import annotations

import pytest

from focuscam.camera import (
    apply_crop_overrides,
    build_camera_windows,
    normalize_anchors,
    normalize_crop_anchors,
    parse_aspect,
    selected_boxes,
    selected_track_ids,
)


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


def test_offscreen_segment_has_no_active_track_or_box() -> None:
    anchors = [
        {"frame": 0, "track_id": 3},
        {"frame": 3, "track_id": None, "mode": "absent"},
        {"frame": 6, "track_id": 7},
    ]
    assert selected_track_ids(anchors, 8) == [3, 3, 3, None, None, None, 7, 7]
    boxes = selected_boxes(_frames(), anchors)
    assert boxes[2] == [12, 20, 32, 80]
    assert boxes[3:6] == [None, None, None]
    assert boxes[6] == [64, 30, 84, 90]


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


def test_camera_window_preserves_headroom_after_fast_motion() -> None:
    frames = [
        {"index": 0, "detections": [{"track_id": 3, "bbox": [50, 20, 90, 100]}]},
        {"index": 1, "detections": [{"track_id": 3, "bbox": [50, 80, 90, 160]}]},
    ]
    windows = build_camera_windows(
        frames,
        [{"frame": 0, "track_id": 3}],
        frame_width=180,
        frame_height=220,
        fps=30,
        aspect=9 / 16,
        padding=1.3,
    )
    for (_, top, _, height), bbox in zip(windows, ([50, 20, 90, 100], [50, 80, 90, 160])):
        person_height = bbox[3] - bbox[1]
        assert top <= bbox[1] - person_height * 0.10
        assert top + height >= bbox[3]


def test_camera_centers_performer_or_clamps_at_source_edge() -> None:
    centered = [{"index": 0, "detections": [{"track_id": 3, "bbox": [80, 50, 120, 150]}]}]
    edge = [{"index": 0, "detections": [{"track_id": 3, "bbox": [0, 50, 40, 150]}]}]
    kwargs = {
        "raw_anchors": [{"frame": 0, "track_id": 3}],
        "frame_width": 200,
        "frame_height": 200,
        "fps": 30,
        "aspect": 1,
        "padding": 1.3,
    }
    left, _, width, _ = build_camera_windows(centered, **kwargs)[0]
    assert left + width / 2 == pytest.approx(100, abs=1)
    edge_left, _, edge_width, _ = build_camera_windows(edge, **kwargs)[0]
    assert edge_left == 0
    assert edge_left + edge_width / 2 > 20


def test_camera_path_suppresses_detector_jitter() -> None:
    noise = [-5, 4, -3, 5, 0, -4, 3]
    frames = []
    for index in range(120):
        horizontal = noise[index % len(noise)]
        size = noise[(index * 3) % len(noise)]
        frames.append(
            {
                "index": index,
                "detections": [
                    {
                        "track_id": 3,
                        "bbox": [
                            150 + horizontal,
                            100 + horizontal / 2,
                            250 + horizontal,
                            400 + horizontal / 2 + size,
                        ],
                    }
                ],
            }
        )

    windows = build_camera_windows(
        frames,
        [{"frame": 0, "track_id": 3}],
        frame_width=500,
        frame_height=600,
        fps=30,
        aspect=9 / 16,
        padding=1.15,
    )
    stable = windows[10:-10]
    centers_x = [left + width / 2 for left, _, width, _ in stable]
    centers_y = [top + height / 2 for _, top, _, height in stable]
    heights = [height for _, _, _, height in stable]
    assert max(centers_x) - min(centers_x) <= 2
    assert max(centers_y) - min(centers_y) <= 2
    assert max(heights) - min(heights) <= 2


def test_offscreen_segment_eases_to_wide_centered_frame() -> None:
    frames = [
        {"index": index, "detections": [{"track_id": 3, "bbox": [20, 50, 60, 150]}]}
        for index in range(120)
    ]
    windows = build_camera_windows(
        frames,
        [
            {"frame": 0, "track_id": 3},
            {"frame": 30, "track_id": None, "mode": "absent"},
            {"frame": 90, "track_id": 3},
        ],
        frame_width=200,
        frame_height=200,
        fps=30,
        aspect=1,
        padding=1.3,
    )
    left, top, width, height = windows[60]
    assert width >= 195
    assert height >= 195
    assert left == pytest.approx(0, abs=3)
    assert top == pytest.approx(0, abs=3)


def test_manual_crop_override_moves_and_resizes_auto_window() -> None:
    windows = [(50, 40, 100, 160)] * 5
    adjusted = apply_crop_overrides(
        windows,
        [{"frame": 2, "mode": "manual", "offset_x": 0.25, "offset_y": -0.1, "scale": 0.75}],
        frame_width=300,
        frame_height=300,
        aspect=100 / 160,
    )
    assert adjusted[:2] == windows[:2]
    left, top, width, height = adjusted[2]
    assert width == pytest.approx(75, abs=1)
    assert height == pytest.approx(120, abs=1)
    assert left + width / 2 == pytest.approx(125, abs=1)
    assert top + height / 2 == pytest.approx(104, abs=1)


def test_manual_crop_can_return_to_auto_and_stays_inside_source() -> None:
    windows = [(0, 20, 100, 160)] * 5
    adjusted = apply_crop_overrides(
        windows,
        [
            {"frame": 1, "mode": "manual", "offset_x": -1.0, "offset_y": 0, "scale": 1.5},
            {"frame": 3, "mode": "auto"},
        ],
        frame_width=200,
        frame_height=300,
        aspect=100 / 160,
    )
    assert adjusted[0] == windows[0]
    assert adjusted[3:] == windows[3:]
    for left, top, width, height in adjusted:
        assert left >= 0 and top >= 0
        assert left + width <= 200
        assert top + height <= 300


def test_manual_crop_validation_rejects_invalid_scale() -> None:
    with pytest.raises(ValueError, match="scale"):
        normalize_crop_anchors([{"frame": 0, "scale": 3}], frame_count=1)


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
