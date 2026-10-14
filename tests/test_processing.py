"""Stage 2 (note cleaning): instrument auto-detection, sub-range notes, the optional ghost filter, as-played timing."""

from __future__ import annotations

import inspect

from config.defaults import AUTO_GUITAR_LOW_SHARE, DEFAULTS
from core import note_processing as np_
from core.note_processing import _drop_ghost_notes, _merge_fragments, _suppress_harmonics, resolve_instrument

from conftest import EXPECTED_DRILL, is_ordered_subsequence, pitches_in_time_order


def _note(pitch, start, dur=0.3, amp=0.8):
    return {"pitch_midi": pitch, "start_time_s": start, "end_time_s": start + dur, "duration_s": dur, "amplitude": amp}


# ------------------------------------------------------------------ the real recording (fixture)

def test_fixture_recording_is_detected_as_guitar(process_fixture):
    meta = process_fixture()["metadata"]
    assert meta["instrument"] == "auto" and meta["instrument_resolved"] == "guitar"
    assert meta["low_note_share"] < AUTO_GUITAR_LOW_SHARE
    assert meta["pitch_range"] == [40, 88]


def test_no_notes_below_the_lowest_guitar_string(process_fixture):
    assert min(pitches_in_time_order(process_fixture())) >= 40  # the F1 ghosts (MIDI 29) are gone


def test_explicit_bass_still_keeps_low_notes(process_fixture):
    result = process_fixture(instrument="bass")
    assert result["metadata"]["instrument_resolved"] == "bass"
    assert any(p < 40 for p in pitches_in_time_order(result))


def test_all_78_notes_of_the_six_string_drill_are_recovered_in_order(process_fixture):
    assert is_ordered_subsequence(EXPECTED_DRILL, pitches_in_time_order(process_fixture()))


def test_ghost_filter_is_off_by_default_and_removes_the_known_ghost_when_on(process_fixture):
    off, on = process_fixture(), process_fixture(ghost_filter=True)
    assert off["metadata"]["ghost_filter"] is False and off["metadata"]["ghost_removed"] == 0
    assert on["metadata"]["ghost_removed"] >= 1
    assert len(on["notes"]) == len(off["notes"]) - on["metadata"]["ghost_removed"]
    # the ghost was a 58 ms open-E2 blip that rang when the finger lifted off the F2, near the start of the drill
    assert pitches_in_time_order(off)[:5] == [40, 41, 40, 42, 43]
    assert pitches_in_time_order(on)[:5] == [40, 41, 42, 43, 44]
    assert is_ordered_subsequence(EXPECTED_DRILL, pitches_in_time_order(on))  # no real note was lost
    assert on["metadata"]["ghost_removed"] <= 6  # it targets blips, not the recording


def test_as_played_times_are_kept_next_to_the_quantized_ones(process_fixture):
    for n in process_fixture(quantize="4th")["notes"][:20]:
        assert "orig_start_time_s" in n and "orig_end_time_s" in n
        assert n["orig_end_time_s"] > n["orig_start_time_s"]


# ------------------------------------------------------------------ unit tests

def test_resolve_instrument_rules():
    guitar_like = [_note(52 + i % 12, i * 0.5) for i in range(40)] + [_note(35, 30.0)]
    assert resolve_instrument(guitar_like, "auto")[0] == "guitar"
    bass_like = [_note(30 + i % 10, i * 0.5) for i in range(40)]
    resolved, rng, share = resolve_instrument(bass_like, "auto")
    assert resolved == "bass" and rng == (28, 88) and share > AUTO_GUITAR_LOW_SHARE  # wide range kept: mixes lose nothing
    assert resolve_instrument(bass_like, "guitar")[0] == "guitar" and resolve_instrument(bass_like, "guitar")[2] is None
    assert resolve_instrument([], "auto")[0] == "guitar"


def test_ghost_filter_only_drops_short_quiet_blips_right_after_a_note_ends():
    f2 = _note(41, 1.0, dur=0.5, amp=0.74)  # F2 from 1.0 to 1.5
    blip = _note(40, 1.5, dur=0.058, amp=0.5)  # open E2 rings for 58 ms as the finger lifts
    assert [n["pitch_midi"] for n in _drop_ghost_notes([f2, blip])] == [41]
    # the same pitch as a real note: long enough to be played on purpose -> kept
    assert len(_drop_ghost_notes([f2, _note(40, 1.5, dur=0.3, amp=0.5)])) == 2
    # not right after the previous note ended -> kept
    assert len(_drop_ghost_notes([f2, _note(40, 1.7, dur=0.058, amp=0.5)])) == 2
    # as loud as its neighbour -> a real note -> kept
    assert len(_drop_ghost_notes([f2, _note(40, 1.5, dur=0.058, amp=0.7)])) == 2
    # above the previous note, or far below it -> not a release ghost
    assert len(_drop_ghost_notes([f2, _note(43, 1.5, dur=0.058, amp=0.5)])) == 2
    assert len(_drop_ghost_notes([f2, _note(36, 1.5, dur=0.058, amp=0.5)])) == 2


def test_ghost_filter_leaves_simultaneous_chord_notes_alone():
    chord = [_note(48, 1.0), _note(52, 1.0, amp=0.7), _note(55, 1.0, amp=0.7)]
    assert len(_drop_ghost_notes(chord)) == 3
    sus2 = [_note(50, 1.0, amp=0.8), _note(52, 1.0, amp=0.5)]  # D + quiet E together: neighbours, but not a release
    assert len(_drop_ghost_notes(sus2)) == 2


def test_harmonic_suppression_and_fragment_merge_still_work():
    fundamental, octave_up = _note(40, 1.0, amp=0.9), _note(52, 1.0, amp=0.3)
    assert [n["pitch_midi"] for n in _suppress_harmonics([fundamental, octave_up], 0.5)] == [40]
    merged = _merge_fragments([_note(45, 1.0, dur=0.2), _note(45, 1.25, dur=0.2)], 0.08)
    assert len(merged) == 1 and abs(merged[0]["end_time_s"] - 1.45) < 1e-9


def test_process_defaults_come_from_the_shared_defaults():
    sig = inspect.signature(np_.process).parameters
    for key in ("instrument", "min_amplitude", "min_duration_s", "merge_gap_s", "quantize", "dedup_octaves",
                "suppress_harmonics", "harmonic_ratio", "ghost_filter"):
        assert sig[key].default == DEFAULTS[key], key
