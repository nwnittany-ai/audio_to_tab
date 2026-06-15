"""Stage 2: clean up raw Basic Pitch note events -> refined note list.

Steps applied in order:
  1. Pitch range filter   — drop notes outside instrument range
  2. Amplitude filter     — drop low-confidence detections
  3. Duration filter      — drop very short noise hits
  4. Fragment merge       — join same-pitch notes with tiny gaps
  5. Octave dedup         — when two octaves of the same pitch overlap, keep lower
  6. Tempo detection      — estimate BPM via librosa beat tracking
  7. Quantization         — snap onsets/durations to nearest grid subdivision
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import librosa
import numpy as np

logger = logging.getLogger(__name__)

# Standard instrument pitch ranges (MIDI note numbers)
INSTRUMENT_RANGES = {
    "bass":   (28, 67),   # E1 – G4
    "guitar": (40, 88),   # E2 – E6
    "auto":   (28, 88),   # accept both; let dedup sort it out
}

GRID_SUBDIVISIONS = {
    "4th":  4,
    "8th":  8,
    "16th": 16,
    "32nd": 32,
}


def process(
    notes_path: Path,
    output_path: Path,
    audio_path: Path | None = None,
    instrument: str = "auto",
    min_amplitude: float = 0.15,
    min_duration_s: float = 0.05,
    merge_gap_s: float = 0.08,
    quantize: str = "16th",
    tempo_override: float | None = None,
    dedup_octaves: bool = False,
) -> dict[str, Any]:
    """Clean raw note events and write processed JSON to *output_path*.

    Parameters
    ----------
    notes_path:
        JSON output from Stage 1 (pitch_extraction).
    output_path:
        Destination JSON for cleaned notes.
    audio_path:
        Original audio file — used for librosa tempo detection.
        If None, tempo detection is skipped and quantization uses *tempo_override*.
    instrument:
        One of 'bass', 'guitar', 'auto' — sets pitch range filter.
    min_amplitude:
        Drop notes below this amplitude (0–1). Basic Pitch noise tends to be < 0.15.
    min_duration_s:
        Drop notes shorter than this after amplitude filter.
    merge_gap_s:
        Merge same-pitch notes whose gap is smaller than this (seconds).
    quantize:
        Grid subdivision: '4th', '8th', '16th', '32nd'.
    tempo_override:
        BPM to use if audio_path is None or tempo detection fails.
    dedup_octaves:
        When True, drop the higher note whenever two notes an octave apart overlap.
        Use only on single-instrument stems — leave False for mixed recordings where
        multiple instruments may legitimately play different octaves simultaneously.
    """
    notes_path = Path(notes_path)
    output_path = Path(output_path)

    raw = json.loads(notes_path.read_text())
    notes: list[dict] = raw["notes"]
    logger.info("Loaded %d raw notes from %s", len(notes), notes_path.name)

    # 1. Pitch range
    lo, hi = INSTRUMENT_RANGES.get(instrument, INSTRUMENT_RANGES["auto"])
    notes = [n for n in notes if lo <= n["pitch_midi"] <= hi]
    logger.info("After pitch range filter [%d-%d]: %d notes", lo, hi, len(notes))

    # 2. Amplitude
    notes = [n for n in notes if n["amplitude"] >= min_amplitude]
    logger.info("After amplitude filter (>= %.2f): %d notes", min_amplitude, len(notes))

    # 3. Duration
    notes = [n for n in notes if n["duration_s"] >= min_duration_s]
    logger.info("After duration filter (>= %.3fs): %d notes", min_duration_s, len(notes))

    # 4. Fragment merge
    notes = _merge_fragments(notes, merge_gap_s)
    logger.info("After fragment merge (gap < %.3fs): %d notes", merge_gap_s, len(notes))

    # 5. Octave dedup (opt-in only — not appropriate for mixed recordings)
    if dedup_octaves:
        notes = _dedup_octaves(notes)
        logger.info("After octave dedup: %d notes", len(notes))
    else:
        logger.info("Octave dedup skipped (mixed recording or single instrument stem)")

    # 6. Tempo detection
    tempo = _detect_tempo(audio_path, tempo_override)
    logger.info("Tempo: %.1f BPM", tempo)

    # 7. Quantize
    grid_div = GRID_SUBDIVISIONS.get(quantize, 16)
    notes = _quantize(notes, tempo, grid_div)
    logger.info("After quantization (%s grid): %d notes", quantize, len(notes))

    result: dict[str, Any] = {
        "metadata": {
            "source_notes": str(notes_path),
            "instrument": instrument,
            "pitch_range": [lo, hi],
            "min_amplitude": min_amplitude,
            "min_duration_s": min_duration_s,
            "merge_gap_s": merge_gap_s,
            "quantize": quantize,
            "tempo_bpm": round(tempo, 2),
            "dedup_octaves": dedup_octaves,
            "note_count": len(notes),
        },
        "notes": notes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    logger.info("Wrote %d processed notes to %s", len(notes), output_path)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _merge_fragments(notes: list[dict], gap_s: float) -> list[dict]:
    """Merge consecutive notes of the same pitch separated by less than *gap_s*."""
    if not notes:
        return notes

    notes = sorted(notes, key=lambda n: (n["pitch_midi"], n["start_time_s"]))
    merged = [notes[0].copy()]

    for n in notes[1:]:
        prev = merged[-1]
        gap = n["start_time_s"] - prev["end_time_s"]
        if n["pitch_midi"] == prev["pitch_midi"] and gap < gap_s:
            # Extend previous note to cover this one
            prev["end_time_s"] = max(prev["end_time_s"], n["end_time_s"])
            prev["duration_s"] = prev["end_time_s"] - prev["start_time_s"]
            prev["amplitude"] = max(prev["amplitude"], n["amplitude"])
        else:
            merged.append(n.copy())

    return sorted(merged, key=lambda n: n["start_time_s"])


def _dedup_octaves(notes: list[dict]) -> list[dict]:
    """When two notes an octave apart overlap in time, drop the higher one.

    Basic Pitch frequently detects both a note and its octave harmonic
    (especially on bass). We keep the lower pitch as the more likely
    fundamental.
    """
    notes = sorted(notes, key=lambda n: n["start_time_s"])
    keep = []

    for n in notes:
        dominated = False
        for other in keep:
            if abs(n["pitch_midi"] - other["pitch_midi"]) % 12 != 0:
                continue
            if n["pitch_midi"] <= other["pitch_midi"]:
                continue
            # n is higher; check time overlap
            overlap_start = max(n["start_time_s"], other["start_time_s"])
            overlap_end = min(n["end_time_s"], other["end_time_s"])
            if overlap_end > overlap_start:
                dominated = True
                break
        if not dominated:
            keep.append(n)

    return sorted(keep, key=lambda n: n["start_time_s"])


def _detect_tempo(audio_path: Path | None, override: float | None) -> float:
    if override is not None:
        return float(override)
    if audio_path is None:
        logger.warning("No audio path for tempo detection; defaulting to 120 BPM")
        return 120.0
    try:
        y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
        if bpm < 40 or bpm > 240:
            logger.warning("Detected tempo %.1f BPM looks suspect; defaulting to 120", bpm)
            return 120.0
        return bpm
    except Exception as exc:
        logger.warning("Tempo detection failed (%s); defaulting to 120 BPM", exc)
        return 120.0


def _quantize(notes: list[dict], tempo_bpm: float, subdivisions: int) -> list[dict]:
    """Snap note onsets and durations to the nearest grid step."""
    beat_s = 60.0 / tempo_bpm
    grid_s = beat_s / (subdivisions / 4)  # grid step in seconds

    result = []
    for n in notes:
        n = n.copy()
        onset_q = round(n["start_time_s"] / grid_s) * grid_s
        dur_steps = max(1, round(n["duration_s"] / grid_s))
        dur_q = dur_steps * grid_s
        n["start_time_s"] = round(onset_q, 6)
        n["end_time_s"] = round(onset_q + dur_q, 6)
        n["duration_s"] = round(dur_q, 6)
        n["grid_steps"] = dur_steps
        result.append(n)

    return sorted(result, key=lambda n: n["start_time_s"])
