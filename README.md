# audio2tab

Turns a guitar or bass recording (`.wav` / `.mp3`) into **ASCII tab** and a **MIDI file**, using Spotify's
Basic Pitch note detector. Runs locally on the CPU; a typical recording takes well under a minute.

## What you get

For `song.wav` it writes, into a `tab_output` folder beside the audio (or any folder you choose):

| File | What it is |
|---|---|
| `song.tab` | Readable ASCII tab |
| `song.mid` | The cleaned notes as MIDI (tempo, guitar or bass instrument, note loudness) |
| `song_notes.json`, `song_processed.json`, `song_mapped.json` | Intermediate results, so any stage can be re-run without redoing the slow note detection |

## Use it

**Window:** double-click the `audio2tab` desktop shortcut (it runs `gui\launcher.bat`). Pick a file, press **Run Pipeline**.
The **Advanced** tab holds the note-cleaning options and the folders you want remembered (**Save Settings**).

**Command line:** `.venv\Scripts\audio2tab.exe run song.wav` (see the **CLI Reference** tab, or `audio2tab --help`).

## Good to know

- **Pitch is accurate; fret positions are a best guess.** The same pitch can be played on several strings, and audio can't
  say which was used, so the tab shows a plausible choice. MIDI doesn't have this limit because it only needs the pitch.
- **Instrument "auto"** decides guitar vs bass from the notes themselves and drops impossible low notes for guitar.
- **For the cleanest result, transcribe one instrument at a time** (a single exported track or a stem).
- Drums are not supported (the note detector only finds pitched notes).

## Developing

```
.venv\Scripts\python.exe -m pytest tests -q      # no audio or model needed; uses a recorded fixture
```

All default values live in `config/defaults.py`; the window and the command line both call `core.pipeline.run`.
See `CLAUDE.md` for the architecture and conventions.
