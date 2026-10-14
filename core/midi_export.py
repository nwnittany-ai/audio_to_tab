"""Stage 5: write the cleaned notes as a standard MIDI file (.mid).

Only pitch matters for MIDI, so (unlike the tab) nothing here depends on which string or fret was used: the
string/fret ambiguity of audio never comes into play. The file carries the detected tempo, a 4/4 time signature,
and one track labelled and programmed as guitar or bass; note loudness comes from the detected amplitude.

Timing: "played" (default) writes the notes exactly as they were performed, keeping the feel; "grid" writes them
snapped to the quantize grid used for the tab. Pitch bends are not exported.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pretty_midi

from config.defaults import DEFAULTS, MIDI_TIMING_CHOICES
from core.note_processing import resolve_instrument

logger = logging.getLogger(__name__)

# General MIDI program numbers (0-based, as pretty_midi uses): 25 = Acoustic Guitar (steel), 33 = Electric Bass (finger)
PROGRAMS = {"guitar": (25, "Guitar"), "bass": (33, "Bass")}
MIN_NOTE_LENGTH_S = 0.02
MIN_VELOCITY = 30


def _velocity(amplitude: float) -> int:
    return int(max(MIN_VELOCITY, min(127, round(amplitude * 127))))


def _instrument(meta: dict, notes: list[dict]) -> str:
    resolved = meta.get("instrument_resolved")
    if resolved in PROGRAMS:
        return resolved
    requested = meta.get("instrument", "auto")
    if requested in PROGRAMS:
        return requested
    return resolve_instrument(notes, "auto")[0]  # older processed files that predate the decision being saved


def export(
    processed_path: Path,
    output_path: Path,
    timing: str = DEFAULTS["midi_timing"],
    tempo_override: float | None = None,
) -> dict[str, Any]:
    """Write *output_path* (.mid) from a processed-notes JSON (Stage 2 output).

    Returns a summary dict: path, note_count, tempo_bpm, instrument, program, timing, duration_s.
    """
    if timing not in MIDI_TIMING_CHOICES:
        raise ValueError(f"timing must be one of {', '.join(MIDI_TIMING_CHOICES)} (got {timing!r})")
    processed_path, output_path = Path(processed_path), Path(output_path)
    data = json.loads(processed_path.read_text())
    meta, notes = data.get("metadata", {}), data["notes"]

    tempo = float(tempo_override or meta.get("tempo_bpm") or 120.0)
    instrument = _instrument(meta, notes)
    program, name = PROGRAMS[instrument]

    midi = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    midi.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0.0))
    track = pretty_midi.Instrument(program=program, name=name)
    for n in sorted(notes, key=lambda n: (n["start_time_s"], n["pitch_midi"])):
        pitch = int(n["pitch_midi"])
        if not 0 <= pitch <= 127:
            continue
        if timing == "played":
            start = float(n.get("orig_start_time_s", n["start_time_s"]))
            end = float(n.get("orig_end_time_s", n["end_time_s"]))
        else:
            start, end = float(n["start_time_s"]), float(n["end_time_s"])
        end = max(end, start + MIN_NOTE_LENGTH_S)
        track.notes.append(pretty_midi.Note(velocity=_velocity(float(n.get("amplitude", 0.7))),
                                            pitch=pitch, start=start, end=end))
    midi.instruments.append(track)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(output_path))
    summary = {
        "path": str(output_path),
        "note_count": len(track.notes),
        "tempo_bpm": round(tempo, 2),
        "instrument": instrument,
        "program": program,
        "timing": timing,
        "duration_s": round(midi.get_end_time(), 2),
    }
    logger.info("Wrote %d notes (%s, %s timing, %.1f BPM) to %s", summary["note_count"], instrument, timing, tempo,
                output_path.name)
    return summary
