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
