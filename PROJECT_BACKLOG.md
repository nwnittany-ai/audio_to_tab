# audio_to_tab — Project Backlog

## P2 — Low Priority Enhancements

| Item | Description |
|------|-------------|
| **GPU acceleration for Basic Pitch** | TensorFlow dropped native Windows GPU support after TF 2.10. Options to investigate: (1) TF-DirectML plugin (`tensorflow-directml`) for Windows GPU via DirectX; (2) WSL2 with TF 2.x + CUDA 12.x; (3) replace Basic Pitch TF backend with an ONNX runtime path (`onnxruntime-gpu`) if Basic Pitch exposes one. Current implementation runs CPU-only; inference on a 3-4 min stem is ~30-60s which is acceptable for now. |
| **Guitar Pro export** | Add a `.gp5`/`.gpx` renderer alongside ASCII tab using `PyGuitarPro`. |
| **Chord-shape recognition** | Upgrade fretboard mapping from position-window heuristic to chord-shape-aware algorithm. |
| **Diff against known tab** | "Self-transcription accuracy" mode — compare generated tab to a reference tab file. |
| **Waveform display in GUI** | Visual waveform preview in the GUI with playback-synced tab scrolling. |
| **Manual fret override in GUI** | Let user adjust fret-position assignments in the Map stage via the GUI. |

## P3 — Future / Speculative

| Item | Description |
|------|-------------|
| **Plug-in alternate pitch models** | Architecture hook to swap Basic Pitch for another model (e.g., CREPE, pYIN) if quality is insufficient. |
| **Desktop shortcut** | `.lnk` or `.bat` launcher for double-click GUI launch without opening PowerShell. |
