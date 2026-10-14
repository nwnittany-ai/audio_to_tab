"""Saved GUI settings (audio2tab_config.json, git-ignored), the same idea as the stem maker's drumremover_config.json.

Only values the user chooses to keep. Anything missing or unreadable falls back to the shared defaults, so a damaged
or older file can never stop the program from starting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.defaults import DEFAULTS

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "audio2tab_config.json"

# The options the window lets you keep (a subset of DEFAULTS) plus two folder preferences.
SAVED_KEYS = (
    "tuning", "instrument", "quantize", "measures_per_line", "max_fret", "chord_symbols",
    "midi", "midi_timing", "min_amplitude", "suppress_harmonics", "harmonic_ratio", "ghost_filter",
)
FOLDER_KEYS = ("default_input_dir", "default_output_dir")  # "" = ask / use the folder beside the audio file


def factory() -> dict[str, Any]:
    values = {k: DEFAULTS[k] for k in SAVED_KEYS}
    values.update({k: "" for k in FOLDER_KEYS})
    return values


def load(path: Path | None = None) -> dict[str, Any]:
    values = factory()
    try:
        stored = json.loads(Path(path or SETTINGS_PATH).read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            for key in values:
                if key in stored and isinstance(stored[key], type(values[key])):
                    values[key] = stored[key]
    except (OSError, ValueError):
        pass
    return values


def save(values: dict[str, Any], path: Path | None = None) -> None:
    keep = {k: values[k] for k in factory() if k in values}
    Path(path or SETTINGS_PATH).write_text(json.dumps(keep, indent=2), encoding="utf-8")
