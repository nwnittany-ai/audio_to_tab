"""Stage 1: pitch extraction via Basic Pitch -> list of note events saved as JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH

# Use the ONNX model — TF saved_model is broken on native Windows (TF >= 2.11 dropped
# Windows GPU, and the Intel stub has a saved_model attribute regression on 2.15).
_ONNX_MODEL_PATH = str(ICASSP_2022_MODEL_PATH) + ".onnx"

logger = logging.getLogger(__name__)

# Basic Pitch returns note events as a structured array; these are the fields we keep.
_NOTE_FIELDS = ("start_time_s", "end_time_s", "pitch_midi", "velocity", "pitch_bend")


def extract(
    audio_path: Path,
    output_path: Path,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    minimum_note_length: float = 0.058,
    minimum_frequency: float | None = 40.0,
    maximum_frequency: float | None = 2000.0,
) -> dict[str, Any]:
    """Run Basic Pitch on *audio_path*, write note events to *output_path* as JSON.

    Parameters
    ----------
    audio_path:
        Input audio file (.wav or .mp3).
    output_path:
        Destination JSON file for note events.
    onset_threshold:
        Confidence threshold for note onset detection (0-1). Lower = more notes detected.
    frame_threshold:
        Confidence threshold for note frame activation (0-1).
    minimum_note_length:
        Shortest note to keep, in seconds.
    minimum_frequency:
        Lowest pitch to keep in Hz. 40 Hz ≈ E1 (below standard bass low string).
    maximum_frequency:
        Highest pitch to keep in Hz. 2000 Hz covers most guitar/bass content.

    Returns
    -------
    dict with keys: ``notes`` (list of note dicts), ``metadata`` (extraction params).
    """
    audio_path = Path(audio_path)
    output_path = Path(output_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info("Extracting pitches from %s", audio_path.name)

    model_output, midi_data, note_events = predict(
        audio_path,
        _ONNX_MODEL_PATH,
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=minimum_note_length,
        minimum_frequency=minimum_frequency,
        maximum_frequency=maximum_frequency,
        melodia_trick=True,
        midi_tempo=120,
    )

    notes = _note_events_to_dicts(note_events)

    result: dict[str, Any] = {
        "metadata": {
            "source_file": str(audio_path),
            "onset_threshold": onset_threshold,
            "frame_threshold": frame_threshold,
            "minimum_note_length": minimum_note_length,
            "minimum_frequency": minimum_frequency,
            "maximum_frequency": maximum_frequency,
            "note_count": len(notes),
        },
        "notes": notes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    logger.info("Wrote %d note events to %s", len(notes), output_path)

    return result


def _note_events_to_dicts(note_events: Any) -> list[dict]:
    """Convert Basic Pitch note_events array to a list of plain dicts."""
    notes = []
    if note_events is None:
        return notes

    for event in note_events:
        # note_events is a list of (start, end, pitch, amplitude, pitch_bend) tuples
        start, end, pitch, amplitude, pitch_bend = event
        note = {
            "start_time_s": float(start),
            "end_time_s": float(end),
            "duration_s": float(end - start),
            "pitch_midi": int(pitch),
            "amplitude": float(amplitude),
            "pitch_bend": (
                [float(b) for b in pitch_bend]
                if pitch_bend is not None and hasattr(pitch_bend, "__iter__")
                else None
            ),
        }
        notes.append(note)

    notes.sort(key=lambda n: n["start_time_s"])
    return notes
