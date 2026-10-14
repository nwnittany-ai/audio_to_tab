"""Single source of truth for audio2tab's default option values and version.

The GUI, the command line and the pipeline all read their defaults from here, so they cannot drift apart
(they used to: three different sets of values). Change a default here and every entry point follows.
"""

from __future__ import annotations

VERSION = "0.2.0"

DEFAULTS: dict = {
    # --- tab layout / mapping ---
    "tuning": "standard",
    "instrument": "auto",          # auto | guitar | bass  (auto decides from the notes themselves)
    "quantize": "8th",             # 4th | 8th | 16th | 32nd
    "measures_per_line": 4,
    "position_window": 5,
    "max_fret": 12,                # first position; raise to 24 for high-fret leads
    "chord_symbols": False,
    # --- note detection (Basic Pitch) ---
    "onset_threshold": 0.5,
    "frame_threshold": 0.3,
    # --- note cleaning ---
    "min_amplitude": 0.25,
    "min_duration_s": 0.05,
    "merge_gap_s": 0.08,
    "suppress_harmonics": True,
    "harmonic_ratio": 0.5,
    "dedup_octaves": False,
    "ghost_filter": False,         # opt-in: drop short "release ghost" notes (see GHOST_* below)
    # --- MIDI export ---
    "midi": True,
    "midi_timing": "played",       # played = as performed (keeps the feel) | grid = snapped to the quantize grid
}

# "auto" instrument: if fewer than this share of the notes lie below E2 (MIDI 40, the lowest guitar string),
# the recording is treated as guitar. Measured on real recordings: bass lines 19-25%, mixes with bass 11-13%,
# guitar 2-4.5%. A wrong guess errs toward keeping notes (treating guitar as bass), never toward losing them.
AUTO_GUITAR_LOW_SHARE = 0.08
GUITAR_LOWEST_MIDI = 40            # E2

# Release-ghost filter (opt-in): lifting a finger off a fretted note lets the string below briefly ring, which the
# detector reports as a very short, quieter note starting exactly when the previous note ends. A note is dropped when
# it is 1-2 semitones BELOW a note that just ended (start within GHOST_START_TOLERANCE_S of that end), lasts at most
# GHOST_MAX_DURATION_S, and is quieter than GHOST_RATIO x that note. A pull-off makes a real note that looks the same,
# which is why this stays off by default.
GHOST_START_TOLERANCE_S = 0.04
GHOST_MAX_DURATION_S = 0.12
GHOST_RATIO = 0.8
GHOST_MAX_INTERVAL = 2

QUANTIZE_CHOICES = ("4th", "8th", "16th", "32nd")
INSTRUMENT_CHOICES = ("auto", "guitar", "bass")
MIDI_TIMING_CHOICES = ("played", "grid")
