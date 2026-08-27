#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "google-genai==2.19.0",
# ]
# ///
"""Generate section-cached Gemini TTS and fit it to a video's timeline."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from array import array
from pathlib import Path
from typing import Any

SAMPLE_RATE = 24_000
SILENCE_THRESHOLD_RMS = 500
MIN_SILENCE_SECONDS = 0.15
DEFAULT_MODEL = "gemini-3.1-flash-tts-preview"
DEFAULT_VOICE = "Kore"
SECTION_RE = re.compile(r"^## \[(\d{2}:\d{2}:\d{2})\]\s+(.+?)\s*$", re.MULTILINE)


def timestamp_to_seconds(value: str) -> int:
    hours, minutes, seconds = map(int, value.split(":"))
    if minutes > 59 or seconds > 59:
        raise ValueError(f"Invalid section timestamp: {value}")
    return hours * 3600 + minutes * 60 + seconds


def normalize_markdown_for_speech(value: str) -> str:
    value = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"^[ \t]*(?:[-*+] |\d+[.)] )", "", value, flags=re.MULTILINE)
    value = value.replace("`", "").replace("**", "").replace("__", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_sections(markdown: str, total_seconds: float) -> list[dict[str, Any]]:
    matches = list(SECTION_RE.finditer(markdown))
    if not matches:
        raise ValueError("No sections found; expected headings like '## [00:00:00] Title'")
    sections: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = timestamp_to_seconds(match.group(1))
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        text = normalize_markdown_for_speech(markdown[body_start:body_end])
        if not text:
            raise ValueError(f"Section {index + 1} ({match.group(1)}) has no speech text")
        sections.append(
            {
                "index": index + 1,
                "timestamp": match.group(1),
                "title": match.group(2).strip(),
                "start": float(start),
                "text": text,
            }
        )
    if sections[0]["start"] != 0:
        raise ValueError("The first TTS section must start at 00:00:00")
    starts = [section["start"] for section in sections]
    if starts != sorted(set(starts)):
        raise ValueError("Section timestamps must be unique and strictly increasing")
    if starts[-1] >= total_seconds:
        raise ValueError("The final section starts at or after the requested media duration")
    for index, section in enumerate(sections):
        end = sections[index + 1]["start"] if index + 1 < len(sections) else total_seconds
        section["end"] = end
        section["duration"] = end - section["start"]
    return sections


def media_duration(path: Path) -> float:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required when --media is used")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def write_wave(path: Path, samples: array, rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(rate)
        destination.writeframes(samples.tobytes())


def write_pcm_wave(path: Path, pcm: bytes, rate: int = SAMPLE_RATE) -> None:
    if sys.byteorder != "little":
        values = array("h")
        values.frombytes(pcm)
        values.byteswap()
        pcm = values.tobytes()
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(rate)
        destination.writeframes(pcm)


def load_wave(path: Path) -> tuple[int, array]:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError(f"Expected mono 16-bit PCM WAV: {path}")
        rate = source.getframerate()
        samples = array("h")
        samples.frombytes(source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    return rate, samples


def wave_duration(path: Path) -> float:
    rate, samples = load_wave(path)
    return len(samples) / rate


def cache_key(section: dict[str, Any], model: str, voice: str) -> str:
    serialized = json.dumps(
        {"model": model, "voice": voice, "text": section["text"]},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def generate_section(
    client: Any,
    section: dict[str, Any],
    raw_path: Path,
    model: str,
    voice: str,
) -> None:
    prompt = (
        "Audio profile: A clear, warm, professional English-speaking presenter. "
        "Scene: A professional presentation. "
        "Director's notes: Speak naturally and confidently at a steady pace. "
        f"Aim to finish in approximately {section['duration']:.1f} seconds. "
        "Read the transcript exactly. Do not announce a title, add commentary, "
        "or omit names, numbers, or technical terms.\n\nTranscript:\n"
        + section["text"]
    )
    delay = 5
    for attempt in range(1, 7):
        try:
            interaction = client.interactions.create(
                model=model,
                input=prompt,
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": voice}]},
                timeout=600,
            )
            audio = interaction.output_audio.data
            pcm = base64.b64decode(audio) if isinstance(audio, str) else bytes(audio)
            if len(pcm) < 1_000:
                raise RuntimeError("Gemini returned an unexpectedly small audio payload")
            write_pcm_wave(raw_path, pcm)
            return
        except Exception as error:  # noqa: BLE001
            if attempt == 6:
                raise RuntimeError(
                    f"Gemini TTS failed for section {section['index']} after 6 attempts "
                    f"({type(error).__name__})"
                ) from error
            print(
                f"  attempt {attempt} failed ({type(error).__name__}); retrying in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay = min(delay * 2, 60)


def atempo_filter(factor: float) -> str:
    factors: list[float] = []
    while factor > 2.0:
        factors.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        factors.append(0.5)
        factor /= 0.5
    factors.append(factor)
    return ",".join(f"atempo={value:.8f}" for value in factors)


def speed_up_wave(raw_path: Path, output_path: Path, factor: float) -> tuple[int, array]:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to shorten overlong generated speech")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw_path),
            "-af",
            atempo_filter(factor),
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        check=True,
    )
    return load_wave(output_path)


def internal_silence_endpoints(samples: array, rate: int) -> list[int]:
    frame_samples = max(1, rate // 100)
    silent_frames: list[bool] = []
    frame_rms: list[float] = []
    for offset in range(0, len(samples), frame_samples):
        frame = samples[offset : offset + frame_samples]
        rms = math.sqrt(sum(value * value for value in frame) / max(1, len(frame)))
        frame_rms.append(rms)
        silent_frames.append(rms < SILENCE_THRESHOLD_RMS)

    minimum_frames = math.ceil(MIN_SILENCE_SECONDS * 100)
    endpoints: list[int] = []
    run_start: int | None = None
    for index, is_silent in enumerate(silent_frames + [False]):
        if is_silent and run_start is None:
            run_start = index
        elif not is_silent and run_start is not None:
            if index - run_start >= minimum_frames:
                start_sample = run_start * frame_samples
                end_sample = min(index * frame_samples, len(samples))
                margin = int(0.1 * rate)
                if start_sample > margin and end_sample < len(samples) - margin:
                    endpoints.append(end_sample)
            run_start = None
    if endpoints:
        return endpoints

    margin_frames = max(1, math.ceil(0.1 * rate / frame_samples))
    candidates = range(margin_frames, max(margin_frames + 1, len(frame_rms) - margin_frames))
    quietest = min(candidates, key=lambda index: frame_rms[index], default=len(frame_rms) // 2)
    return [min(len(samples) - 1, max(1, quietest * frame_samples))]


def fit_section(
    raw_path: Path,
    speed_path: Path,
    target_samples: int,
    max_speedup: float,
) -> tuple[array, dict[str, Any]]:
    rate, samples = load_wave(raw_path)
    if rate != SAMPLE_RATE:
        raise ValueError(f"Gemini WAV must be {SAMPLE_RATE} Hz, got {rate} Hz: {raw_path}")
    raw_samples = len(samples)
    speedup = 1.0
    if raw_samples > target_samples:
        speedup = raw_samples / target_samples
        if speedup > max_speedup:
            raise ValueError(
                f"Generated speech is {raw_samples / rate:.2f}s but its section is "
                f"{target_samples / rate:.2f}s; required atempo {speedup:.3f} exceeds "
                f"--max-speedup {max_speedup:.3f}. Shorten the English text or regenerate."
            )
        rate, samples = speed_up_wave(raw_path, speed_path, speedup)
        if len(samples) > target_samples:
            overflow = len(samples) - target_samples
            if overflow > int(0.05 * rate):
                raise ValueError(
                    f"Speed-adjusted speech still exceeds target by {overflow / rate:.3f}s"
                )
            samples = samples[:target_samples]

    extra_samples = target_samples - len(samples)
    endpoints = internal_silence_endpoints(samples, rate) if extra_samples else []
    output = array("h")
    if extra_samples:
        base, remainder = divmod(extra_samples, len(endpoints))
        cursor = 0
        for index, endpoint in enumerate(endpoints):
            output.extend(samples[cursor:endpoint])
            output.extend(array("h", [0]) * (base + (1 if index < remainder else 0)))
            cursor = endpoint
        output.extend(samples[cursor:])
    else:
        output.extend(samples)
    if len(output) != target_samples:
        raise AssertionError(f"Fitted section has {len(output)} samples, expected {target_samples}")
    return output, {
        "raw_duration": raw_samples / rate,
        "target_duration": target_samples / rate,
        "speedup_factor": speedup,
        "pause_count": len(endpoints),
        "added_silence": extra_samples / rate,
        "added_per_pause": (extra_samples / rate / len(endpoints)) if endpoints else 0.0,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcript", type=Path, help="English Markdown with ## [HH:MM:SS] headings")
    duration_group = parser.add_mutually_exclusive_group(required=True)
    duration_group.add_argument("--media", type=Path, help="Media whose duration defines the final WAV")
    duration_group.add_argument("--duration", type=float, help="Final duration in seconds")
    parser.add_argument("--output", type=Path, required=True, help="Output 24 kHz mono PCM WAV")
    parser.add_argument("--work-dir", type=Path, help="Cache directory (default: <output>.work)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--max-speedup", type=float, default=1.15)
    parser.add_argument("--dry-run", action="store_true", help="Validate and plan without API calls or writes")
    parser.add_argument("--force", action="store_true", help="Regenerate cached speech and replace output")
    args = parser.parse_args()

    transcript = args.transcript.expanduser().resolve()
    output = args.output.expanduser().resolve()
    work_dir = (
        args.work_dir.expanduser().resolve()
        if args.work_dir
        else output.with_suffix(output.suffix + ".work")
    )
    if not transcript.is_file():
        parser.error(f"Transcript does not exist: {transcript}")
    if args.media:
        media = args.media.expanduser().resolve()
        if not media.is_file():
            parser.error(f"Media does not exist: {media}")
        total_seconds = media_duration(media)
    else:
        total_seconds = args.duration
    if total_seconds is None or total_seconds <= 0:
        parser.error("Duration must be positive")
    if args.max_speedup < 1.0:
        parser.error("--max-speedup must be at least 1.0")
    if output.exists() and not args.force and not args.dry_run:
        parser.error(f"Output already exists: {output}; use --force")

    markdown = transcript.read_text(encoding="utf-8")
    sections = parse_sections(markdown, total_seconds)
    plan = {
        "transcript": str(transcript),
        "transcript_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "duration": total_seconds,
        "model": args.model,
        "voice": args.voice,
        "section_count": len(sections),
        "sections": [
            {
                "index": section["index"],
                "timestamp": section["timestamp"],
                "title": section["title"],
                "start": section["start"],
                "end": section["end"],
                "duration": section["duration"],
                "characters": len(section["text"]),
            }
            for section in sections
        ],
    }
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        parser.error("GEMINI_API_KEY is not set")

    try:
        from google import genai
    except ImportError as error:
        raise SystemExit(
            "google-genai is unavailable; run this script with 'uv run' so its pinned dependency is used"
        ) from error

    output.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    client = genai.Client()
    all_samples = array("h")
    metrics_list: list[dict[str, Any]] = []
    total_target_samples = round(total_seconds * SAMPLE_RATE)

    print("Gemini receives English transcript text only; no video or audio is uploaded.")
    for index, section in enumerate(sections):
        raw_path = work_dir / f"section_{section['index']:03d}_raw.wav"
        speed_path = work_dir / f"section_{section['index']:03d}_speed.wav"
        cache_path = work_dir / f"section_{section['index']:03d}_cache.json"
        key = cache_key(section, args.model, args.voice)
        reusable = False
        if raw_path.is_file() and cache_path.is_file() and not args.force:
            try:
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
                reusable = cache.get("cache_key") == key and wave_duration(raw_path) >= 0.5
            except (OSError, ValueError, json.JSONDecodeError, wave.Error):
                reusable = False

        print(
            f"[{section['index']:03d}/{len(sections):03d}] {section['timestamp']} "
            f"{section['title']} ({section['duration']:.3f}s)"
        )
        if reusable:
            print("  reusing cached Gemini audio")
        else:
            generate_section(client, section, raw_path, args.model, args.voice)
            write_json(
                cache_path,
                {
                    "cache_key": key,
                    "model": args.model,
                    "voice": args.voice,
                    "text_sha256": hashlib.sha256(section["text"].encode("utf-8")).hexdigest(),
                    "raw_file": raw_path.name,
                    "raw_duration": wave_duration(raw_path),
                },
            )

        start_sample = round(section["start"] * SAMPLE_RATE)
        end_sample = (
            round(sections[index + 1]["start"] * SAMPLE_RATE)
            if index + 1 < len(sections)
            else total_target_samples
        )
        fitted, metrics = fit_section(
            raw_path,
            speed_path,
            end_sample - start_sample,
            args.max_speedup,
        )
        all_samples.extend(fitted)
        metrics.update(
            {
                "index": section["index"],
                "timestamp": section["timestamp"],
                "title": section["title"],
                "start": section["start"],
                "end": section["end"],
                "raw_file": raw_path.name,
                "cache_key": key,
                "reused": reusable,
            }
        )
        metrics_list.append(metrics)
        print(
            f"  raw={metrics['raw_duration']:.2f}s speed={metrics['speedup_factor']:.3f} "
            f"pauses={metrics['pause_count']} added={metrics['added_silence']:.2f}s"
        )

    if len(all_samples) != total_target_samples:
        raise AssertionError(f"Final sample count {len(all_samples)} != {total_target_samples}")
    write_wave(output, all_samples)
    manifest = {
        **plan,
        "output": str(output),
        "output_duration": len(all_samples) / SAMPLE_RATE,
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "sample_width_bits": 16,
        "work_dir": str(work_dir),
        "sections": metrics_list,
    }
    manifest_path = work_dir / "manifest.json"
    write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "output": str(output),
                "duration": manifest["output_duration"],
                "manifest": str(manifest_path),
                "section_count": len(sections),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
