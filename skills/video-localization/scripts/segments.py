#!/usr/bin/env python3
"""Initialize, validate, and render cue-locked localization segments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import Cue, parse_srt, render_srt, write_json

REQUIRED_FIELDS = ("index", "start", "end", "raw_ja", "corrected_ja", "en")


def load_segments(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Segments JSON must be an array")
    return value


def init_segments(source_srt: Path, output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; use --force")
    cues = parse_srt(source_srt)
    segments = [
        {
            "index": cue.index,
            "start": cue.start,
            "end": cue.end,
            "raw_ja": " ".join(cue.lines),
            "corrected_ja": "",
            "en": "",
        }
        for cue in cues
    ]
    write_json(output, segments)
    print(json.dumps({"created": str(output), "cue_count": len(segments)}, ensure_ascii=False))


def validate_segments(source_srt: Path, segments_path: Path) -> dict[str, Any]:
    cues = parse_srt(source_srt)
    segments = load_segments(segments_path)
    errors: list[str] = []
    warnings: list[str] = []
    if len(segments) != len(cues):
        errors.append(f"Segment count {len(segments)} does not match source cue count {len(cues)}")

    for position, cue in enumerate(cues):
        if position >= len(segments):
            break
        segment = segments[position]
        missing = [field for field in REQUIRED_FIELDS if field not in segment]
        if missing:
            errors.append(f"Segment {position + 1} is missing fields: {missing}")
            continue
        if segment["index"] != cue.index:
            errors.append(f"Segment position {position + 1} has index {segment['index']}, expected {cue.index}")
        if segment["start"] != cue.start or segment["end"] != cue.end:
            errors.append(f"Cue {cue.index} timestamps differ from the source SRT")
        expected_raw = " ".join(cue.lines)
        if str(segment["raw_ja"]).strip() != expected_raw:
            errors.append(f"Cue {cue.index} raw_ja differs from the source SRT")
        for field in ("corrected_ja", "en"):
            if not isinstance(segment[field], str) or not segment[field].strip():
                errors.append(f"Cue {cue.index} has empty {field}")
        english = str(segment.get("en", "")).strip()
        if len(english) > 84:
            warnings.append(f"Cue {cue.index} English text exceeds 84 characters ({len(english)})")

    return {
        "ok": not errors,
        "source_srt": str(source_srt),
        "segments": str(segments_path),
        "cue_count": len(cues),
        "segment_count": len(segments),
        "first_timestamp": cues[0].start if cues else None,
        "last_timestamp": cues[-1].end if cues else None,
        "warnings": warnings,
        "errors": errors,
    }


def wrap_english(text: str, width: int = 42) -> tuple[str, ...]:
    normalized = " ".join(text.split())
    if len(normalized) <= width:
        return (normalized,)
    spaces = [index for index, character in enumerate(normalized) if character == " "]
    if not spaces:
        return (normalized,)
    midpoint = len(normalized) / 2
    split = min(spaces, key=lambda index: abs(index - midpoint))
    return (normalized[:split].strip(), normalized[split + 1 :].strip())


def render_outputs(source_srt: Path, segments_path: Path, output_dir: Path, stem: str) -> None:
    report = validate_segments(source_srt, segments_path)
    if not report["ok"]:
        raise ValueError("Segments are invalid:\n" + "\n".join(report["errors"]))
    segments = load_segments(segments_path)
    ja_cues = [
        Cue(
            index=int(segment["index"]),
            start=segment["start"],
            end=segment["end"],
            lines=(" ".join(segment["corrected_ja"].split()),),
        )
        for segment in segments
    ]
    en_cues = [
        Cue(
            index=int(segment["index"]),
            start=segment["start"],
            end=segment["end"],
            lines=wrap_english(segment["en"]),
        )
        for segment in segments
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    ja_path = output_dir / f"{stem}.corrected_ja.srt"
    en_path = output_dir / f"{stem}.en.srt"
    ja_path.write_text(render_srt(ja_cues), encoding="utf-8")
    en_path.write_text(render_srt(en_cues), encoding="utf-8")
    print(
        json.dumps(
            {
                "japanese_srt": str(ja_path),
                "english_srt": str(en_path),
                "cue_count": len(segments),
                "warnings": report["warnings"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a segments JSON template")
    init_parser.add_argument("source_srt", type=Path)
    init_parser.add_argument("output", type=Path)
    init_parser.add_argument("--force", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="Validate translated segments")
    validate_parser.add_argument("source_srt", type=Path)
    validate_parser.add_argument("segments", type=Path)
    validate_parser.add_argument("--output-json", type=Path)

    render_parser = subparsers.add_parser("render", help="Render corrected Japanese and English SRT")
    render_parser.add_argument("source_srt", type=Path)
    render_parser.add_argument("segments", type=Path)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    render_parser.add_argument("--stem", required=True)

    args = parser.parse_args()
    if args.command == "init":
        init_segments(args.source_srt, args.output, args.force)
        return 0
    if args.command == "validate":
        report = validate_segments(args.source_srt, args.segments)
        if args.output_json:
            write_json(args.output_json, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2
    render_outputs(args.source_srt, args.segments, args.output_dir, args.stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
