from __future__ import annotations

from focuscam.config import Settings
from focuscam.web import create_app


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
