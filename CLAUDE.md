# CLAUDE.md — audio2tab Project Briefing

This file is read automatically at the start of every Claude Code session in
this directory. It encodes the architecture, conventions, and decisions made
so far so future sessions start with full context.

---

## Project Goal

Convert `.wav` / `.mp3` audio files — either full mixes or isolated stems
from the companion Demucs tool (`C:\Users\klgra\mp3 stem`) — into
human-readable ASCII guitar or bass tab files **and MIDI files**.

The MIDI output matters for the user's Suno workflow: record bass/guitar tracks
in Audacity, convert each to MIDI here, and upload the MIDI to Suno Studio instead
of the raw recording (Suno Studio accepts MIDI imports; whether that avoids
false copyright flags on original recordings is untested and not guaranteed).
MIDI only needs pitch, so the string/fret ambiguity of audio never matters for it.

---

## Environment

- **OS**: Windows 11
- **GPU**: RTX 5060 Ti (Blackwell) — not used by this project (Basic Pitch runs on CPU via ONNX)
- **Python venv**: `.venv` — Python 3.11.9 (64-bit), created with `py -3.11`
  (the stem maker uses its own Python 3.13 venv; the two cannot import each other — call each other's CLI)
- **TensorFlow note**: TF dropped native Windows GPU support after 2.10.
  Basic Pitch uses the **ONNX backend** (`nmp.onnx`) via `onnxruntime` to
  bypass TF entirely. Do not switch back to the TF saved model — it fails
  with `AttributeError: module 'tensorflow' has no attribute 'saved_model'`
  on the Windows Intel stub (TF 2.15).
- **Installed as package**: `pip install -e ".[gui,dev]"` — the `audio2tab`
  console script is available at `.venv\Scripts\audio2tab.exe`.

---

## Architecture

Five pipeline stages, each reading/writing a JSON intermediate (or the final file) so any stage
can be re-run without redoing earlier (expensive) work:

```
audio_to_tab/
├── core/
│   ├── pitch_extraction.py   # Stage 1 — Basic Pitch (ONNX) -> note events JSON
│   ├── note_processing.py    # Stage 2 — filter, instrument auto-detect, merge, quantize -> processed JSON
│   ├── fretboard_mapping.py  # Stage 3 — pitch -> (string, fret) -> mapped JSON
│   ├── tab_renderer.py       # Stage 4 — mapped -> ASCII tab file
│   ├── midi_export.py        # Stage 5 — processed -> .mid (tempo, guitar/bass program, velocity)
│   └── pipeline.py           # Orchestrates all stages; STAGES names; progress callback for the GUI
├── config/
│   ├── defaults.py           # SINGLE SOURCE OF TRUTH for default values + VERSION (GUI, CLI, pipeline all read it)
│   ├── settings.py           # Saved GUI settings (audio2tab_config.json, gitignored)
│   └── tunings.py            # Named tuning definitions (guitar + bass)
├── cli/
│   └── main.py               # Click CLI: run, extract, process, map, render, midi
├── gui/
│   ├── app.py                # PySide6 main window (Main / Advanced / CLI Reference tabs)
│   ├── cli_reference.py      # CLI Reference tab text, GENERATED from the real click commands
│   ├── launcher.bat          # Starts the GUI with pythonw (no console window)
│   └── widgets/
│       ├── file_picker.py    # Browse button + path display
│       ├── stage_panel.py    # Per-stage status + log panel (waiting/running/done/skipped/error)
│       └── tab_preview.py    # Monospace scrollable tab display
├── tests/                    # pytest (run: .venv\Scripts\python.exe -m pytest tests -q)
│   ├── data/guitar_six_strings_notes.json   # real recording as a fixture: open string..12th fret on all 6 strings
│   └── test_processing.py, test_midi.py, test_cli.py, test_gui.py
├── output/                   # Generated files (gitignored)
├── logs/                     # Log files
├── scratch/                  # Throwaway inspection scripts (gitignored)
├── pyproject.toml            # Package config; defines audio2tab console script; pytest config
├── requirements.txt          # Pinned deps for the venv
├── README.md                 # Short user-facing overview
├── PROJECT_PLAN.md           # Original design document
└── PROJECT_BACKLOG.md        # Backlog items
```

---

## Conventions (keep these — they mirror the stem maker at `C:\Users\klgra\mp3 stem`)

- **The GUI is a wrapper around the pipeline** (`core.pipeline.run`, the same function the CLI calls). No music logic in `gui/`.
- **Defaults live only in `config/defaults.py`.** Never hard-code a default in the CLI, GUI or a function signature;
  `tests/test_cli.py` and `tests/test_processing.py` fail if they drift. Bump `VERSION` there AND in `pyproject.toml`
  (a test checks they match).
- **Window parity with the stem maker:** Main / Advanced / CLI Reference tabs; a chosen output folder with an
  **Open Output Folder** button; settings remembered via **Save Settings**; overwrite warning before replacing files;
  launcher uses `pythonw` (no console). `gui.app.ensure_streams()` gives pythonw's missing stdout/stderr UTF-8 stand-ins
  (progress-bar block characters crashed the stem maker's model download under pythonw once).
- **Output location:** default is a `tab_output` folder beside the audio file (GUI and CLI alike); Advanced → default
  output folder overrides it.
- **Tests first for behaviour changes**, using the fixture recording; the GUI tests run Qt `offscreen` with a stand-in pipeline.
- Work on a branch / separate worktree when changing anything the desktop shortcut runs.

---

## CLI Usage

```
audio2tab run   input.wav [--tuning standard] [--out-dir DIR] [--midi/--no-midi]   # full pipeline
audio2tab extract  input.wav --out notes.json
audio2tab process  notes.json --audio input.wav --instrument auto --out processed.json
audio2tab map      processed.json --tuning bass --out mapped.json
audio2tab render   mapped.json --out song.tab
audio2tab midi     processed.json --timing played --out song.mid
```

Defaults are identical everywhere (see `config/defaults.py`): 8th-note grid, max fret 12, minimum amplitude 0.25,
harmonic filter 0.5, MIDI on with "played" timing.

---

## GUI

Launch: the `audio2tab` desktop shortcut (→ `gui\launcher.bat`) or `.venv\Scripts\pythonw.exe gui\app.py`.

- **Main tab:** input file, output folder (Choose…), Tuning / Instrument / Quantize / Measures-per-line / Max fret,
  Chord symbols, "Also save MIDI", **Run Pipeline**, **Save Tab As…**, **Open Output Folder**, five stage panels, tab preview.
- **Advanced tab:** minimum amplitude, harmonic filter (on/off + strength), release-ghost filter, MIDI timing,
  default input/output folders, **Save Settings** / **Reset to Defaults**.
- **CLI Reference tab:** generated from the real commands, so it cannot go stale.

---

## Key Design Decisions

### ONNX backend for Basic Pitch
`core/pitch_extraction.py` uses `_ONNX_MODEL_PATH = str(ICASSP_2022_MODEL_PATH) + ".onnx"`
instead of `ICASSP_2022_MODEL_PATH`. This bypasses the broken TF saved_model
loader on Windows. Do not revert to TF path.

### Instrument "auto" decides from the notes
`core.note_processing.resolve_instrument`: if fewer than `AUTO_GUITAR_LOW_SHARE` (8%) of the notes are below E2 (MIDI 40),
it is guitar and sub-E2 notes (rumble, ghosts) are dropped; otherwise bass/mix keeps the wide legacy range (28–88) so nothing
is lost. Measured on real recordings: bass lines 19–25% below E2, mixes with bass 11–13%, guitar 2–4.5%. A wrong guess errs
toward keeping notes. The decision is saved in the processed JSON (`instrument_resolved`, `low_note_share`).

### Release-ghost filter is opt-in (`--ghost-filter`)
Lifting a finger lets the string below briefly ring; Basic Pitch reports a ~58 ms, quieter note 1–2 semitones below the
note that just ended (e.g. a stray open E2 after an F2). The filter drops such blips. It is off by default because a
pull-off creates a real note that looks identical.

### Octave dedup is opt-in (`--dedup-octaves`)
Basic Pitch sometimes detects both a note and its octave harmonic on single-
instrument stems. However, a mixed recording (bass + guitar) legitimately has
notes at multiple octaves simultaneously. Dedup is off by default; pass
`--dedup-octaves` only for isolated single-instrument stems.

### Two timelines in the processed JSON
Notes are quantized in place for the tab (`start_time_s`/`end_time_s`); the as-performed times are kept as
`orig_start_time_s`/`orig_end_time_s`. MIDI export uses the as-performed times by default (keeps the feel) or the grid
times (`--timing grid`).

### Fretboard mapping window
Default position window is 5 frets. The mapper tries to stay within
`[window_start, window_start + 5]` and shifts the window when a note falls
outside. Prefer low strings (thick strings) by default — idiomatic for
bass/rhythm. Pass `--prefer-high-strings` for lead guitar feel. **Audio cannot tell which string/fret a pitch was played
on** (the same pitch exists in several places); the tab shows a plausible choice, not necessarily the one played.
Pitch itself is accurate (verified: all 78 notes of a six-string open-to-12th-fret drill recovered in order).

### Unmapped notes
Notes that fall outside the instrument's range on the chosen tuning (or above the max fret) are
flagged `"unmapped": true` in the JSON and silently skipped during rendering.
For a mixed file on guitar standard tuning, bass notes (E1/A1/G1) will be
unmapped — this is expected, not an error.

---

## Typical Workflows

**Record in Audacity → Suno Studio (the main use):** export each instrument track on its own (cleanest transcription —
no Demucs needed), then `audio2tab run bass.wav --instrument bass --tuning bass` and `audio2tab run guitar.wav`, and
import the resulting `.mid` files into Suno Studio.

**Full mix (no stem separation):**
```
audio2tab run mix_no_drums.mp3 --instrument auto --tuning standard
```

**Isolated guitar stem from Demucs:**
```
audio2tab run guitar_stem.wav --instrument guitar --tuning standard --dedup-octaves
```

**Re-render with different settings (reuse Stage 1 output — skips slow inference):**
```
audio2tab process stem_notes.json --audio stem.wav --quantize 16th --out processed.json
audio2tab map processed.json --tuning drop_d --out mapped.json
audio2tab render mapped.json --measures-per-line 2 --out song.tab
audio2tab midi processed.json --out song.mid
```

---

## Backlog

See `PROJECT_BACKLOG.md`. Key items:
- **Drum transcription** — Basic Pitch cannot do drums; would need a separate detector on a drum stem
- **Tempo map / beat grid** for MIDI (currently one detected tempo)
- **Guitar Pro export** (P2) — `.gp5`/`.gpx` via `PyGuitarPro`
- **GPU acceleration** (P2) — `onnxruntime-gpu`; current CPU speed (~minute per stem) is acceptable

---

## Companion Project

The Demucs stem separator lives at `C:\Users\klgra\mp3 stem` with its own
CLAUDE.md (and a Lyric Timing tab). Its venv uses PyTorch 2.11 + CUDA 12.8 (GPU working). That
project's output (isolated stems) is a good input for this pipeline.
