"""Named tuning definitions — MIDI note numbers for each open string, low to high."""

from __future__ import annotations

# Each tuning is a list of open-string MIDI pitches, lowest string first.
# Standard MIDI: E2=40, A2=45, D3=50, G3=55, B3=59, E4=64
# Bass octave lower: E1=28, A1=33, D2=38, G2=43

GUITAR_TUNINGS: dict[str, list[int]] = {
    "standard":  [40, 45, 50, 55, 59, 64],   # E A D G B e
    "drop_d":    [38, 45, 50, 55, 59, 64],   # D A D G B e
    "open_g":    [38, 43, 50, 55, 59, 62],   # D G D G B D
    "open_d":    [38, 45, 50, 54, 57, 62],   # D A D F# A D
    "dadgad":    [38, 45, 50, 55, 57, 62],   # D A D G A D
    "half_step_down": [39, 44, 49, 54, 58, 63],  # Eb Ab Db Gb Bb eb
    "full_step_down": [38, 43, 48, 53, 57, 62],  # D G C F A d
}

BASS_TUNINGS: dict[str, list[int]] = {
    "standard":  [28, 33, 38, 43],   # E A D G
    "drop_d":    [26, 33, 38, 43],   # D A D G
    "5string":   [23, 28, 33, 38, 43],  # B E A D G
    "half_step_down": [27, 32, 37, 42],  # Eb Ab Db Gb
}

ALL_TUNINGS: dict[str, list[int]] = {
    **{f"guitar_{k}": v for k, v in GUITAR_TUNINGS.items()},
    **{f"bass_{k}": v for k, v in BASS_TUNINGS.items()},
}

# Convenient aliases without prefix
ALL_TUNINGS.update(GUITAR_TUNINGS)
ALL_TUNINGS["bass"] = BASS_TUNINGS["standard"]
ALL_TUNINGS["guitar"] = GUITAR_TUNINGS["standard"]

MAX_FRET = 24


def get_tuning(name: str) -> list[int]:
    """Return open-string MIDI pitches for *name*, raising ValueError if unknown."""
    if name not in ALL_TUNINGS:
        available = ", ".join(sorted(ALL_TUNINGS))
        raise ValueError(f"Unknown tuning '{name}'. Available: {available}")
    return ALL_TUNINGS[name]
