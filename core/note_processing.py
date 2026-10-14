"""Stage 2: clean up raw Basic Pitch note events -> refined note list.

Steps applied in order:
  1. Amplitude filter      -- drop low-confidence detections
  2. Duration filter       -- drop very short noise hits
  3. Instrument + range    -- "auto" decides guitar vs bass from the notes themselves, then drops notes outside
                              that instrument's range (a guitar cannot play below E2, so sub-E2 notes are noise)
  4. Fragment merge        -- join same-pitch notes with tiny gaps
  5. Ghost filter (opt-in) -- drop short "release ghost" notes: a quiet blip just below a note that has just ended
  6. Harmonic suppression  -- drop quieter notes whose pitch is a harmonic of a louder co-occurring note
  7. Octave dedup (opt-in) -- when two octaves of the same pitch overlap, keep lower
  8. Tempo detection       -- estimate BPM via librosa beat tracking
  9. Quantization          -- snap onsets/durations to nearest grid subdivision (the as-played times are kept
                              in orig_start_time_s / orig_end_time_s for MIDI export)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import librosa
import numpy as np

from config.defaults import (
    AUTO_GUITAR_LOW_SHARE,
    DEFAULTS,
    GHOST_MAX_DURATION_S,
    GHOST_MAX_INTERVAL,
    GHOST_RATIO,
    GHOST_START_TOLERANCE_S,
    GUITAR_LOWEST_MIDI,
)

logger = logging.getLogger(__name__)

# Standard instrument pitch ranges (MIDI note numbers)
INSTRUMENT_RANGES = {
    "bass":   (28, 67),   # E1 - G4
    "guitar": (40, 88),   # E2 - E6
    "auto":   (28, 88),   # accept both; let dedup sort it out
}

GRID_SUBDIVISIONS = {
    "4th":  4,
    "8th":  8,
    "16th": 16,
    "32nd": 32,
}

# Semitone intervals corresponding to guitar harmonic series above fundamental:
#   7=P5, 12=octave, 19=oct+P5, 24=2oct, 28=2oct+M3, 31=2oct+P5
_HARMONIC_INTERVALS = frozenset({7, 12, 19, 24, 28, 31})


def process(
    notes_path: Path,
    output_path: Path,
    audio_path: Path | None = None,
    instrument: str = DEFAULTS["instrument"],
    min_amplitude: float = DEFAULTS["min_amplitude"],
    min_duration_s: float = DEFAULTS["min_duration_s"],
    merge_gap_s: float = DEFAULTS["merge_gap_s"],
    quantize: str = DEFAULTS["quantize"],
    tempo_override: float | None = None,
    dedup_octaves: bool = DEFAULTS["dedup_octaves"],
    suppress_harmonics: bool = DEFAULTS["suppress_harmonics"],
    harmonic_ratio: float = DEFAULTS["harmonic_ratio"],
    ghost_filter: bool = DEFAULTS["ghost_filter"],
) -> dict[str, Any]:
    """Clean raw note events and write processed JSON to *output_path*.

    Parameters
    ----------
    notes_path:
        JSON output from Stage 1 (pitch_extraction).
    output_path:
        Destination JSON for cleaned notes.
    audio_path:
        Original audio file -- used for librosa tempo detection.
        If None, tempo detection is skipped and quantization uses *tempo_override*.
    instrument:
        One of "bass", "guitar", "auto". "auto" decides from the notes (see resolve_instrument) and
        records its decision in the output metadata.
    min_amplitude:
        Drop notes below this amplitude (0-1). Basic Pitch noise tends to be < 0.15.
    min_duration_s:
        Drop notes shorter than this after amplitude filter.
    merge_gap_s:
        Merge same-pitch notes whose gap is smaller than this (seconds).
    quantize:
        Grid subdivision: "4th", "8th", "16th", "32nd".
    tempo_override:
        BPM to use if audio_path is None or tempo detection fails.
    dedup_octaves:
        When True, drop the higher note whenever two notes an octave apart overlap.
        Use only on single-instrument stems -- leave False for mixed recordings.
    suppress_harmonics:
        When True (default), drop notes whose pitch is a harmonic interval above a
        louder simultaneous note. Filters guitar/bass overtones that Basic Pitch
        detects as separate pitches. Disable for mixed recordings where harmonic
        intervals between real instruments are expected.
    harmonic_ratio:
        A candidate harmonic is suppressed only when its amplitude is below
        harmonic_ratio x the fundamental amplitude (default 0.5 = 2x quieter).
        Lower values suppress more aggressively.
    ghost_filter:
        Opt-in. Drop "release ghosts": a very short, quieter note 1-2 semitones below a note that has just ended
        (lifting a finger lets the string below ring briefly). Leave off if you play pull-offs or fast descending
        lines, which make real notes that look the same.
    """
    notes_path = Path(notes_path)
    output_path = Path(output_path)

    raw = json.loads(notes_path.read_text())
    notes: list[dict] = raw["notes"]
    logger.info("Loaded %d raw notes from %s", len(notes), notes_path.name)

    # 1. Amplitude
    notes = [n for n in notes if n["amplitude"] >= min_amplitude]
    logger.info("After amplitude filter (>= %.2f): %d notes", min_amplitude, len(notes))

    # 2. Duration
    notes = [n for n in notes if n["duration_s"] >= min_duration_s]
    logger.info("After duration filter (>= %.3fs): %d notes", min_duration_s, len(notes))

    # 3. Instrument + pitch range
    resolved, (lo, hi), low_share = resolve_instrument(notes, instrument)
    if instrument == "auto":
        logger.info("Auto instrument: %s (%.1f%% of notes below E2)", resolved, 100 * (low_share or 0.0))
    notes = [n for n in notes if lo <= n["pitch_midi"] <= hi]
    logger.info("After pitch range filter [%d-%d]: %d notes", lo, hi, len(notes))

    # 4. Fragment merge
    notes = _merge_fragments(notes, merge_gap_s)
    logger.info("After fragment merge (gap < %.3fs): %d notes", merge_gap_s, len(notes))

    # 5. Ghost filter (opt-in)
    ghost_removed = 0
    if ghost_filter:
        before = len(notes)
        notes = _drop_ghost_notes(notes)
        ghost_removed = before - len(notes)
        logger.info("After ghost filter: %d notes (-%d)", len(notes), ghost_removed)

    # 6. Harmonic suppression
    if suppress_harmonics:
        before = len(notes)
        notes = _suppress_harmonics(notes, harmonic_ratio)
        logger.info(
            "After harmonic suppression (ratio=%.2f): %d notes (-%d)",
            harmonic_ratio, len(notes), before - len(notes),
        )
    else:
        logger.info("Harmonic suppression skipped")

    # 6. Octave dedup (opt-in only)
    if dedup_octaves:
        notes = _dedup_octaves(notes)
        logger.info("After octave dedup: %d notes", len(notes))
    else:
        logger.info("Octave dedup skipped")

    # 7. Tempo detection
    tempo = _detect_tempo(audio_path, tempo_override)
    logger.info("Tempo: %.1f BPM", tempo)

    # 8. Quantize
    grid_div = GRID_SUBDIVISIONS.get(quantize, 16)
    notes = _quantize(notes, tempo, grid_div)
    logger.info("After quantization (%s grid): %d notes", quantize, len(notes))

    result: dict[str, Any] = {
        "metadata": {
            "source_notes": str(notes_path),
            "instrument": instrument,
            "instrument_resolved": resolved,
            "low_note_share": None if low_share is None else round(low_share, 4),
            "pitch_range": [lo, hi],
            "min_amplitude": min_amplitude,
            "min_duration_s": min_duration_s,
            "merge_gap_s": merge_gap_s,
            "quantize": quantize,
            "tempo_bpm": round(tempo, 2),
            "dedup_octaves": dedup_octaves,
            "suppress_harmonics": suppress_harmonics,
            "harmonic_ratio": harmonic_ratio,
            "ghost_filter": ghost_filter,
            "ghost_removed": ghost_removed,
            "note_count": len(notes),
        },
        "notes": notes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    logger.info("Wrote %d processed notes to %s", len(notes), output_path)

    return result


# ---------------------------------------------------------------------------
# Instrument decision
# ---------------------------------------------------------------------------

def resolve_instrument(notes: list[dict], instrument: str) -> tuple[str, tuple[int, int], float | None]:
    """Decide which instrument a set of notes belongs to; returns (resolved, (lowest, highest MIDI), low_share).

    An explicit "guitar" or "bass" is used as given (low_share is None). For "auto" the share of notes below E2
    (MIDI 40, the lowest guitar string) decides: under AUTO_GUITAR_LOW_SHARE it is guitar, so impossible sub-E2
    notes (rumble, ghosts) are dropped; otherwise it is bass or a mix, and the wide legacy range is kept so
    nothing is lost. A wrong guess therefore errs toward keeping notes.
    """
    if instrument != "auto":
        return instrument, INSTRUMENT_RANGES[instrument], None
    lo, hi = INSTRUMENT_RANGES["auto"]
    candidates = [n for n in notes if lo <= n["pitch_midi"] <= hi]
    if not candidates:
        return "guitar", INSTRUMENT_RANGES["guitar"], 0.0
    share = sum(1 for n in candidates if n["pitch_midi"] < GUITAR_LOWEST_MIDI) / len(candidates)
    if share < AUTO_GUITAR_LOW_SHARE:
        return "guitar", INSTRUMENT_RANGES["guitar"], share
    return "bass", INSTRUMENT_RANGES["auto"], share


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _drop_ghost_notes(
    notes: list[dict],
    start_tolerance_s: float = GHOST_START_TOLERANCE_S,
    max_duration_s: float = GHOST_MAX_DURATION_S,
    ratio: float = GHOST_RATIO,
    max_interval: int = GHOST_MAX_INTERVAL,
) -> list[dict]:
    """Drop "release ghosts": short, quieter notes 1-2 semitones below a note that has just ended.

    Lifting a finger off a fretted note lets the string below ring briefly; the detector reports that as a
    tiny extra note starting exactly when the previous note stops (e.g. a stray open E2 right after an F2).
    """
    keep = [True] * len(notes)
    for i, ghost in enumerate(notes):
        if ghost["duration_s"] > max_duration_s:
            continue
        for j, prev in enumerate(notes):
            if i == j or not keep[j]:
                continue
            if not 1 <= prev["pitch_midi"] - ghost["pitch_midi"] <= max_interval:
                continue
            if not -0.02 <= ghost["start_time_s"] - prev["end_time_s"] <= start_tolerance_s:
                continue
            if ghost["amplitude"] < ratio * prev["amplitude"]:
                keep[i] = False
                break
    return [n for n, k in zip(notes, keep) if k]


def _suppress_harmonics(notes: list[dict], ratio: float) -> list[dict]:
    """Drop notes that are likely guitar harmonics of a louder simultaneous fundamental.

    For each overlapping pair where the pitch interval is a known harmonic, the
    higher/quieter note is suppressed when its amplitude < ratio x fundamental amplitude.
    """
    if not notes:
        return notes

    keep_flags = [True] * len(notes)

    for i, candidate in enumerate(notes):
        if not keep_flags[i]:
            continue
        for j, fundamental in enumerate(notes):
            if i == j or not keep_flags[j]:
                continue
            interval = candidate["pitch_midi"] - fundamental["pitch_midi"]
            if interval not in _HARMONIC_INTERVALS:
                continue
            overlap_start = max(candidate["start_time_s"], fundamental["start_time_s"])
            overlap_end   = min(candidate["end_time_s"],   fundamental["end_time_s"])
            if overlap_end <= overlap_start:
                continue
            if candidate["amplitude"] < ratio * fundamental["amplitude"]:
                keep_flags[i] = False
                logger.debug(
                    "Suppress harmonic: midi=%d (+%d above %d)  amp=%.3f < %.2f x %.3f",
                    candidate["pitch_midi"], interval, fundamental["pitch_midi"],
                    candidate["amplitude"], ratio, fundamental["amplitude"],
                )
                break

    return [n for n, keep in zip(notes, keep_flags) if keep]


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
            prev["end_time_s"] = max(prev["end_time_s"], n["end_time_s"])
            prev["duration_s"] = prev["end_time_s"] - prev["start_time_s"]
            prev["amplitude"] = max(prev["amplitude"], n["amplitude"])
        else:
            merged.append(n.copy())

    return sorted(merged, key=lambda n: n["start_time_s"])


def _dedup_octaves(notes: list[dict]) -> list[dict]:
    """When two notes an octave apart overlap in time, drop the higher one."""
    notes = sorted(notes, key=lambda n: n["start_time_s"])
    keep = []

    for n in notes:
        dominated = False
        for other in keep:
            if abs(n["pitch_midi"] - other["pitch_midi"]) % 12 != 0:
                continue
            if n["pitch_midi"] <= other["pitch_midi"]:
                continue
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
        n["orig_start_time_s"] = n["start_time_s"]  # as performed; MIDI export uses these ("played" timing)
        n["orig_end_time_s"] = n["end_time_s"]
        onset_q = round(n["start_time_s"] / grid_s) * grid_s
        dur_steps = max(1, round(n["duration_s"] / grid_s))
        dur_q = dur_steps * grid_s
        n["start_time_s"] = round(onset_q, 6)
        n["end_time_s"] = round(onset_q + dur_q, 6)
        n["duration_s"] = round(dur_q, 6)
        n["grid_steps"] = dur_steps
        result.append(n)

    return sorted(result, key=lambda n: n["start_time_s"])
