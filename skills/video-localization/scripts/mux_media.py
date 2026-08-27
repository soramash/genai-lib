#!/usr/bin/env python3
"""Mux English narration, original Japanese audio, and English subtitles into MP4."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from common import ffprobe, run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--english-audio", type=Path, required=True)
    parser.add_argument("--english-srt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    english_audio = args.english_audio.expanduser().resolve()
    english_srt = args.english_srt.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for path in (source, english_audio, english_srt):
        if not path.is_file():
            parser.error(f"Required input does not exist: {path}")
    if source == output:
        parser.error("Output must not overwrite the source video")
    if output.exists() and not args.force:
        parser.error(f"Output already exists: {output}; use --force")
    if output.suffix.lower() not in {".mp4", ".m4v"}:
        parser.error("This script writes MP4-compatible output (.mp4 or .m4v)")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg is not installed")

    source_info = ffprobe(source)
    if not any(stream.get("codec_type") == "video" for stream in source_info["streams"]):
        parser.error("Source has no video stream")
    if not any(stream.get("codec_type") == "audio" for stream in source_info["streams"]):
        parser.error("Source has no original audio stream")

    output.parent.mkdir(parents=True, exist_ok=True)
    overwrite = "-y" if args.force else "-n"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            overwrite,
            "-i",
            str(source),
            "-i",
            str(english_audio),
            "-i",
            str(english_srt),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "0:a:0",
            "-map",
            "2:0",
            "-c:v",
            "copy",
            "-c:a:0",
            "aac",
            "-b:a:0",
            "192k",
            "-ar:a:0",
            "48000",
            "-ac:a:0",
            "2",
            "-c:a:1",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:0",
            "handler_name=English (Gemini TTS)",
            "-metadata:s:a:1",
            "language=jpn",
            "-metadata:s:a:1",
            "handler_name=Japanese (Original)",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:s:0",
            "handler_name=English Subtitles",
            "-disposition:a:0",
            "default",
            "-disposition:a:1",
            "0",
            "-disposition:s:0",
            "default",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    print(json.dumps({"output": str(output), "source_preserved": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
