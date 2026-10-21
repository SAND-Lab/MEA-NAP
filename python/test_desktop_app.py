"""The desktop app's code paths, tested from source by pretending to be frozen.

    .venv/bin/python -m pytest python/test_desktop_app.py

The real check of a build is ``<app> --smoke-test`` (``packaging/build_app.py
--smoke``). These cover the decisions the app makes about being frozen, which a
source checkout never takes — and that each one is a no-op when not frozen.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap import frozen, updates  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def as_frozen(monkeypatch, tmp_path):
    """Look like a PyInstaller app whose bundle is *tmp_path*."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    return tmp_path


# ── python_command ───────────────────────────────────────────────────────────

def test_python_command_from_source_is_python_dash_m():
    assert frozen.python_command("meanap.x", "--a") == [sys.executable, "-m", "meanap.x", "--a"]


def test_python_command_frozen_re_enters_the_app(as_frozen):
    assert frozen.python_command("meanap.x", "--a") == [
        sys.executable, frozen.RUN_MODULE_FLAG, "meanap.x", "--a"]


def test_entry_point_runs_a_module_like_python_dash_m(tmp_path):
    """--run-module gives the module __main__ and its own argv."""
    probe = tmp_path / "probe_mod.py"
    probe.write_text("import sys, json\n"
                     "if __name__ == '__main__':\n"
                     "    print(json.dumps(sys.argv))\n")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT / "src")])}
    out = subprocess.run(
        [sys.executable, str(ROOT / "packaging" / "meanap_app.py"),
         frozen.RUN_MODULE_FLAG, "probe_mod", "--x", "1"],
        capture_output=True, text=True, env=env, check=True).stdout
    argv = json.loads(out)
    # As with python -m: argv[0] is the module's file, then its own arguments.
    assert Path(argv[0]).name == "probe_mod.py" and argv[1:] == ["--x", "1"]


# ── prepare_runtime ──────────────────────────────────────────────────────────

def test_prepare_runtime_does_nothing_from_source(monkeypatch):
    out, err = sys.stdout, sys.stderr
    mpl = os.environ.get("MPLCONFIGDIR")
    frozen.prepare_runtime()
    assert (sys.stdout, sys.stderr) == (out, err)
    assert os.environ.get("MPLCONFIGDIR") == mpl


def test_prepare_runtime_frozen_logs_to_file_and_children_append(tmp_path):
    """No console: output goes to the log; a spawned worker adds to, not replaces, it."""
    script = (
        "import sys, os\n"
        "sys.frozen = True\n"
        "sys.stdout = None; sys.stderr = None\n"
        "from meanap import frozen\n"
        "frozen.prepare_runtime()\n"
        "print('hello from', os.environ.get('ROLE'))\n"
        "sys.stderr.write('stderr too\\n')\n"
    )
    env = {**os.environ, "HOME": str(tmp_path), "XDG_CACHE_HOME": str(tmp_path / "cache"),
           "LOCALAPPDATA": str(tmp_path / "local"), "PYTHONPATH": str(ROOT / "src")}
    env.pop("MEANAP_APP_LOG_STARTED", None)
    subprocess.run([sys.executable, "-c", script], env={**env, "ROLE": "parent"}, check=True)
    subprocess.run([sys.executable, "-c", script], check=True,
                   env={**env, "ROLE": "child", "MEANAP_APP_LOG_STARTED": "1"})
    log = _log_path(tmp_path)
    text = log.read_text()
    assert "hello from parent" in text and "hello from child" in text
    assert "stderr too" in text
    # A fresh launch (no inherited marker) keeps the last run as .previous.log.
    subprocess.run([sys.executable, "-c", script], env={**env, "ROLE": "again"}, check=True)
    assert "hello from again" in log.read_text()
    assert "hello from parent" in log.with_suffix(".previous.log").read_text()


def test_prepare_runtime_frozen_keeps_the_matplotlib_cache(tmp_path):
    """PyInstaller's hook gives each launch a new MPLCONFIGDIR; the app overrides it."""
    script = (
        "import sys, os\n"
        "sys.frozen = True\n"
        "os.environ['MPLCONFIGDIR'] = 'per-launch-temp'\n"
        "from meanap import frozen\n"
        "frozen.prepare_runtime()\n"
        "print(os.environ['MPLCONFIGDIR'])\n"
    )
    env = {**os.environ, "HOME": str(tmp_path), "XDG_CACHE_HOME": str(tmp_path / "cache"),
           "LOCALAPPDATA": str(tmp_path / "local"), "PYTHONPATH": str(ROOT / "src")}
    runs = [subprocess.run([sys.executable, "-c", script], env=env, check=True,
                           capture_output=True, text=True).stdout.strip() for _ in range(2)]
    assert runs[0] == runs[1] != 'per-launch-temp'
    assert Path(runs[0]).is_dir() and Path(runs[0]).is_relative_to(tmp_path)


