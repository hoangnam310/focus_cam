from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, send_file

from .config import Settings
from .jobs import JobManager
from .renderer import render_focus_cam
from .storage import analysis_id, list_videos, read_json, resolve_video, run_dir
from .tracker import analyze_video
from .video import probe_video


def _json_body() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise TypeError("Expected a JSON object")
    return payload


def _safe_asset(base: Path, relative: str) -> Path:
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise FileNotFoundError(relative) from exc
    if not candidate.is_file():
        raise FileNotFoundError(relative)
    return candidate


def _analysis_matches_settings(path: Path, settings: Settings) -> bool:
    if not path.is_file():
        return False
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return False
    return (
        payload.get("model") == settings.model
        and payload.get("tracker") == settings.tracker
        and int(payload.get("image_size", 0)) == settings.image_size
    )


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_environment()
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    jobs = JobManager()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    @app.errorhandler(FileNotFoundError)
    def handle_bad_request(error: Exception):
        return jsonify({"error": str(error)}), 400

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/videos")
    def videos():
        payload = []
        for path in list_videos(settings):
            try:
                info = probe_video(path)
            except (OSError, ValueError):
                continue
            identifier = analysis_id(path)
            analyzed = _analysis_matches_settings(
                run_dir(settings, identifier) / "tracks.json", settings
            )
            payload.append({**info.to_dict(), "analysis_id": identifier, "analyzed": analyzed})
        return jsonify({"videos": payload})

    @app.get("/media/<path:name>")
    def media(name: str):
        try:
            path = resolve_video(settings, Path(name).name)
        except FileNotFoundError:
            abort(404)
        return send_file(path, conditional=True)

    @app.post("/api/analyze")
    def analyze():
        payload = _json_body()
        video_path = resolve_video(settings, str(payload.get("video", "")))
        identifier = analysis_id(video_path)
        tracks_path = run_dir(settings, identifier) / "tracks.json"
        if _analysis_matches_settings(tracks_path, settings):
            return jsonify(
                {
                    "status": "completed",
                    "analysis_id": identifier,
                    "analysis_url": f"/api/analyses/{identifier}",
                }
            )

        def task(progress):
            result = analyze_video(video_path, settings, progress)
            return {
                "analysis_id": result["analysis_id"],
                "analysis_url": f"/api/analyses/{result['analysis_id']}",
            }

        job = jobs.submit("analysis", task)
        return jsonify({"status": "queued", "job_id": job.job_id}), 202

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            abort(404)
        return jsonify(job.snapshot())

    @app.get("/api/analyses/<identifier>")
    def analysis(identifier: str):
        path = run_dir(settings, identifier) / "tracks.json"
        if not path.is_file():
            abort(404)
        return jsonify(read_json(path))

    @app.get("/api/analyses/<identifier>/assets/<path:filename>")
    def analysis_asset(identifier: str, filename: str):
        try:
            path = _safe_asset(run_dir(settings, identifier), filename)
        except FileNotFoundError:
            abort(404)
        return send_file(path, conditional=True)

    @app.post("/api/render")
    def render():
        payload = _json_body()
        identifier = str(payload.get("analysis_id", ""))
        analysis_path = run_dir(settings, identifier) / "tracks.json"
        if not analysis_path.is_file():
            raise FileNotFoundError("Run analysis before rendering")
        analysis_payload = read_json(analysis_path)
        video_path = resolve_video(settings, analysis_payload["source"]["path"])
        anchors = payload.get("anchors")
        if not isinstance(anchors, list):
            raise TypeError("anchors must be a list")
        crop_anchors = payload.get("crop_anchors", [])
        if not isinstance(crop_anchors, list):
            raise TypeError("crop_anchors must be a list")
        aspect = str(payload.get("aspect", "9:16"))
        padding = float(payload.get("padding", 1.3))
        render_id = uuid.uuid4().hex[:10]
        filename = f"focus-cam-{render_id}.mp4"
        output_path = run_dir(settings, identifier) / "outputs" / filename

        def task(progress):
            rendered = render_focus_cam(
                video_path,
                analysis_payload,
                anchors,
                output_path,
                aspect_name=aspect,
                padding=padding,
                crop_anchors=crop_anchors,
                progress=progress,
            )
            return {
                "analysis_id": identifier,
                "filename": rendered.name,
                "url": f"/api/analyses/{identifier}/outputs/{rendered.name}",
            }

        job = jobs.submit("render", task)
        return jsonify({"status": "queued", "job_id": job.job_id}), 202

    @app.get("/api/analyses/<identifier>/outputs/<filename>")
    def output(identifier: str, filename: str):
        try:
            path = _safe_asset(run_dir(settings, identifier) / "outputs", Path(filename).name)
        except FileNotFoundError:
            abort(404)
        return send_file(path, conditional=True, as_attachment=False, download_name=path.name)

    return app
