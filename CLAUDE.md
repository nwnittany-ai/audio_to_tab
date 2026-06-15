# CLAUDE.md — audio2tab Project Briefing

This file is read automatically at the start of every Claude Code session in
this directory. It encodes the architecture, conventions, and decisions made
during the initial build so future sessions start with full context.

---

## Project Goal

Convert `.wav` / `.mp3` audio files — either full mixes or isolated stems
from the companion Demucs tool (`C:\Users\klgra\mp3 stem`) — into
human-readable ASCII guitar or bass tab files.

---

## Environment

- **OS**: Windows 11
- **GPU**: RTX 5060 Ti (Blackwell) — CUDA 12.8 / driver 596.49
- **Python venv**: `.venv` — Python 3.11.9 (64-bit), created with `py -3.11`
- **TensorFlow note**: TF dropped native Windows GPU support after 2.10.
  Basic Pitch uses the **ONNX backend** (`nmp.onnx`) via `onnxruntime` to
  bypass TF entirely. Do not switch back to the TF saved model — it fails
  with `AttributeError: module 'tensorflow' has no attribute 'saved_model'`
  on the Windows Intel stub (TF 2.15).
- **Installed as package**: `pip install -e ".[gui,dev]"` — the `audio2tab`
  console script is available at `.venv\Scripts\audio2tab.exe`.

---

## Architecture

Four pipeline stages, each reading/writing a JSON intermediate so any stage
can be re-run without redoing earlier (expensive) work:

```
audio_to_tab/
├── core/
│   ├── pitch_extraction.py   # Stage 1 — Basic Pitch (ONNX) -> note events JSON
│   ├── note_processing.py    # Stage 2 — filter, merge, quantize -> processed JSON
│   ├── fretboard_mapping.py  # Stage 3 — pitch -> (string, fret) -> mapped JSON
│   ├── tab_renderer.py       # Stage 4 — mapped -> ASCII tab file
│   └── pipeline.py           # Orchestrates all four stages end-to-end
├── config/
│   └── tunings.py            # Named tuning definitions (guitar + bass)
├── cli/
│   └── main.py               # Click CLI with: extract, process, map, render, run
├── gui/
│   ├── app.py                # PySide6 main window
│   ├── cli_reference.py      # CLI reference text + Help dialog
│   └── widgets/
│       ├── file_picker.py    # Browse button + path display
│       ├── stage_panel.py    # Per-stage status + log panel
│       └── tab_preview.py    # Monospace scrollable tab display
├── output/                   # Generated files (gitignored)
├── logs/                     # Log files
├── tests/                    # pytest unit tests (not yet written)
├── pyproject.toml            # Package config; defines audio2tab console script
├── requirements.txt          # Pinned deps for the venv
├── PROJECT_PLAN.md           # Original design document
└── PROJECT_BACKLOG.md        # Backlog items (GPU, Guitar Pro export, etc.)
```

---

## CLI Usage

All commands available after activating the venv or via `.venv\Scripts\audio2tab.exe`:

```
audio2tab run   input.wav --tuning standard --out-dir output/   # full pipeline
audio2tab extract  input.wav --out notes.json
audio2tab process  notes.json --audio input.wav --instrument bass --out processed.json
audio2tab map      processed.json --tuning bass --out mapped.json
audio2tab render   mapped.json --out song.tab
```

Default quantization is **8th notes** for the `run` command (more readable
at typical tempos). Individual `process` stage defaults to 16th notes.

---

## GUI

Launch: `gui\launcher.bat` or `.venv\Scripts\python.exe gui\app.py`

- **File → Open Audio File** or the Browse button to select input
- Tuning / Instrument / Quantize / Measures-per-line dropdowns
- **Run Pipeline** button — runs all 4 stages in a background thread
- Stage panels show live status and log output per stage
- Tab preview pane shows the rendered ASCII tab on completion
- **Help → CLI Reference** — full command reference in a scrollable dialog
- **File → Save Tab As** — save the rendered tab to a chosen location

---

## Key Design Decisions

### ONNX backend for Basic Pitch
`core/pitch_extraction.py` uses `_ONNX_MODEL_PATH = str(ICASSP_2022_MODEL_PATH) + ".onnx"`
instead of `ICASSP_2022_MODEL_PATH`. This bypasses the broken TF saved_model
loader on Windows. Do not revert to TF path.

### Octave dedup is opt-in (`--dedup-octaves`)
Basic Pitch sometimes detects both a note and its octave harmonic on single-
instrument stems. However, a mixed recording (bass + guitar) legitimately has
notes at multiple octaves simultaneously. Dedup is off by default; pass
`--dedup-octaves` only for isolated single-instrument stems.

### Quantization defaults
- `audio2tab run`: defaults to `8th` — more readable line widths at typical tempos
- `audio2tab process`: defaults to `16th` — preserves more timing detail when
  running stages individually

### Fretboard mapping window
Default position window is 5 frets. The mapper tries to stay within
`[window_start, window_start + 5]` and shifts the window when a note falls
outside. Prefer low strings (thick strings) by default — idiomatic for
bass/rhythm. Pass `--prefer-high-strings` for lead guitar feel.

### Unmapped notes
Notes that fall outside the instrument's range on the chosen tuning are
flagged `"unmapped": true` in the JSON and silently skipped during rendering.
For a mixed file on guitar standard tuning, bass notes (E1/A1/G1) will be
unmapped — this is expected, not an error.

---

## Typical Workflows

**Full mix (no stem separation):**
```
audio2tab run mix_no_drums.mp3 --instrument auto --tuning standard
```

**Isolated guitar stem from Demucs:**
```
audio2tab run guitar_stem.wav --instrument guitar --tuning standard --dedup-octaves
```

**Isolated bass stem from Demucs:**
```
audio2tab run bass_stem.wav --instrument bass --tuning bass --dedup-octaves
```

**Re-render with different settings (reuse Stage 1 output — skips slow inference):**
```
audio2tab process stem_notes.json --audio stem.wav --quantize 16th --out processed.json
audio2tab map processed.json --tuning drop_d --out mapped.json
audio2tab render mapped.json --measures-per-line 2 --out song.tab
```

---

## Backlog

See `PROJECT_BACKLOG.md`. Key items:
- **GPU acceleration** (P2) — TF-DirectML or WSL2; `onnxruntime-gpu` may also
  work natively on Windows with CUDA — worth investigating before WSL2 path
- **Guitar Pro export** (P2) — `.gp5`/`.gpx` via `PyGuitarPro`
- **Tests** (P1) — pytest unit tests for each stage; not yet written

---

## Companion Project

The Demucs stem separator lives at `C:\Users\klgra\mp3 stem` with its own
CLAUDE.md. Its venv uses PyTorch 2.11 + CUDA 12.8 (GPU working). That
project's output (isolated stems) is the ideal input for this pipeline.
