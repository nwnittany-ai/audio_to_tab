"""Stage 4: render (string, fret, timing) data to ASCII tab.

Layout
------
  e |---0---2---3---|---0-----------|
  B |---0---0---0---|---0-----------|
  G |---0---0---0---|---0-----------|
  D |---2---2---0---|---2-----------|
  A |---3---3---2---|---3-----------|
  E |---0---0---3---|---0-----------|
       1 e + a 2 e      1           (beat markers, optional)

Conventions
-----------
- Strings displayed high-to-low (standard tab orientation).
- Measures separated by |.
- Simultaneous notes (same quantized onset) share a column.
- Each column is wide enough for the widest fret number in that slot.
- Unmapped notes are silently skipped (logged at DEBUG level).
- Lines wrap at *measures_per_line* measures.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# String label order for display: highest string first (standard tab orientation)
_GUITAR_LABELS = ["e", "B", "G", "D", "A", "E"]
_BASS_LABELS   = ["G", "D", "A", "E"]
_BASS5_LABELS  = ["G", "D", "A", "E", "B"]


def render(
    mapped_path: Path,
    output_path: Path,
    measures_per_line: int = 4,
    time_sig_num: int = 4,
    col_padding: int = 1,
) -> dict[str, Any]:
    """Render mapped notes to ASCII tab and write to *output_path*.

    Parameters
    ----------
    mapped_path:
        JSON output from Stage 3 (fretboard_mapping).
    output_path:
        Destination .tab text file.
    measures_per_line:
        How many measures to place on each line before wrapping.
    time_sig_num:
        Beats per measure (default 4 = 4/4 time).
    col_padding:
        Extra dash characters added before each fret number for readability.
    """
    mapped_path = Path(mapped_path)
    output_path = Path(output_path)

    data = json.loads(mapped_path.read_text())
    notes = data["notes"]
    meta = data["metadata"]
    open_strings: list[int] = meta["open_strings_midi"]
    n_strings = len(open_strings)
    tempo_bpm: float = _get_tempo(mapped_path)
    quantize_subdiv: int = _get_subdivisions(mapped_path)

    string_labels = _pick_labels(n_strings)
    # Tab displays highest string (last in open_strings list) at top
    display_order = list(range(n_strings - 1, -1, -1))

    steps_per_beat = quantize_subdiv // 4
    steps_per_measure = time_sig_num * steps_per_beat
    beat_s = 60.0 / tempo_bpm
    step_s = beat_s / steps_per_beat

    # Build a grid: grid[measure][step] -> list of (string_idx, fret)
    grid: dict[int, dict[int, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    skipped = 0

    for note in notes:
        if note.get("unmapped"):
            skipped += 1
            continue
        s, f = note["string"], note["fret"]
        onset = note["start_time_s"]
        step_abs = round(onset / step_s)
        measure = step_abs // steps_per_measure
        step_in_measure = step_abs % steps_per_measure
        grid[measure][step_in_measure].append((s, f))

    if skipped:
        logger.debug("Skipped %d unmapped notes during render", skipped)

    total_measures = max(grid.keys()) + 1 if grid else 0
    logger.info("Rendering %d measures (%d unmapped notes skipped)", total_measures, skipped)

    # Render measure by measure, grouped into lines
    lines_out: list[str] = []
    label_width = max(len(l) for l in string_labels) + 2  # "E |" etc.

    for line_start in range(0, total_measures, measures_per_line):
        line_measures = range(line_start, min(line_start + measures_per_line, total_measures))

        # Build each measure's column data
        measure_cols: list[list[list[str]]] = []  # [measure][step][string] = char
        for m in line_measures:
            cols: list[list[str]] = []
            for step in range(steps_per_measure):
                events = grid[m].get(step, [])
                col = ["-"] * n_strings
                for s_idx, fret in events:
                    col[s_idx] = str(fret)
                cols.append(col)
            measure_cols.append(cols)

        # Determine column widths (each col = max fret digit width + padding)
        col_widths: list[list[int]] = []
        for cols in measure_cols:
            widths = []
            for col in cols:
                w = max(len(c) for c in col) + col_padding
                widths.append(w)
            col_widths.append(widths)

        # Render each string as a row
        string_rows: list[list[str]] = [[] for _ in range(n_strings)]

        for m_idx, (cols, widths) in enumerate(zip(measure_cols, col_widths)):
            for step_idx, (col, w) in enumerate(zip(cols, widths)):
                for s_idx in range(n_strings):
                    cell = col[s_idx]
                    # Pad: fret number left-justified, rest filled with dashes
                    string_rows[s_idx].append(cell.ljust(w, "-"))
            # Measure separator
            for s_idx in range(n_strings):
                string_rows[s_idx].append("|")

        # Format output lines (display order: highest string first)
        for display_idx, s_idx in enumerate(display_order):
            label = string_labels[display_idx].rjust(label_width - 2) + " |"
            row_str = "".join(string_rows[s_idx])
            lines_out.append(label + row_str)
        lines_out.append("")  # blank line between tab line groups

    tab_text = "\n".join(lines_out)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tab_text, encoding="utf-8")
    logger.info("Wrote ASCII tab to %s", output_path)

    result: dict[str, Any] = {
        "metadata": {
            "source_mapped": str(mapped_path),
            "measures": total_measures,
            "tempo_bpm": tempo_bpm,
            "time_signature": f"{time_sig_num}/4",
            "quantize_subdivisions": quantize_subdiv,
            "measures_per_line": measures_per_line,
            "unmapped_skipped": skipped,
        },
        "output_file": str(output_path),
    }
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_labels(n_strings: int) -> list[str]:
    """Return string label list (high to low) for the given string count."""
    if n_strings == 4:
        return _BASS_LABELS
    if n_strings == 5:
        return _BASS5_LABELS
    return _GUITAR_LABELS[:n_strings]


def _get_tempo(mapped_path: Path) -> float:
    """Walk back through intermediate JSONs to find tempo."""
    data = json.loads(mapped_path.read_text())
    proc_path = Path(data["metadata"].get("source_processed", ""))
    if proc_path.exists():
        proc = json.loads(proc_path.read_text())
        return float(proc["metadata"].get("tempo_bpm", 120.0))
    return 120.0


def _get_subdivisions(mapped_path: Path) -> int:
    """Walk back to find the quantize subdivision count."""
    _SUBDIV_MAP = {"4th": 4, "8th": 8, "16th": 16, "32nd": 32}
    data = json.loads(mapped_path.read_text())
    proc_path = Path(data["metadata"].get("source_processed", ""))
    if proc_path.exists():
        proc = json.loads(proc_path.read_text())
        q = proc["metadata"].get("quantize", "16th")
        return _SUBDIV_MAP.get(q, 16)
    return 16
