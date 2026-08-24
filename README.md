# Focus Cam Studio

Focus Cam Studio analyzes a performance once, tracks every visible person, and lets you
manually choose who the camera should follow. It does not identify anyone by name or face.

The local browser interface supports:

- person detection and multi-object tracking;
- click-to-follow selection directly on the video;
- a thumbnail gallery of every detected track;
- a persistent timeline of track changes after overlaps or cuts;
- explicit off-screen segments that ease to a centered wide-stage frame;
- a live output-crop preview centered on the selected bounding box;
- draggable, resizable crop corrections that keep the chosen aspect ratio;
- 9:16, 4:5, 1:1, and 16:9 H.264 exports with the original audio.

## Requirements

- Python 3.10–3.13
- FFmpeg and FFprobe available on `PATH`
- An Apple Silicon, NVIDIA, or CPU PyTorch installation

The accuracy-first default is `yolo11s.pt` at 640 pixels with appearance-aware BoT-SORT.
Ultralytics downloads the model file on first use. Review the licenses of Ultralytics and
any model weights before using this in a distributed or commercial product.

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
4. When the performer leaves the shot, pause and click **Mark off-screen**. Select the new
   track when they return.
5. Review the coral output-crop preview and choose the framing. For a manual correction,
   pause at the desired moment, click **Adjust crop on video**, drag the coral frame, and
   resize it with the slider. The correction follows the automatic camera motion from that
   moment forward; use **Return to auto framing** when it should end.
6. Render the focus cam.

Analysis files, thumbnails, and exports are written under `runs/`. The performer timeline
and manual crop corrections are saved in local browser storage for each analysis. Source
media, model weights, and generated files are ignored by Git.

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
| `FOCUSCAM_MODEL` | `yolo11s.pt` | Ultralytics detection model |
| `FOCUSCAM_TRACKER` | bundled BoT-SORT ReID config | Ultralytics tracker configuration |
| `FOCUSCAM_DEVICE` | auto | `cpu`, `mps`, or a CUDA device such as `0` |
| `FOCUSCAM_IMAGE_SIZE` | `640` | Detector input size; larger is slower but finds smaller people |
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

An optional future segmentation pass can use a manually selected box to prompt SAM 2 and
derive a less noisy silhouette-based bounding box through short occlusions. Segmentation
should refine framing, not automatically decide which performer is the target or cross an
explicit off-screen segment.

For a faster, lower-accuracy analysis, use `FOCUSCAM_MODEL=yolo11n.pt` and
`FOCUSCAM_IMAGE_SIZE=512`.
