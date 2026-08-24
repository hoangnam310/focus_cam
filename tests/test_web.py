from __future__ import annotations

from focuscam.config import Settings
from focuscam.storage import write_json
from focuscam.web import _analysis_matches_settings, create_app


def test_home_page(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        model="test-model.pt",
        tracker="test-tracker.yaml",
        device="cpu",
        image_size=512,
    )
    app = create_app(settings)
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"Focus Cam Studio" in response.data


def test_video_list_starts_empty(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        model="test-model.pt",
        tracker="test-tracker.yaml",
        device="cpu",
        image_size=512,
    )
    app = create_app(settings)
    response = app.test_client().get("/api/videos")
    assert response.status_code == 200
    assert response.get_json() == {"videos": []}


def test_cached_analysis_must_match_current_model_settings(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        model="quality.pt",
        tracker="reid.yaml",
        device="cpu",
        image_size=640,
    )
    path = tmp_path / "tracks.json"
    write_json(path, {"model": "fast.pt", "tracker": "reid.yaml", "image_size": 512})
    assert not _analysis_matches_settings(path, settings)
    write_json(path, {"model": "quality.pt", "tracker": "reid.yaml", "image_size": 640})
    assert _analysis_matches_settings(path, settings)


def test_selection_is_saved_with_analysis(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        model="test-model.pt",
        tracker="test-tracker.yaml",
        device="cpu",
        image_size=512,
    )
    analysis_dir = settings.runs_dir / "sample-analysis"
    write_json(
        analysis_dir / "tracks.json",
        {
            "analysis_id": "sample-analysis",
            "source": {"fps": 30},
            "frames": [{"index": index, "detections": []} for index in range(4)],
            "tracks": [{"track_id": 3, "first_frame": 0, "last_frame": 3}],
        },
    )
    app = create_app(settings)
    selection = {
        "anchors": [{"frame": 0, "track_id": 3}],
        "crop_anchors": [
            {"frame": 1, "mode": "manual", "offset_x": 0.2, "offset_y": 0, "scale": 0.8}
        ],
    }

    response = app.test_client().post("/api/analyses/sample-analysis/selection", json=selection)
    assert response.status_code == 200
    assert response.get_json() == selection
    analysis = app.test_client().get("/api/analyses/sample-analysis").get_json()
    assert analysis["selection"] == selection


def test_selection_rejects_unknown_track(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        runs_dir=tmp_path / "runs",
        model="test-model.pt",
        tracker="test-tracker.yaml",
        device="cpu",
        image_size=512,
    )
    analysis_dir = settings.runs_dir / "sample-analysis"
    write_json(
        analysis_dir / "tracks.json",
        {
            "analysis_id": "sample-analysis",
            "frames": [{"index": 0, "detections": []}],
            "tracks": [{"track_id": 3, "first_frame": 0, "last_frame": 0}],
        },
    )
    app = create_app(settings)

    response = app.test_client().post(
        "/api/analyses/sample-analysis/selection",
        json={"anchors": [{"frame": 0, "track_id": 99}], "crop_anchors": []},
    )
    assert response.status_code == 400
    assert "does not appear" in response.get_json()["error"]
