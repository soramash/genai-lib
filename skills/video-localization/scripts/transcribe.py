#!/usr/bin/env python3
"""Extract audio and transcribe Japanese locally with whisper-cli."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from common import file_sha256, parse_srt, run, write_json

DEFAULT_PROMPT = (
    "これは日本語のプレゼンテーションです。固有名詞、技術用語、英字略語、数値を"
    "正確に文字起こししてください。"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source video")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True, help="Multilingual GGML model")
    parser.add_argument("--language", default="ja")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    model = args.model.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Input does not exist: {source}")
    if not model.is_file():
        parser.error(f"Model does not exist: {model}")
    for command in ("ffmpeg", "whisper-cli"):
        if not shutil.which(command):
            parser.error(f"Required command is not installed: {command}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    audio = output_dir / f"{stem}.transcription.wav"
    base = output_dir / f"{stem}.raw"
    expected = [base.with_suffix(extension) for extension in (".txt", ".srt", ".json")]
    protected = [audio, *expected]
    if not args.force and any(path.exists() for path in protected):
        existing = ", ".join(str(path) for path in protected if path.exists())
        parser.error(f"Refusing to overwrite existing artifacts: {existing}; use --force")

    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio),
        ]
    )
    run(
        [
            "whisper-cli",
            "-m",
            str(model),
            "-f",
            str(audio),
            "-l",
            args.language,
            "-t",
            str(args.threads),
            "-bo",
            "5",
            "-bs",
            "5",
            "-otxt",
            "-osrt",
            "-oj",
            "-of",
            str(base),
            "--prompt",
            args.prompt,
        ]
    )
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError(f"whisper-cli did not produce: {missing}")
    cues = parse_srt(base.with_suffix(".srt"))
    manifest = {
        "input": str(source),
        "input_sha256": file_sha256(source),
        "model": str(model),
        "model_sha256": file_sha256(model),
        "language": args.language,
        "cue_count": len(cues),
        "first_timestamp": cues[0].start if cues else None,
        "last_timestamp": cues[-1].end if cues else None,
        "artifacts": {
            "audio": str(audio),
            "txt": str(base.with_suffix(".txt")),
            "srt": str(base.with_suffix(".srt")),
            "json": str(base.with_suffix(".json")),
        },
    }
    manifest_path = output_dir / f"{stem}.transcription-manifest.json"
    write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