def _log_path(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Logs" / "MEA-NAP" / "meanap.log"
    if sys.platform == "win32":
        return home / "local" / "MEA-NAP" / "logs" / "meanap.log"
    return home / "cache" / "meanap" / "logs" / "meanap.log"


# ── bundled files ────────────────────────────────────────────────────────────

def test_matlab_images_found_in_repo_and_in_bundle(as_frozen, monkeypatch):
    from meanap.pipeline import plotting_step4

    assert plotting_step4._matlab_images_dir() == as_frozen / "matlab" / "Images"
    monkeypatch.setattr(sys, "frozen", False)
    monkeypatch.delattr(sys, "_MEIPASS")
    repo = plotting_step4._matlab_images_dir()
    assert repo == ROOT / "matlab" / "Images" and (repo / "ND.png").is_file()


def test_build_info_falls_back_to_baked_file(tmp_path, monkeypatch):
    """No .git around the package: read _build_info.json beside it instead."""
    from meanap import version

    pkg = tmp_path / "a" / "b" / "meanap"
    pkg.mkdir(parents=True)
    (pkg / "_build_info.json").write_text(json.dumps(
        {"describe": "v9.9.9-dev.1", "commit": "abc", "dirty": False}))
    monkeypatch.setattr(version, "__file__", str(pkg / "version.py"))
    version.build_info.cache_clear()
    try:
        assert version.build_info()["describe"] == "v9.9.9-dev.1"
        (pkg / "_build_info.json").write_text("{}")
        version.build_info.cache_clear()
        assert version.build_info() == {}
    finally:
        version.build_info.cache_clear()


# ── update check ─────────────────────────────────────────────────────────────

def _latest(tag, url="https://example/rel"):
    return lambda _url: {"tag_name": tag, "html_url": url}


def test_check_app_newer_release():
    s = updates.check_app("v1.12.0", fetch_json=_latest("v1.13.0"))
    assert s.update_available and s.newer_version == "v1.13.0" and s.url == "https://example/rel"


def test_check_app_same_or_older_is_current():
    assert not updates.check_app("v1.12.0", fetch_json=_latest("v1.12.0")).update_available
    assert not updates.check_app("v1.12.0", fetch_json=_latest("v1.11.0")).update_available


def test_check_app_ignores_dev_and_junk_tags():
    for tag in ("v1.13.0-dev.4", "nightly", None):
        s = updates.check_app("v1.12.0", fetch_json=_latest(tag))
        assert not s.update_available and s.error


def test_check_app_offline_is_an_error_not_an_exception():
    def offline(_url):
        raise OSError("no network")
    s = updates.check_app("v1.12.0", fetch_json=offline)
    assert not s.update_available and "no network" in s.error


def test_app_version_dialog_offers_the_download(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from meanap.gui.versions_dialog import AppVersionDialog, status_summary

    app = QApplication.instance() or QApplication([])  # noqa: F841
    dlg = AppVersionDialog()
    dlg.set_status(updates.check_app("v1.12.0", fetch_json=_latest("v1.13.0")))
    assert dlg._download_button.text() == "Download v1.13.0"
    assert "v1.13.0" in dlg._status_label.text()
    dlg.set_status(updates.check_app("v1.12.0", fetch_json=_latest("v1.12.0")))
    assert dlg._download_button.text() == "Open download page"
    assert status_summary(dlg._status) == "This is the latest official release."


def test_gui_entry_point_leaves_the_pipeline_for_after_the_splash():
    # Everything gui.app imports loads before the splash screen can show, so a
    # pipeline import creeping in there means seconds of blank screen again.
    code = ("import sys, meanap.gui.app; "
            "heavy = [m for m in ('meanap.pipeline.runner', 'meanap.gui.main_window', "
            "'scipy.signal', 'numba', 'pandas') if m in sys.modules]; "
            "print(heavy); sys.exit(1 if heavy else 0)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_time_startup_reports_every_stage():
    # In its own process, as the app runs it: a QApplication made here would be
    # shared with (and alter) every later GUI test in the session.
    from meanap.app_smoke import STARTUP_IMPORTS

    result = subprocess.run(
        [sys.executable, "-c", "import sys; from meanap.app_smoke import time_startup; "
                               "sys.exit(time_startup())"],
        capture_output=True, text=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
    assert result.returncode == 0, result.stdout + result.stderr
    for name in STARTUP_IMPORTS:
        assert f"import {name}" in result.stdout
    assert "build and show the main window" in result.stdout and "total" in result.stdout
