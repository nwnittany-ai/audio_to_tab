"""Stage 5 (MIDI export)."""

from __future__ import annotations

import json

import pretty_midi
import pytest

from core.midi_export import MIN_VELOCITY, export

from conftest import EXPECTED_DRILL, is_ordered_subsequence


def _load(path):
    return pretty_midi.PrettyMIDI(str(path))


def test_export_writes_a_valid_midi_file_with_every_note(process_fixture, tmp_path):
    result = process_fixture()
    out = tmp_path / "song.mid"
    summary = export(tmp_path / "processed.json", out)
    assert out.read_bytes()[:4] == b"MThd"  # a standard MIDI header
    midi = _load(out)
    assert len(midi.instruments) == 1 and len(midi.instruments[0].notes) == len(result["notes"]) == summary["note_count"]
    pitches = [n.pitch for n in sorted(midi.instruments[0].notes, key=lambda n: (n.start, n.pitch))]
    assert sorted(pitches) == sorted(n["pitch_midi"] for n in result["notes"])
    assert is_ordered_subsequence(EXPECTED_DRILL, pitches)  # the six-string drill is all there, in order


def test_guitar_and_bass_get_the_matching_instrument(process_fixture, tmp_path):
    process_fixture()
    guitar = export(tmp_path / "processed.json", tmp_path / "g.mid")
    assert guitar["instrument"] == "guitar" and guitar["program"] == 25
    assert pretty_midi.program_to_instrument_name(_load(tmp_path / "g.mid").instruments[0].program) == "Acoustic Guitar (steel)"
    process_fixture(instrument="bass")
    bass = export(tmp_path / "processed.json", tmp_path / "b.mid")
    assert bass["instrument"] == "bass" and bass["program"] == 33
    assert pretty_midi.program_to_instrument_name(_load(tmp_path / "b.mid").instruments[0].program) == "Electric Bass (finger)"


def test_tempo_and_time_signature_are_written(process_fixture, tmp_path):
    process_fixture(tempo_override=93.75)
    export(tmp_path / "processed.json", tmp_path / "t.mid")
    midi = _load(tmp_path / "t.mid")
    assert abs(midi.estimate_tempo() - 93.75) < 0.5 or abs(midi.get_tempo_changes()[1][0] - 93.75) < 0.1
    ts = midi.time_signature_changes[0]
    assert (ts.numerator, ts.denominator) == (4, 4)


def test_played_timing_keeps_the_performance_and_grid_timing_snaps(process_fixture, tmp_path):
    result = process_fixture(quantize="4th")  # a coarse grid so the two timings clearly differ
    played = export(tmp_path / "processed.json", tmp_path / "p.mid", timing="played")
    grid = export(tmp_path / "processed.json", tmp_path / "g.mid", timing="grid")
    assert played["timing"] == "played" and grid["timing"] == "grid"
    p_notes = sorted(_load(tmp_path / "p.mid").instruments[0].notes, key=lambda n: (n.start, n.pitch))
    g_notes = sorted(_load(tmp_path / "g.mid").instruments[0].notes, key=lambda n: (n.start, n.pitch))
    src = sorted(result["notes"], key=lambda n: (n["start_time_s"], n["pitch_midi"]))
    # played: the as-performed onsets; grid: the snapped onsets (compare as sorted multisets: ordering can tie)
    assert sorted(n.start for n in p_notes) == pytest.approx(sorted(n["orig_start_time_s"] for n in src), abs=0.01)  # MIDI ticks are ~3 ms
    assert sorted(n.start for n in g_notes) == pytest.approx(sorted(n["start_time_s"] for n in src), abs=0.01)
    assert sorted(round(n.start, 2) for n in p_notes) != sorted(round(n.start, 2) for n in g_notes)


def test_velocity_follows_loudness_and_every_note_has_length(process_fixture, tmp_path):
    process_fixture()
    export(tmp_path / "processed.json", tmp_path / "v.mid")
    notes = _load(tmp_path / "v.mid").instruments[0].notes
    assert all(MIN_VELOCITY <= n.velocity <= 127 for n in notes)
    assert len({n.velocity for n in notes}) > 10  # not one flat value
    assert all(n.end > n.start for n in notes)


def test_older_processed_files_without_as_played_times_still_export(tmp_path):
    old = {"metadata": {"tempo_bpm": 110, "instrument": "auto"},
           "notes": [{"pitch_midi": 45, "start_time_s": 0.0, "end_time_s": 0.5, "duration_s": 0.5, "amplitude": 0.6},
                     {"pitch_midi": 33, "start_time_s": 0.5, "end_time_s": 1.0, "duration_s": 0.5, "amplitude": 0.6}]}
    (tmp_path / "old_processed.json").write_text(json.dumps(old))
    summary = export(tmp_path / "old_processed.json", tmp_path / "old.mid")
    assert summary["note_count"] == 2 and summary["instrument"] in ("guitar", "bass")
    assert [n.pitch for n in _load(tmp_path / "old.mid").instruments[0].notes] == [45, 33]


def test_bad_timing_is_rejected_and_empty_notes_are_handled(tmp_path):
    (tmp_path / "empty_processed.json").write_text(json.dumps({"metadata": {"tempo_bpm": 100}, "notes": []}))
    with pytest.raises(ValueError):
        export(tmp_path / "empty_processed.json", tmp_path / "x.mid", timing="sometimes")
    assert export(tmp_path / "empty_processed.json", tmp_path / "e.mid")["note_count"] == 0
    assert (tmp_path / "e.mid").exists()
