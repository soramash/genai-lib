#!/usr/bin/env python3
"""Validate localized MP4 streams, timing, subtitles, and source-video preservation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from common import ffprobe, parse_srt, parse_srt_text, video_stream_hash, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--english-srt", type=Path, required=True)
    parser.add_argument("--duration-tolerance", type=float, default=0.15)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    english_srt = args.english_srt.expanduser().resolve()
    errors: list[str] = []
    checks: dict[str, object] = {}
    for path in (source, output, english_srt):
        if not path.is_file():
            errors.append(f"Missing file: {path}")
    if errors:
        report = {"ok": False, "checks": checks, "errors": errors}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    source_info = ffprobe(source)
    output_info = ffprobe(output)
    streams = output_info.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    subtitles = [stream for stream in streams if stream.get("codec_type") == "subtitle"]
    checks["stream_counts"] = {"video": len(videos), "audio": len(audios), "subtitle": len(subtitles)}
    if len(videos) != 1:
        errors.append(f"Expected one video stream, found {len(videos)}")
    if len(audios) < 2:
        errors.append(f"Expected English and Japanese audio streams, found {len(audios)}")
    if len(subtitles) != 1:
        errors.append(f"Expected one subtitle stream, found {len(subtitles)}")

    if len(audios) >= 2:
        english, japanese = audios[:2]
        checks["english_audio"] = {
            "codec": english.get("codec_name"),
            "language": english.get("tags", {}).get("language"),
            "handler": english.get("tags", {}).get("handler_name"),
            "default": english.get("disposition", {}).get("default"),
        }
        checks["japanese_audio"] = {
            "codec": japanese.get("codec_name"),
            "language": japanese.get("tags", {}).get("language"),
            "handler": japanese.get("tags", {}).get("handler_name"),
            "default": japanese.get("disposition", {}).get("default"),
        }
        if english.get("tags", {}).get("language") != "eng" or english.get("disposition", {}).get("default") != 1:
            errors.append("First audio stream must be default English")
        if japanese.get("tags", {}).get("language") != "jpn":
            errors.append("Second audio stream must be tagged jpn")

    source_duration = float(source_info["format"]["duration"])
    output_duration = float(output_info["format"]["duration"])
    duration_delta = abs(source_duration - output_duration)
    checks["duration"] = {
        "source": source_duration,
        "output": output_duration,
        "delta": duration_delta,
        "tolerance": args.duration_tolerance,
    }
    if duration_delta > args.duration_tolerance:
        errors.append(f"Output duration differs from source by {duration_delta:.3f}s")

    source_hash = video_stream_hash(source)
    output_hash = video_stream_hash(output)
    checks["video_stream_hash"] = {"source": source_hash, "output": output_hash, "match": source_hash == output_hash}
    if source_hash != output_hash:
        errors.append("Output video bitstream differs from source")

    try:
        extracted = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(output), "-map", "0:s:0", "-f", "srt", "-"],
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8-sig")
        embedded_cues = parse_srt_text(extracted)
        source_cues = parse_srt(english_srt)
        exact = embedded_cues == source_cues
        checks["subtitles"] = {
            "expected_cues": len(source_cues),
            "embedded_cues": len(embedded_cues),
            "exact_match": exact,
        }
        if not exact:
            errors.append("Embedded subtitles differ from the English SRT")
    except Exception as error:  # noqa: BLE001
        errors.append(f"Subtitle extraction or comparison failed: {error}")

    for audio_index in range(min(2, len(audios))):
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(output),
                "-map",
                f"0:a:{audio_index}",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            errors.append(f"Audio stream {audio_index} failed to decode")
    checks["audio_decode"] = not any("failed to decode" in error for error in errors)

    report = {"ok": not errors, "output": str(output), "checks": checks, "errors": errors}
    if args.output_json:
        write_json(args.output_json, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
