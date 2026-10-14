"""Shared test helpers. Tests never need Basic Pitch or any audio: they start from saved note events."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"

# What the fixture recording contains: the open string up to the 12th fret on each of the six guitar strings.
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
SIX_STRING_RUNS = [list(range(open_midi, open_midi + 13)) for open_midi in (40, 45, 50, 55, 59, 64)]
EXPECTED_DRILL = [m for run in SIX_STRING_RUNS for m in run]  # 78 notes: E2..E3, A2..A3, D3..D4, G3..G4, B3..B4, E4..E5


def note_name(midi: int) -> str:
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def is_ordered_subsequence(needle: list[int], haystack: list[int]) -> bool:
    it = iter(haystack)
    return all(any(h == n for h in it) for n in needle)


@pytest.fixture
def raw_notes_path() -> Path:
    return DATA / "guitar_six_strings_notes.json"


@pytest.fixture
def process_fixture(tmp_path, raw_notes_path):
    """Run Stage 2 on the fixture with the settings that reproduce the known-good recording; returns the result."""
    from core.note_processing import process

    def run(**overrides):
        kwargs = dict(notes_path=raw_notes_path, output_path=tmp_path / "processed.json", audio_path=None,
                      min_amplitude=0.5, harmonic_ratio=0.7, tempo_override=100.0)
        kwargs.update(overrides)
        return process(**kwargs)

    return run


def pitches_in_time_order(result: dict) -> list[int]:
    return [n["pitch_midi"] for n in sorted(result["notes"], key=lambda n: (n["start_time_s"], n["pitch_midi"]))]
