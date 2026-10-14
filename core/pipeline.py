"""Full pipeline in one call: extract -> process -> map -> render -> (optional) MIDI export."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from config.defaults import DEFAULTS
from core.fretboard_mapping import map_notes
from core.midi_export import export as export_midi
from core.note_processing import process
from core.pitch_extraction import extract
from core.tab_renderer import render

logger = logging.getLogger(__name__)

# Stage names, shared with the GUI so progress reports and panels always agree.
STAGES = ("Stage 1: Extract", "Stage 2: Process", "Stage 3: Map", "Stage 4: Render", "Stage 5: MIDI")

# progress(stage_name, state, text): state is "running", "done" or "skipped"; text is a short summary.
ProgressCallback = Callable[[str, str, str], None]


def run(
    audio_path: Path,
    output_dir: Path,
    tuning: str = DEFAULTS["tuning"],
    instrument: str = DEFAULTS["instrument"],
    quantize: str = DEFAULTS["quantize"],
    measures_per_line: int = DEFAULTS["measures_per_line"],
    onset_threshold: float = DEFAULTS["onset_threshold"],
    frame_threshold: float = DEFAULTS["frame_threshold"],
    min_amplitude: float = DEFAULTS["min_amplitude"],
    position_window: int = DEFAULTS["position_window"],
    max_fret: int = DEFAULTS["max_fret"],
    dedup_octaves: bool = DEFAULTS["dedup_octaves"],
    suppress_harmonics: bool = DEFAULTS["suppress_harmonics"],
    harmonic_ratio: float = DEFAULTS["harmonic_ratio"],
    ghost_filter: bool = DEFAULTS["ghost_filter"],
    tempo_override: float | None = None,
    keep_intermediates: bool = True,
    chord_symbols: bool = DEFAULTS["chord_symbols"],
    midi: bool = DEFAULTS["midi"],
    midi_timing: str = DEFAULTS["midi_timing"],
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run all stages end-to-end and return a summary with the output paths and counts.

    Parameters
    ----------
    audio_path:
        Input audio file (.wav or .mp3).
    output_dir:
        Directory for every output file (tab, MIDI and the intermediate JSON files).
    tuning, instrument, quantize, measures_per_line, chord_symbols:
        Tab layout options. ``instrument`` is "guitar", "bass" or "auto" (decided from the notes).
    onset_threshold, frame_threshold:
        Basic Pitch detection confidence thresholds.
    min_amplitude, suppress_harmonics, harmonic_ratio, dedup_octaves, ghost_filter:
        Note-cleaning options (see core.note_processing).
    position_window, max_fret:
        Fretboard mapping: fret-hand window size and the highest fret allowed.
    tempo_override:
        Force a BPM instead of auto-detecting.
    keep_intermediates:
        If False, delete the three intermediate JSON files afterwards.
    midi, midi_timing:
        Also write a .mid file; "played" keeps the performance's timing, "grid" snaps to the quantize grid.
    progress:
        Optional callback ``progress(stage, state, text)`` used by the GUI instead of parsing log text.
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda stage, state, text: None)

    stem = audio_path.stem
    notes_path = output_dir / f"{stem}_notes.json"
    processed_path = output_dir / f"{stem}_processed.json"
    mapped_path = output_dir / f"{stem}_mapped.json"
    tab_path = output_dir / f"{stem}.tab"
    midi_path = output_dir / f"{stem}.mid"

    logger.info("=== Stage 1: pitch extraction ===")
    say(STAGES[0], "running", "")
    r1 = extract(audio_path=audio_path, output_path=notes_path,
                 onset_threshold=onset_threshold, frame_threshold=frame_threshold)
    say(STAGES[0], "done", f"{r1['metadata']['note_count']} raw notes")

    logger.info("=== Stage 2: note processing ===")
    say(STAGES[1], "running", "")
    r2 = process(
        notes_path=notes_path, output_path=processed_path, audio_path=audio_path, instrument=instrument,
        min_amplitude=min_amplitude, quantize=quantize, tempo_override=tempo_override,
        dedup_octaves=dedup_octaves, suppress_harmonics=suppress_harmonics, harmonic_ratio=harmonic_ratio,
        ghost_filter=ghost_filter,
    )
    resolved = r2["metadata"]["instrument_resolved"]
    say(STAGES[1], "done", f"{r2['metadata']['note_count']} kept ({resolved})")

    logger.info("=== Stage 3: fretboard mapping ===")
    say(STAGES[2], "running", "")
    r3 = map_notes(processed_path=processed_path, output_path=mapped_path, tuning=tuning,
                   position_window=position_window, max_fret=max_fret)
    mapped = r3["metadata"]["note_count"] - r3["metadata"]["unmapped_count"]
    say(STAGES[2], "done", f"{mapped} mapped")

    logger.info("=== Stage 4: tab rendering ===")
    say(STAGES[3], "running", "")
    r4 = render(mapped_path=mapped_path, output_path=tab_path, measures_per_line=measures_per_line,
                chord_symbols=chord_symbols)
    say(STAGES[3], "done", f"{r4['metadata']['measures']} measures")

    r5: dict[str, Any] | None = None
    if midi:
        logger.info("=== Stage 5: MIDI export ===")
        say(STAGES[4], "running", "")
        r5 = export_midi(processed_path=processed_path, output_path=midi_path, timing=midi_timing)
        say(STAGES[4], "done", f"{r5['note_count']} notes")
    else:
        say(STAGES[4], "skipped", "not requested")

    if not keep_intermediates:
        for p in (notes_path, processed_path, mapped_path):
            p.unlink(missing_ok=True)
        logger.info("Intermediate files removed")

    return {
        "audio": str(audio_path),
        "output_dir": str(output_dir),
        "tab": str(tab_path),
        "midi": r5["path"] if r5 else None,
        "midi_notes": r5["note_count"] if r5 else 0,
        "notes_raw": r1["metadata"]["note_count"],
        "notes_kept": r2["metadata"]["note_count"],
        "notes_mapped": mapped,
        "measures": r4["metadata"]["measures"],
        "tempo_bpm": r4["metadata"]["tempo_bpm"],
        "instrument": resolved,
        "tuning": tuning,
        "quantize": quantize,
    }
