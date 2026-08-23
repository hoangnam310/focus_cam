from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .tracker import analyze_video
from .web import create_app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="focus-cam",
        description="Track every performer, choose one manually, and render a smooth focus cam.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start the local selection interface")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)

    analyze = commands.add_parser("analyze", help="Analyze a video from the command line")
    analyze.add_argument("video", type=Path)
    analyze.add_argument("--max-frames", type=int)
    return parser


def main() -> None:
    args = _parser().parse_args()
    settings = Settings.from_environment()
    if args.command == "serve":
        create_app(settings).run(host=args.host, port=args.port, debug=False, threaded=True)
        return

    video = args.video.expanduser().resolve()
    if not video.is_file():
        raise SystemExit(f"Video not found: {video}")

    def progress(current: int, total: int, message: str) -> None:
        percent = round(100 * current / max(1, total))
        print(f"\r{message}: {percent:3d}%", end="", flush=True)

    result = analyze_video(video, settings, progress, max_frames=args.max_frames)
    print(f"\nSaved analysis {result['analysis_id']} with {len(result['tracks'])} tracks")


if __name__ == "__main__":
    main()
