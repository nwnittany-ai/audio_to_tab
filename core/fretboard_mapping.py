"""Stage 3: map each note MIDI pitch to a (string, fret) pair.

Heuristic: play within a position window (default frets 0-5), minimising
fret-hand movement between consecutive notes. When a note falls outside the
current window, shift the window to centre on the new note.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config.tunings import get_tuning, MAX_FRET

logger = logging.getLogger(__name__)

_NO_POSITION = -1  # sentinel: note could not be mapped


def map_notes(
    processed_path: Path,
    output_path: Path,
    tuning: str = "standard",
    position_window: int = 5,
    prefer_low_strings: bool = True,
    max_fret: int = MAX_FRET,
) -> dict[str, Any]:
    """Assign each note a (string_index, fret) and write mapped JSON.

    Parameters
    ----------
    processed_path:
        JSON output from Stage 2 (note_processing).
    output_path:
        Destination JSON for mapped notes.
    tuning:
        Tuning name from config/tunings.py (e.g. "standard", "drop_d", "dadgad").
    position_window:
        Number of frets the fretting hand covers at once. Notes are played
        within [window_start, window_start + position_window]. The window
        shifts when a note cannot be reached within it.
    prefer_low_strings:
        When multiple (string, fret) options are valid, prefer the lowest-
        numbered string (thickest). Produces more idiomatic bass/rhythm tab.
        Set False to prefer higher strings / higher frets for lead guitar feel.
    max_fret:
        Hard upper limit on fret numbers. Notes that can only be played above
        this fret are marked unmapped. Default is MAX_FRET (24). Set to 12 to
        restrict to first-position playing or to filter high-fret harmonics.
    """
    processed_path = Path(processed_path)
    output_path = Path(output_path)

    data = json.loads(processed_path.read_text())
    notes: list[dict] = data["notes"]
    open_strings = get_tuning(tuning)
    n_strings = len(open_strings)

    logger.info(
        "Mapping %d notes | tuning: %s (%d strings) | window: %d frets | max_fret: %d",
        len(notes), tuning, n_strings, position_window, max_fret,
    )

    window_start = 0
    mapped = []
    unmapped = 0

    for note in notes:
        pitch = note["pitch_midi"]
        candidates = _find_candidates(pitch, open_strings, window_start, position_window, max_fret)

        if not candidates:
            # Try full fretboard (up to max_fret) before giving up
            candidates = _find_candidates(pitch, open_strings, 0, max_fret, max_fret)
            if candidates:
                best = _pick_candidate(candidates, prefer_low_strings)
                window_start = max(0, best[1] - position_window // 2)
            else:
                logger.debug("Cannot map pitch %d (%s) on tuning %s (max_fret=%d)",
                             pitch, _midi_name(pitch), tuning, max_fret)
                unmapped += 1
                mapped.append({**note, "string": None, "fret": None, "unmapped": True})
                continue
        else:
            best = _pick_candidate(candidates, prefer_low_strings)

        string_idx, fret = best
        if fret > 0 and fret > window_start + position_window:
            window_start = fret - position_window // 2
        elif fret > 0 and fret < window_start:
            window_start = max(0, fret)

        mapped.append({
            **note,
            "string": string_idx,        # 0 = lowest/thickest string
            "fret": fret,
            "unmapped": False,
        })

    logger.info(
        "Mapped %d / %d notes (%d unmapped)",
        len(mapped) - unmapped, len(mapped), unmapped,
    )

    result: dict[str, Any] = {
        "metadata": {
            "source_processed": str(processed_path),
            "tuning": tuning,
            "open_strings_midi": open_strings,
            "position_window": position_window,
            "max_fret": max_fret,
            "prefer_low_strings": prefer_low_strings,
            "note_count": len(mapped),
            "unmapped_count": unmapped,
        },
        "notes": mapped,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    logger.info("Wrote mapped notes to %s", output_path)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_candidates(
    pitch: int,
    open_strings: list[int],
    window_start: int,
    window_size: int,
    max_fret: int,
) -> list[tuple[int, int]]:
    """Return all (string_index, fret) pairs that produce *pitch* within the window."""
    candidates = []
    for s, open_pitch in enumerate(open_strings):
        fret = pitch - open_pitch
        if fret < 0 or fret > max_fret:
            continue
        if fret == 0 or (window_start <= fret <= window_start + window_size):
            candidates.append((s, fret))
    return candidates


def _pick_candidate(
    candidates: list[tuple[int, int]],
    prefer_low_strings: bool,
) -> tuple[int, int]:
    """Choose the best (string, fret) from valid candidates."""
    open_candidates = [(s, f) for s, f in candidates if f == 0]
    if open_candidates:
        candidates = open_candidates

    if prefer_low_strings:
        return min(candidates, key=lambda sf: (sf[0], sf[1]))
    else:
        return max(candidates, key=lambda sf: (sf[0], -sf[1]))


def _midi_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"
