# Focus Cam Studio

Focus Cam Studio analyzes a performance once, tracks every visible person, and lets you
manually choose who the camera should follow. It does not identify anyone by name or face.

The local browser interface supports:

- person detection and multi-object tracking;
- click-to-follow selection directly on the video;
- a thumbnail gallery of every detected track;
- correction anchors when a track changes after an overlap or cut;
- smooth virtual-camera motion with safe behavior while the target is lost;
- 9:16, 4:5, 1:1, and 16:9 H.264 exports with the original audio.

## Requirements

- Python 3.10–3.13
- FFmpeg and FFprobe available on `PATH`
- An Apple Silicon, NVIDIA, or CPU PyTorch installation

The default detector is `yolo11n.pt` with BoT-SORT. Ultralytics downloads the small model
file on first use. Review the licenses of Ultralytics and any model weights before using
this in a distributed or commercial product.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On macOS, install FFmpeg with `brew install ffmpeg` if it is not already available.

## Run

Place performance videos in the project root or in a `media/` directory, then start the
local interface:

```bash
focus-cam serve
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080), choose a video, and click **Analyze
performers**. After analysis:

1. Pause on a clear frame and click the desired performer, or choose a track card.
2. Scrub through the video to review the selection.
3. If the tracker changes identity, pause there and click the correct performer. This adds
   a correction anchor from that point forward.
4. Choose the framing and render the focus cam.

Analysis files, thumbnails, selection metadata, and exports are written under `runs/`.
The source media, model weights, and generated files are ignored by Git.

## Command-line analysis

The browser starts analysis for you, but the same step can run without the UI:

```bash
focus-cam analyze performance.mp4
```

For a short pipeline check:

```bash
focus-cam analyze performance.mp4 --max-frames 120
```

## Configuration

Environment variables can override the defaults:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FOCUSCAM_MODEL` | `yolo11n.pt` | Ultralytics detection model |
| `FOCUSCAM_TRACKER` | `botsort.yaml` | Ultralytics tracker configuration |
| `FOCUSCAM_DEVICE` | auto | `cpu`, `mps`, or a CUDA device such as `0` |
| `FOCUSCAM_IMAGE_SIZE` | `512` | Detector input size; larger is slower but finds smaller people |
| `FOCUSCAM_ROOT` | project root | Directory scanned for source videos |
| `FOCUSCAM_RUNS_DIR` | `runs/` | Generated analysis and output directory |

## Tests

```bash
pytest -q
ruff check src tests
```

The code separates tracking, selection, camera-path generation, and rendering so future
versions can add scene boundaries, track-fragment merging, pose-aware framing, or a
different detector without replacing the interface.
