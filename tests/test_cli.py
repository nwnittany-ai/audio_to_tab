"""Command line: every subcommand works end to end on the fixture, defaults match the shared defaults."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pretty_midi
from click.testing import CliRunner

from cli.main import cli
from config.defaults import DEFAULTS, VERSION


def _invoke(*args):
    result = CliRunner().invoke(cli, [str(a) for a in args])
    assert result.exit_code == 0, f"{args} failed:\n{result.output}\n{result.exception!r}"
    return result.output


def test_process_map_render_midi_chain_runs_on_the_fixture(raw_notes_path, tmp_path):
    """The stand-alone `process` command used to crash (an undefined variable); this walks the whole chain."""
    processed, mapped, tab, mid = (tmp_path / n for n in ("p_processed.json", "p_mapped.json", "p.tab", "p.mid"))
    out = _invoke("process", raw_notes_path, "--tempo", 100, "--min-amplitude", 0.5, "--harmonic-ratio", 0.7, "--out", processed)
    assert "guitar" in out
    _invoke("map", processed, "--out", mapped)
    _invoke("render", mapped, "--out", tab)
    out = _invoke("midi", processed, "--out", mid)
    assert "Wrote" in out and "played timing" in out
    assert tab.read_text(encoding="utf-8").strip() and len(pretty_midi.PrettyMIDI(str(mid)).instruments[0].notes) > 100


def test_midi_timing_option_and_ghost_filter_flag(raw_notes_path, tmp_path):
    processed = tmp_path / "g_processed.json"
    _invoke("process", raw_notes_path, "--tempo", 100, "--min-amplitude", 0.5, "--harmonic-ratio", 0.7, "--ghost-filter",
            "--out", processed)
    assert json.loads(processed.read_text())["metadata"]["ghost_removed"] >= 1
    assert "grid timing" in _invoke("midi", processed, "--timing", "grid", "--out", tmp_path / "g.mid")


def test_cli_defaults_equal_the_shared_defaults():
    commands = cli.commands
    expected = {
        "process": {"min_amplitude": "min_amplitude", "quantize": "quantize", "harmonic_ratio": "harmonic_ratio",
                    "instrument": "instrument"},
        "run": {"min_amplitude": "min_amplitude", "quantize": "quantize", "max_fret": "max_fret",
                "harmonic_ratio": "harmonic_ratio", "instrument": "instrument", "tuning": "tuning",
                "measures_per_line": "measures_per_line", "midi_timing": "midi_timing", "midi_flag": "midi"},
        "map": {"max_fret": "max_fret", "window": "position_window", "tuning": "tuning"},
    }
    for command, params in expected.items():
        by_name = {p.name: p for p in commands[command].params}
        for cli_name, default_key in params.items():
            assert by_name[cli_name].default == DEFAULTS[default_key], (command, cli_name)


def test_version_comes_from_one_place():
    assert VERSION in _invoke("--version")
    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf'^version = "{re.escape(VERSION)}"', pyproject, re.M), "pyproject version != config/defaults.VERSION"


def test_help_text_no_longer_claims_harmonic_suppression_is_off_by_default():
    text = _invoke("process", "--help")
    assert "off by default for mixed recordings" not in text
    assert "ON by default" in text
