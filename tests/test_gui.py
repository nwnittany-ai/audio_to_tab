"""The window, driven headlessly (Qt "offscreen") with a stand-in for the slow pipeline."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from config import settings as app_settings  # noqa: E402
from config.defaults import DEFAULTS  # noqa: E402
from core.pipeline import STAGES  # noqa: E402

TAB_TEXT = "e |--0--|\nB |-----|\n"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    """A window with a fake pipeline, message boxes recorded instead of shown, and a temporary settings file."""
    from gui import app as gapp

    boxes = {"question": [], "critical": [], "information": [], "warning": []}
    answers = {"question": gapp.QMessageBox.StandardButton.Yes}
    for kind in ("critical", "information", "warning"):
        monkeypatch.setattr(gapp.QMessageBox, kind, staticmethod(lambda *a, _k=kind, **kw: boxes[_k].append(a[2] if len(a) > 2 else "")))
    monkeypatch.setattr(gapp.QMessageBox, "question",
                        staticmethod(lambda *a, **kw: (boxes["question"].append(a[2]), answers["question"])[1]))
    calls: list[dict] = []
    behaviour = {"error": None}

    def fake_pipeline(progress=None, **kwargs):
        calls.append(kwargs)
        if behaviour["error"]:
            progress(STAGES[0], "running", "")
            raise RuntimeError(behaviour["error"])
        for stage in STAGES[:4]:
            progress(stage, "running", "")
            progress(stage, "done", "ok")
        if kwargs["midi"]:
            progress(STAGES[4], "running", "")
            progress(STAGES[4], "done", "ok")
        else:
            progress(STAGES[4], "skipped", "not requested")
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        tab = out / f"{Path(kwargs['audio_path']).stem}.tab"
        tab.write_text(TAB_TEXT, encoding="utf-8")
        return {"tab": str(tab), "output_dir": str(out), "midi": str(out / "x.mid") if kwargs["midi"] else None,
                "midi_notes": 5 if kwargs["midi"] else 0, "measures": 3, "tempo_bpm": 100.0, "instrument": "guitar"}

    cfg = tmp_path / "cfg.json"
    audio = tmp_path / "songs" / "riff.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"RIFF")
    window = gapp.MainWindow(settings_path=cfg, pipeline=fake_pipeline)

    class Env:
        pass

    e = Env()
    e.gapp, e.window, e.boxes, e.answers, e.calls, e.behaviour, e.cfg, e.audio = (
        gapp, window, boxes, answers, calls, behaviour, cfg, audio)

    def pick():
        window._file_picker.set_path(audio)
        window._on_file_selected(audio)

    def wait():
        t0 = time.time()
        while window._worker is not None and window._worker.isRunning() and time.time() - t0 < 15:
            QApplication.processEvents()
            time.sleep(0.01)
        window._worker.wait()
        for _ in range(30):
            QApplication.processEvents()

    e.pick, e.wait = pick, wait
    yield e
    window.close()


# ---------------------------------------------------------------------------

def test_widgets_start_with_the_shared_defaults(env):
    v = env.window._values()
    for key in app_settings.SAVED_KEYS:
        assert v[key] == DEFAULTS[key], key
    assert env.window._max_fret_spin.value() == 12 and env.window._midi_chk.isChecked()
    assert list(env.window._stage_panels) == list(STAGES)


def test_settings_save_reload_and_reset(env):
    w = env.window
    w._tuning_combo.setCurrentText("drop_d")
    w._max_fret_spin.setValue(17)
    w._ghost_chk.setChecked(True)
    w._midi_timing_combo.setCurrentIndex(w._midi_timing_combo.findData("grid"))
    w._def_out_edit.setText(r"C:\Tabs")
    w._save_settings()
    assert env.boxes["information"] == ["Settings saved."] and env.cfg.exists()

    again = env.gapp.MainWindow(settings_path=env.cfg)
    v = again._values()
    assert (v["tuning"], v["max_fret"], v["ghost_filter"], v["midi_timing"], v["default_output_dir"]) == (
        "drop_d", 17, True, "grid", r"C:\Tabs")
    again._reset_settings()
    v = again._values()
    assert v["tuning"] == DEFAULTS["tuning"] and v["max_fret"] == 12 and v["default_output_dir"] == ""
    assert app_settings.load(env.cfg)["max_fret"] == 17  # reset changes the window only until you save


def test_a_damaged_settings_file_cannot_stop_startup(env, tmp_path):
    bad = tmp_path / "bad.json"
    for content in ("{not json", '["a list"]', '{"max_fret": "twelve", "tuning": 5}'):
        bad.write_text(content, encoding="utf-8")
        v = env.gapp.MainWindow(settings_path=bad)._values()
        assert v["max_fret"] == 12 and v["tuning"] == "standard"


def test_output_folder_rules(env):
    w = env.window
    env.pick()
    assert Path(w._out_edit.text()) == env.audio.parent / "tab_output"           # beside the audio by default
    w._def_out_edit.setText(r"C:\Saved Tabs")
    w._update_output_label()
    assert Path(w._out_edit.text()) == Path(r"C:\Saved Tabs")                      # the saved default folder
    w._output_override = Path(r"D:\Elsewhere")
    w._update_output_label()
    assert Path(w._out_edit.text()) == Path(r"D:\Elsewhere")                       # a folder chosen for this file
    env.pick()                                                                       # picking a new file resets the choice
    assert Path(w._out_edit.text()) == Path(r"C:\Saved Tabs")


def test_run_sends_the_window_settings_to_the_pipeline_and_updates_everything(env):
    w = env.window
    env.pick()
    w._instrument_combo.setCurrentText("guitar")
    w._max_fret_spin.setValue(15)
    w._ghost_chk.setChecked(True)
    w._midi_chk.setChecked(False)
    w._min_amp_spin.setValue(0.4)
    w._run_btn.click()
    env.wait()
    (kw,) = env.calls
    assert kw["instrument"] == "guitar" and kw["max_fret"] == 15 and kw["ghost_filter"] is True
    assert kw["midi"] is False and kw["min_amplitude"] == 0.4 and kw["suppress_harmonics"] is True
    assert Path(kw["output_dir"]) == env.audio.parent / "tab_output"
    states = {name: p.state for name, p in w._stage_panels.items()}
    assert states == {**{s: "done" for s in STAGES[:4]}, STAGES[4]: "skipped"}
    assert w._tab_preview.toPlainText() == TAB_TEXT
    assert w._run_btn.isEnabled() and w._save_btn.isEnabled() and w._open_btn.isEnabled()
    assert "Done" in w.statusBar().currentMessage() and "guitar" in w.statusBar().currentMessage()


def test_existing_files_trigger_the_overwrite_question(env):
    env.pick()
    out = env.audio.parent / "tab_output"
    out.mkdir()
    (out / "riff.tab").write_text("old", encoding="utf-8")
    env.answers["question"] = env.gapp.QMessageBox.StandardButton.No
    env.window._run_btn.click()
    assert env.calls == [] and "riff.tab" in env.boxes["question"][0]  # declined: nothing ran, the file is listed
    env.answers["question"] = env.gapp.QMessageBox.StandardButton.Yes
    env.window._run_btn.click()
    env.wait()
    assert len(env.calls) == 1


def test_a_pipeline_error_is_reported_and_the_window_recovers(env):
    env.pick()
    env.behaviour["error"] = "Basic Pitch exploded"
    env.window._run_btn.click()
    env.wait()
    assert env.boxes["critical"] == ["Basic Pitch exploded"]
    assert env.window._stage_panels[STAGES[0]].state == "error"
    assert env.window._run_btn.isEnabled() and not env.window._open_btn.isEnabled()
    env.behaviour["error"] = None
    env.window._run_btn.click()
    env.wait()
    assert env.window._open_btn.isEnabled()


def test_open_output_folder_shows_the_tab_file(env, monkeypatch):
    shown = []
    monkeypatch.setattr(env.window, "_reveal", shown.append)
    env.pick()
    env.window._run_btn.click()
    env.wait()
    env.window._open_output_folder()
    assert shown == [env.audio.parent / "tab_output" / "riff.tab"]


def test_cli_reference_tab_is_generated_from_the_real_commands(env):
    from config.tunings import ALL_TUNINGS
    from gui.cli_reference import build_cli_reference
    text = build_cli_reference()
    for needle in ("audio2tab midi", "--midi", "--ghost-filter", "--max-fret", "--midi-timing", "[default: 12]"):
        assert needle in text, needle
    assert all(t in text for t in ALL_TUNINGS)
    assert env.window._tabs.count() == 3 and env.window._tabs.tabText(2).strip() == "CLI Reference"


def test_the_launcher_starts_without_a_console_window():
    bat = (Path(__file__).parent.parent / "gui" / "launcher.bat").read_text(encoding="utf-8")
    assert "pythonw.exe" in bat and "gui\\app.py" in bat


def test_missing_console_streams_get_utf8_stand_ins(monkeypatch):
    from gui import app as gapp
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    gapp.ensure_streams()
    sys.stdout.write("progress \u258f\u2588 bar")  # the characters that crashed the stem maker under pythonw
    sys.stderr.write("\u258e")
