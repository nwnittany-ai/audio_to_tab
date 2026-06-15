"""Stage 5: full pipeline -- extract -> process -> map -> render in one call."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.pitch_extraction import extract
from core.note_processing import process
from core.fretboard_mapping import map_notes
from core.tab_renderer import render

logger = logging.getLogger(__name__)


def run(
    audio_path: Path,
    output_dir: Path,
    tuning: str = "standard",
    instrument: str = "auto",
    quantize: str = "8th",
    measures_per_line: int = 4,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    min_amplitude: float = 0.25,
    position_window: int = 5,
    max_fret: int = 24,
    dedup_octaves: bool = False,
    suppress_harmonics: bool = True,
    harmonic_ratio: float = 0.5,
    tempo_override: float | None = None,
    keep_intermediates: bool = True,
) -> dict[str, Any]:
    """Run all four pipeline stages end-to-end.

    Parameters
    ----------
    audio_path:
        Input audio file (.wav or .mp3).
    output_dir:
        Directory for all output files (intermediates + final tab).
    tuning:
        Tuning name for fretboard mapping (e.g. "standard", "drop_d", "bass").
    instrument:
        Pitch range filter for note processing ("guitar", "bass", "auto").
    quantize:
        Grid subdivision for timing quantization ("4th", "8th", "16th", "32nd").
    measures_per_line:
        Measures per line in ASCII tab output.
    onset_threshold:
        Basic Pitch onset confidence threshold.
    frame_threshold:
        Basic Pitch frame confidence threshold.
    min_amplitude:
        Minimum note amplitude to keep after extraction (default 0.25 for run;
        the process stage alone defaults to 0.15).
    position_window:
        Fret-hand position window for fretboard mapping.
    max_fret:
        Hard upper limit on fret numbers (default 24). Set to 12 to restrict to
        first-position playing and filter high-fret harmonic false positives.
    dedup_octaves:
        Remove octave duplicates (use only on single-instrument stems).
    suppress_harmonics:
        Drop quieter notes at harmonic intervals above a louder co-occurring note.
        Default True -- disable for mixed recordings.
    harmonic_ratio:
        Suppression threshold: harmonic amplitude must be < ratio x fundamental.
    tempo_override:
        Force a specific BPM instead of auto-detecting.
    keep_intermediates:
        If False, delete the three intermediate JSON files after rendering.

    Returns
    -------
    dict with paths to all output files and summary metadata.
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = audio_path.stem
    notes_path     = output_dir / f"{stem}_notes.json"
    processed_path = output_dir / f"{stem}_processed.json"
    mapped_path    = output_dir / f"{stem}_mapped.json"
    tab_path       = output_dir / f"{stem}.tab"

    logger.info("=== Stage 1: pitch extraction ===")
    r1 = extract(
        audio_path=audio_path,
        output_path=notes_path,
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
    )

    logger.info("=== Stage 2: note processing ===")
    r2 = process(
        notes_path=notes_path,
        output_path=processed_path,
        audio_path=audio_path,
        instrument=instrument,
        min_amplitude=min_amplitude,
        quantize=quantize,
        tempo_override=tempo_override,
        dedup_octaves=dedup_octaves,
        suppress_harmonics=suppress_harmonics,
        harmonic_ratio=harmonic_ratio,
    )

    logger.info("=== Stage 3: fretboard mapping ===")
    r3 = map_notes(
        processed_path=processed_path,
        output_path=mapped_path,
        tuning=tuning,
        position_window=position_window,
        max_fret=max_fret,
    )

    logger.info("=== Stage 4: tab rendering ===")
    r4 = render(
        mapped_path=mapped_path,
        output_path=tab_path,
        measures_per_line=measures_per_line,
    )

    if not keep_intermediates:
        for p in (notes_path, processed_path, mapped_path):
            p.unlink(missing_ok=True)
        logger.info("Intermediate files removed")

    summary = {
        "audio":      str(audio_path),
        "tab":        str(tab_path),
        "notes_raw":  r1["metadata"]["note_count"],
        "notes_kept": r2["metadata"]["note_count"],
        "notes_mapped": r3["metadata"]["note_count"] - r3["metadata"]["unmapped_count"],
        "measures":   r4["metadata"]["measures"],
        "tempo_bpm":  r4["metadata"]["tempo_bpm"],
        "tuning":     tuning,
        "quantize":   quantize,
    }
    return summary
