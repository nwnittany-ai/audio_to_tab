"""audio2tab CLI -- run via: python -m audio2tab <subcommand>"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from core.pitch_extraction import extract as _extract
from core.note_processing import process as _process, INSTRUMENT_RANGES, GRID_SUBDIVISIONS
from core.fretboard_mapping import map_notes as _map
from core.tab_renderer import render as _render
from core.pipeline import run as _run
from config.tunings import ALL_TUNINGS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


@click.group()
@click.version_option("0.1.0", prog_name="audio2tab")
def cli() -> None:
    """audio2tab -- convert audio to guitar/bass tab."""


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "-o", type=click.Path(path_type=Path), default=None,
              help="Output JSON path (default: <input_stem>_notes.json beside input)")
@click.option("--onset-threshold", default=0.5, show_default=True,
              help="Basic Pitch onset confidence threshold (0-1)")
@click.option("--frame-threshold", default=0.3, show_default=True,
              help="Basic Pitch frame confidence threshold (0-1)")
@click.option("--min-note-length", default=0.058, show_default=True,
              help="Minimum note length in seconds")
@click.option("--min-freq", default=40.0, show_default=True,
              help="Minimum frequency in Hz (40 = below bass low E)")
@click.option("--max-freq", default=2000.0, show_default=True,
              help="Maximum frequency in Hz")
def extract(
    input_file: Path,
    out: Path | None,
    onset_threshold: float,
    frame_threshold: float,
    min_note_length: float,
    min_freq: float,
    max_freq: float,
) -> None:
    """Extract note events from INPUT_FILE and write to a JSON file.

    \b
    Example:
        python -m audio2tab extract guitar_stem.wav --out notes.json
    """
    if out is None:
        out = input_file.parent / f"{input_file.stem}_notes.json"

    try:
        result = _extract(
            audio_path=input_file,
            output_path=out,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_length,
            minimum_frequency=min_freq,
            maximum_frequency=max_freq,
        )
        click.echo(f"Extracted {result['metadata']['note_count']} notes -> {out}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("notes_file", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "-o", type=click.Path(path_type=Path), default=None,
              help="Output JSON path (default: <stem>_processed.json)")
@click.option("--audio", type=click.Path(exists=True, path_type=Path), default=None,
              help="Original audio file for tempo detection")
@click.option("--instrument", default="auto", show_default=True,
              type=click.Choice(list(INSTRUMENT_RANGES.keys())),
              help="Instrument pitch range filter")
@click.option("--min-amplitude", default=0.15, show_default=True,
              help="Drop notes below this amplitude (0-1)")
@click.option("--min-duration", default=0.05, show_default=True,
              help="Drop notes shorter than this (seconds)")
@click.option("--merge-gap", default=0.08, show_default=True,
              help="Merge same-pitch notes with gap smaller than this (seconds)")
@click.option("--quantize", default="16th", show_default=True,
              type=click.Choice(list(GRID_SUBDIVISIONS.keys())),
              help="Quantization grid subdivision")
@click.option("--tempo", default=None, type=float,
              help="Override tempo in BPM (skips auto-detection)")
@click.option("--dedup-octaves", is_flag=True, default=False,
              help="Drop higher note when two octave-apart notes overlap (single-instrument stems only)")
@click.option("--no-suppress-harmonics", is_flag=True, default=False,
              help="Disable harmonic suppression (off by default for mixed recordings)")
@click.option("--harmonic-ratio", default=0.5, show_default=True,
              help="Harmonic suppression threshold: candidate amp must be < ratio x fundamental amp")
def process(
    notes_file: Path,
    out: Path | None,
    audio: Path | None,
    instrument: str,
    min_amplitude: float,
    min_duration: float,
    merge_gap: float,
    quantize: str,
    tempo: float | None,
    dedup_octaves: bool,
    no_suppress_harmonics: bool,
    harmonic_ratio: float,
) -> None:
    """Clean and quantize raw note events from NOTES_FILE.

    \b
    Example:
        python -m audio2tab process notes.json --audio song.mp3 --instrument bass --out processed.json
    """
    if out is None:
        out = notes_file.parent / f"{notes_file.stem.replace('_notes', '')}_processed.json"

    try:
        result = _process(
            notes_path=notes_file,
            output_path=out,
            audio_path=audio,
            instrument=instrument,
            min_amplitude=min_amplitude,
            min_duration_s=min_duration,
            merge_gap_s=merge_gap,
            quantize=quantize,
            tempo_override=tempo,
            dedup_octaves=dedup_octaves,
            suppress_harmonics=not no_suppress_harmonics,
            harmonic_ratio=harmonic_ratio,
        )
        m = result["metadata"]
        click.echo(
            f"Processed {m['note_count']} notes at {m['tempo_bpm']} BPM "
            f"({m['quantize']} grid) -> {out}"
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command("map")
@click.argument("processed_file", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "-o", type=click.Path(path_type=Path), default=None,
              help="Output JSON path (default: <stem>_mapped.json)")
@click.option("--tuning", default="standard", show_default=True,
              type=click.Choice(sorted(ALL_TUNINGS.keys())),
              help="Tuning name from config/tunings.py")
@click.option("--window", default=5, show_default=True,
              help="Fret-hand position window size (number of frets)")
@click.option("--prefer-high-strings", is_flag=True, default=False,
              help="Prefer higher/thinner strings (lead guitar feel; default: low/thick strings)")
@click.option("--max-fret", default=24, show_default=True,
              help="Hard upper limit on fret numbers; notes above this are marked unmapped")
def map_cmd(
    processed_file: Path,
    out: Path | None,
    tuning: str,
    window: int,
    prefer_high_strings: bool,
    max_fret: int,
) -> None:
    """Map processed note pitches to (string, fret) pairs.

    \b
    Example:
        python -m audio2tab map processed.json --tuning bass --max-fret 12 --out mapped.json
    """
    if out is None:
        out = processed_file.parent / f"{processed_file.stem.replace('_processed', '')}_mapped.json"

    try:
        result = _map(
            processed_path=processed_file,
            output_path=out,
            tuning=tuning,
            position_window=window,
            prefer_low_strings=not prefer_high_strings,
            max_fret=max_fret,
        )
        m = result["metadata"]
        click.echo(
            f"Mapped {m['note_count'] - m['unmapped_count']} / {m['note_count']} notes "
            f"(tuning: {m['tuning']}, {m['unmapped_count']} unmapped) -> {out}"
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("mapped_file", type=click.Path(exists=True, path_type=Path))
@click.option("--out", "-o", type=click.Path(path_type=Path), default=None,
              help="Output .tab file (default: <stem>.tab)")
@click.option("--measures-per-line", default=4, show_default=True,
              help="Measures to display per line before wrapping")
@click.option("--time-sig", default=4, show_default=True,
              help="Beats per measure (numerator of time signature)")
def render(
    mapped_file: Path,
    out: Path | None,
    measures_per_line: int,
    time_sig: int,
) -> None:
    """Render mapped notes to ASCII tab.

    \b
    Example:
        python -m audio2tab render mapped.json --out song.tab
    """
    if out is None:
        out = mapped_file.parent / f"{mapped_file.stem.replace('_mapped', '')}.tab"

    try:
        result = _render(
            mapped_path=mapped_file,
            output_path=out,
            measures_per_line=measures_per_line,
            time_sig_num=time_sig,
        )
        m = result["metadata"]
        click.echo(
            f"Rendered {m['measures']} measures at {m['tempo_bpm']:.1f} BPM "
            f"({m['unmapped_skipped']} notes skipped) -> {out}"
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--out-dir", "-d", type=click.Path(path_type=Path), default=None,
              help="Output directory (default: ./output)")
@click.option("--tuning", default="standard", show_default=True,
              type=click.Choice(sorted(ALL_TUNINGS.keys())),
              help="Tuning for fretboard mapping")
@click.option("--instrument", default="auto", show_default=True,
              type=click.Choice(["guitar", "bass", "auto"]),
              help="Instrument pitch range filter")
@click.option("--quantize", default="8th", show_default=True,
              type=click.Choice(["4th", "8th", "16th", "32nd"]),
              help="Timing quantization grid")
@click.option("--measures-per-line", default=4, show_default=True,
              help="Measures per line in tab output")
@click.option("--tempo", default=None, type=float,
              help="Override tempo in BPM")
@click.option("--min-amplitude", default=0.25, show_default=True,
              help="Drop notes below this amplitude (0-1); 0.25 is recommended for isolated guitar stems")
@click.option("--max-fret", default=24, show_default=True,
              help="Hard upper limit on fret numbers (set to 12 to filter high-fret harmonic artifacts)")
@click.option("--dedup-octaves", is_flag=True, default=False,
              help="Remove octave duplicates (single-instrument stems only)")
@click.option("--no-suppress-harmonics", is_flag=True, default=False,
              help="Disable harmonic overtone suppression")
@click.option("--harmonic-ratio", default=0.5, show_default=True,
              help="Harmonic suppression threshold (candidate amp < ratio x fundamental amp)")
@click.option("--no-intermediates", is_flag=True, default=False,
              help="Delete intermediate JSON files after rendering")
def run(
    input_file: Path,
    out_dir: Path | None,
    tuning: str,
    instrument: str,
    quantize: str,
    measures_per_line: int,
    tempo: float | None,
    min_amplitude: float,
    max_fret: int,
    dedup_octaves: bool,
    no_suppress_harmonics: bool,
    harmonic_ratio: float,
    no_intermediates: bool,
) -> None:
    """Run the full pipeline: extract -> process -> map -> render.

    \b
    Example:
        python -m audio2tab run guitar_stem.wav --tuning standard --out-dir output/
        python -m audio2tab run guitar_stem.wav --max-fret 12 --min-amplitude 0.3
        python -m audio2tab run bass_stem.wav --tuning bass --instrument bass
    """
    if out_dir is None:
        out_dir = Path("output")

    try:
        summary = _run(
            audio_path=input_file,
            output_dir=out_dir,
            tuning=tuning,
            instrument=instrument,
            quantize=quantize,
            measures_per_line=measures_per_line,
            tempo_override=tempo,
            min_amplitude=min_amplitude,
            max_fret=max_fret,
            dedup_octaves=dedup_octaves,
            suppress_harmonics=not no_suppress_harmonics,
            harmonic_ratio=harmonic_ratio,
            keep_intermediates=not no_intermediates,
        )
        click.echo(
            f"\nDone: {summary['measures']} measures | "
            f"{summary['tempo_bpm']:.1f} BPM | "
            f"{summary['notes_raw']} raw -> {summary['notes_kept']} kept -> "
            f"{summary['notes_mapped']} mapped\n"
            f"Tab: {summary['tab']}"
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
