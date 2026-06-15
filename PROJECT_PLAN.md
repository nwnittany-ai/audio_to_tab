# Audio → Guitar/Bass Tab Transcription Tool — Project Plan

## Goal

Take a `.wav`/`.mp3` file — either a full song or an isolated stem (from the
existing Demucs-based separator) — and produce a human-readable guitar or
bass tab file.

## Environment

- **OS**: Windows 11 (development and runtime)
- **GPU**: RTX 5060 Ti (already used for Demucs stem separation; check
  whether native Windows TensorFlow gets CUDA acceleration, or whether
  WSL2 is needed — same consideration as the existing Demucs setup)
- **Paths**: use `pathlib` throughout for cross-shell robustness
  (PowerShell / cmd / WSL)
- **CLI invocation**: either package with `pip install -e .` for a console
  script entry point, or run via `python -m audio2tab ...`

## Architecture

```
audio_to_tab/
├── core/
│   ├── pitch_extraction.py   # Basic Pitch wrapper -> note events
│   ├── note_processing.py    # quantize, filter noise, merge fragments
│   ├── fretboard_mapping.py  # note -> string/fret assignment
│   ├── tab_renderer.py       # note/fret data -> ASCII or text tab
│   └── pipeline.py           # orchestrates the above stages
├── config/
│   └── tunings.py            # standard + open tuning definitions
├── cli/
│   └── main.py               # CLI entry point with subcommands
├── gui/
│   ├── app.py                # main window / entry point
│   ├── widgets/
│   │   ├── file_picker.py
│   │   ├── stage_panel.py    # per-stage run/inspect controls
│   │   └── tab_preview.py    # rendered tab display
│   └── launcher.bat          # double-click entry (calls python gui/app.py)
├── logs/
├── tests/
└── output/
```

## Pipeline Stages

Each stage reads/writes JSON intermediates, so any stage can be re-run
independently without redoing earlier (expensive/GPU) work.

1. **Pitch extraction** (`extract`)
   Audio file -> list of note events (pitch, onset, duration, confidence)
   via Basic Pitch. Output saved as intermediate JSON for inspection.

2. **Note processing** (`process`)
   Clean up raw note list: merge fragmented notes, filter low-confidence
   detections, quantize timing to a grid (e.g., 16th notes) based on
   detected tempo.

3. **Fretboard mapping** (`map`)
   Map each pitch to a (string, fret) pair, config-driven by tuning
   (including open tunings). Heuristic: minimize fret-hand movement,
   prefer lower frets within a configurable position window.

4. **Tab rendering** (`render`)
   Convert (string, fret, timing) data into readable ASCII tab, grouped
   into measures based on detected tempo/time signature.

5. **Pipeline orchestration** (`run`)
   Chains all stages end-to-end.

## CLI Design

```
audio2tab extract  input.wav --out notes.json
audio2tab process  notes.json --out processed.json --quantize 16th
audio2tab map      processed.json --tuning dadgad --out mapped.json
audio2tab render   mapped.json --out song.tab
audio2tab run      input.wav --tuning dadgad --out song.tab
```

## Desktop GUI Launcher

A full GUI sits on top of the same `core/` pipeline modules used by the CLI
— no duplicated logic, just a different front end.

- **Framework**: `PySide6` (Qt) — native Windows look, handles monospace
  text rendering well for the tab preview
- **Layout**:
  - File picker for input audio (`.wav` / `.mp3`)
  - Tuning selector dropdown (from `config/tunings.py`)
  - Stage panel: Extract → Process → Map → Render, each runnable
    individually with status/output shown (note counts, confidence
    stats, mapping decisions — mirrors log output)
  - Tab preview pane: monospace view of the rendered ASCII tab
  - "Run All" button for the full pipeline
- **Launch**: `gui/launcher.bat` runs `python gui/app.py`; a desktop
  shortcut can point at this `.bat` for double-click access

## Logging

Standard Python `logging` module, configurable verbosity, per-stage log
entries (note counts, confidence stats, mapping decisions) written to
`logs/`. GUI stage panel surfaces the same information.

## Configuration

- `config/tunings.py`: named tunings (standard, drop D, DADGAD, open G,
  etc.), easy to extend
- Thresholds (confidence cutoff, quantization grid, fret-position
  preferences) in config, not hardcoded

## Third-Party Libraries

| Library | Purpose |
|---|---|
| `basic-pitch` (Spotify) | audio -> note events, GPU-capable via TensorFlow |
| `librosa` | audio loading, tempo/beat detection, audio utilities |
| `pretty_midi` | optional MIDI export step |
| `numpy` | array math |
| `click` | CLI framework with subcommands |
| `pydantic` | schema validation for JSON intermediates |
| `pytest` | unit tests per stage |
| `PySide6` | desktop GUI framework |

Optional later:
- `mido` — lower-level MIDI if `pretty_midi` is insufficient
- `PyGuitarPro` — export to `.gp5`/`.gpx` for Guitar Pro compatibility

## Future Upgrade Paths

- Swap fretboard mapping heuristic for chord-shape recognition
- Add a Guitar Pro format renderer alongside ASCII
- "Diff against known performance" mode for self-transcription accuracy
- Plug in alternative pitch-extraction models if Basic Pitch underperforms
- GUI enhancements: waveform display, playback-synced tab scrolling,
  manual fret-position override in the Map stage

## Implementation Approach (Claude Code)

1. Create the project folder structure (below) on the Windows machine.
2. Place this file in the project root as `PROJECT_PLAN.md`.
3. Launch Claude Code in that directory (`claude`).
4. Direct it to read `PROJECT_PLAN.md` and implement stage 1 (pitch
   extraction) first — most expensive/slow step, build and test in
   isolation.
5. Proceed stage by stage (`extract` -> `process` -> `map` -> `render`),
   using each CLI subcommand as a checkpoint with real stem data before
   moving to the next stage.
6. Before stage 1, verify GPU/CUDA setup for TensorFlow on Windows
   (native vs. WSL2) against the existing Demucs configuration.
7. Once the CLI pipeline works end-to-end, build the GUI shell
   (`gui/app.py`) wrapping `pipeline.py`, then add `launcher.bat` and a
   desktop shortcut.

## Project Setup (Directories)

```
mkdir audio_to_tab
cd audio_to_tab
mkdir core
mkdir config
mkdir cli
mkdir gui
mkdir gui\widgets
mkdir logs
mkdir tests
mkdir output
```
