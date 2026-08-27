#!/usr/bin/env python3
"""Shared helpers for the video-localization Skill."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SRT_TIME_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")


@dataclass(frozen=True)
class Cue:
    index: int
    start: str
    end: str
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture,
    )


def ffprobe(path: Path) -> dict[str, Any]:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def video_stream_hash(path: Path) -> str:
    result = run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-c",
            "copy",
            "-f",
            "hash",
            "-",
        ],
        capture=True,
    )
    return result.stdout.strip()


def timestamp_to_milliseconds(value: str) -> int:
    match = SRT_TIME_RE.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, milliseconds = map(int, match.groups())
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + milliseconds


def parse_srt_text(content: str) -> list[Cue]:
    blocks = re.split(r"\r?\n\s*\r?\n", content.strip()) if content.strip() else []
    cues: list[Cue] = []
    for block_number, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3:
            raise ValueError(f"Invalid SRT block {block_number}: expected at least 3 lines")
        try:
            index = int(lines[0].strip())
        except ValueError as error:
            raise ValueError(f"Invalid cue index in block {block_number}: {lines[0]!r}") from error
        if " --> " not in lines[1]:
            raise ValueError(f"Invalid time range in cue {index}: {lines[1]!r}")
        start, end = (part.strip() for part in lines[1].split(" --> ", maxsplit=1))
        if timestamp_to_milliseconds(end) <= timestamp_to_milliseconds(start):
            raise ValueError(f"Cue {index} has a non-positive duration")
        text_lines = tuple(line.rstrip() for line in lines[2:] if line.strip())
        if not text_lines:
            raise ValueError(f"Cue {index} has no text")
        cues.append(Cue(index=index, start=start, end=end, lines=text_lines))

    expected = list(range(1, len(cues) + 1))
    actual = [cue.index for cue in cues]
    if actual != expected:
        raise ValueError(f"Cue indices must be contiguous from 1; got {actual[:5]}...{actual[-5:]}")
    for previous, current in zip(cues, cues[1:]):
        if timestamp_to_milliseconds(current.start) < timestamp_to_milliseconds(previous.end):
            raise ValueError(f"Cue {current.index} overlaps cue {previous.index}")
    return cues


def parse_srt(path: Path) -> list[Cue]:
    return parse_srt_text(path.read_text(encoding="utf-8-sig"))


def render_srt(cues: Iterable[Cue]) -> str:
    blocks = []
    for cue in cues:
        blocks.append(
            f"{cue.index}\n{cue.start} --> {cue.end}\n" + "\n".join(cue.lines)
        )
    return "\n\n".join(blocks) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
