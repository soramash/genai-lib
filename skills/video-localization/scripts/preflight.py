#!/usr/bin/env python3
"""Check local requirements and inspect the input media without changing it."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path

from common import ffprobe, file_sha256, write_json


def command_version(command: str) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    import subprocess

    candidates = [[executable, "--version"], [executable, "-version"]]
    for invocation in candidates:
        try:
            result = subprocess.run(invocation, text=True, capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (result.stdout or result.stderr).strip()
        if result.returncode == 0 and text:
            return text.splitlines()[0]
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source video path")
    parser.add_argument("--whisper-model", type=Path, help="Multilingual GGML Whisper model")
    parser.add_argument("--require-tts", action="store_true", help="Require uv and GEMINI_API_KEY")
    parser.add_argument("--output-json", type=Path, help="Optional path for the report")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    tools = {name: command_version(name) for name in ("ffmpeg", "ffprobe", "whisper-cli", "uv")}
    for required in ("ffmpeg", "ffprobe", "whisper-cli"):
        if tools[required] is None:
            errors.append(f"Required command is not installed: {required}")
    if args.require_tts and tools["uv"] is None:
        errors.append("uv is required for pinned Gemini SDK execution")
    if args.require_tts and not os.environ.get("GEMINI_API_KEY"):
        errors.append("GEMINI_API_KEY is not set")

    source = args.input.expanduser().resolve()
    media = None
    if not source.is_file():
        errors.append(f"Input video does not exist: {source}")
    elif tools["ffprobe"]:
        try:
            media = ffprobe(source)
            stream_types = [stream.get("codec_type") for stream in media.get("streams", [])]
            if "video" not in stream_types:
                errors.append("Input has no video stream")
            if "audio" not in stream_types:
                errors.append("Input has no audio stream")
        except Exception as error:  # noqa: BLE001
            errors.append(f"ffprobe failed: {error}")

    model = args.whisper_model.expanduser().resolve() if args.whisper_model else None
    if model and not model.is_file():
        errors.append(f"Whisper model does not exist: {model}")
    if model and model.name.endswith(".en.bin"):
        errors.append("An English-only Whisper model cannot transcribe Japanese")
    if not model:
        warnings.append("No Whisper model supplied; transcription cannot start until one is selected")

    report = {
        "ok": not errors,
        "input": str(source),
        "input_sha256": file_sha256(source) if source.is_file() else None,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "tools": tools,
        "whisper_model": str(model) if model else None,
        "gemini_api_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "media": media,
        "warnings": warnings,
        "errors": errors,
    }
    if args.output_json:
        write_json(args.output_json, report)
    print(__import__("json").dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
