# audio_to_tab — Project Backlog

## P1 — Next (Suno workflow)

| Item | Description |
|------|-------------|
| **Try the MIDI in Suno Studio** | Import a `.mid` from this tool into Suno Studio (the September 2026 release notes say MIDI import is supported there). Confirm accepted file types and size, whether one multi-track file or one file per instrument is wanted, and whether it behaves better than uploading the raw recording. Untested. |
| **Combine tracks into one multi-track .mid** | `audio2tab merge bass.mid guitar.mid --out song.mid` (or in the window), so Suno Studio gets one file with named bass and guitar tracks. |
| **Drum track** | Basic Pitch only finds pitched notes. A drum-hit detector (kick/snare/hat) on a drum track would give a MIDI drum track; or leave drums out and let Suno make its own. |

## P2 — Low Priority Enhancements

| Item | Description |
|------|-------------|
| **GPU acceleration for Basic Pitch** | TensorFlow dropped native Windows GPU support after TF 2.10. Options to investigate: (1) TF-DirectML plugin (`tensorflow-directml`) for Windows GPU via DirectX; (2) WSL2 with TF 2.x + CUDA 12.x; (3) replace Basic Pitch TF backend with an ONNX runtime path (`onnxruntime-gpu`) if Basic Pitch exposes one. Current implementation runs CPU-only; inference on a 3-4 min stem is ~30-60s which is acceptable for now. |
| **Guitar Pro export** | Add a `.gp5`/`.gpx` renderer alongside ASCII tab using `PyGuitarPro`. |
| **Chord-shape recognition** | Upgrade fretboard mapping from position-window heuristic to chord-shape-aware algorithm. |
| **Diff against known tab** | "Self-transcription accuracy" mode — compare generated tab to a reference tab file. |
| **Waveform display in GUI** | Visual waveform preview in the GUI with playback-synced tab scrolling. |
| **Manual fret override in GUI** | Let user adjust fret-position assignments in the Map stage via the GUI. |
| **Tempo map / beat grid** | MIDI currently carries one detected tempo. Beat tracking would give a proper bar grid (and downbeats usable for video cuts). |
| **"Play on this string" hint** | Audio cannot tell which string a pitch was played on; a preferred string/position option would reproduce drills such as open-string-to-12th-fret on one string. Not needed for MIDI. |
| **MIDI pitch bends** | Basic Pitch detects them; they are not exported yet. |

## P3 — Future / Speculative

| Item | Description |
|------|-------------|
| **Plug-in alternate pitch models** | Architecture hook to swap Basic Pitch for another model (e.g., CREPE, pYIN) if quality is insufficient. |
| ~~**Desktop shortcut**~~ | ~~`.lnk` or `.bat` launcher for double-click GUI launch without opening PowerShell.~~ **Done** — `audio2tab.lnk` on desktop, targets `gui\launcher.bat`. |

## Done

- v0.2.0: pytest suite with a real-recording fixture; shared defaults (`config/defaults.py`); MIDI export and a `midi` command; instrument auto-detection (drops impossible sub-E2 notes on guitar); optional release-ghost filter; fixed the `process` command crash; window brought in line with the stem maker (tabs, output folder + Open Output Folder, saved settings, overwrite warning, no-console launcher); CLI Reference generated from the real commands.
