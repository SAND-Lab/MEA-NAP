"""What changes when MEA-NAP runs as the packaged desktop app.

The app (see ``packaging/``) is a PyInstaller build: Python and every
dependency inside one folder, started by double-clicking. Three things that a
source checkout takes for granted are missing there, and this module is where
the rest of the code asks about them, so that each answer is a no-op from a
clone:

* **No ``python``.** ``sys.executable`` is the app itself, so ``python -m X``
  becomes ``<app> --run-module X`` — :func:`python_command`.
* **No source tree.** Files that a clone finds relative to the repo (the
  MATLAB folder's schematics) are bundled and found under
  :func:`bundle_dir` instead.
* **No console** on Windows: ``sys.stdout`` and ``sys.stderr`` are ``None``,
  and the first ``print`` to stderr would raise. :func:`prepare_runtime` sends
  both to a log file, which is also the file to attach to a bug report.
* **A throwaway matplotlib folder.** PyInstaller's runtime hook points
  ``MPLCONFIGDIR`` at a new temporary folder on every launch (it is written for
  one-file builds, whose fonts move each run), so matplotlib re-scans every
  font on the system each time the app — or any of its worker processes —
  starts: seconds on a PC with many fonts. The app is a one-folder build whose
  files stay put, so :func:`prepare_runtime` gives matplotlib a lasting folder.

numba's ``cache=True`` needs nothing here: with no source file to cache beside,
numba itself caches in the user's cache folder (``~/Library/Caches/numba``,
``%LOCALAPPDATA%\\numba``), keyed to the app's executable so a new version
never loads an old build's machine code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MEA-NAP"

#: The flag the app's entry point reads to run a module the way ``python -m``
#: would. Kept here, beside :func:`python_command`, so the two cannot drift.
RUN_MODULE_FLAG = "--run-module"


def is_frozen() -> bool:
    """True inside the packaged app, False when run from Python."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path | None:
    """The folder the app's bundled files were unpacked into, or ``None``."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def python_command(module: str, *args: str) -> list[str]:
    """``argv`` that runs *module* as ``__main__`` in a fresh process.

    ``[python, "-m", module, ...]`` from a clone; the app re-entering itself
    with :data:`RUN_MODULE_FLAG` when frozen.
    """
    if is_frozen():
        return [sys.executable, RUN_MODULE_FLAG, module, *args]
    return [sys.executable, "-m", module, *args]


def log_file() -> Path:
    """Where the app's output goes, following each OS's habit for logs."""
    home = Path.home()
    if sys.platform == "darwin":
        folder = home / "Library" / "Logs" / APP_NAME
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        folder = Path(base) / APP_NAME / "logs"
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(home / ".cache")
        folder = Path(base) / "meanap" / "logs"
    return folder / "meanap.log"


def cache_dir() -> Path:
    """The app's own cache folder, following each OS's habit for caches."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / APP_NAME
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(base) / APP_NAME / "cache"
    base = os.environ.get("XDG_CACHE_HOME") or str(home / ".cache")
    return Path(base) / "meanap" / "app-cache"


def prepare_runtime() -> None:
    """Set up the frozen app's process. Does nothing outside the app.

    Must run before anything imports matplotlib.
    """
    if not is_frozen():
        return
    if sys.stdout is None or sys.stderr is None:
        _log_to_file()
    _keep_matplotlib_cache()


def _keep_matplotlib_cache() -> None:
    """Replace the hook's per-launch MPLCONFIGDIR with one that lasts.

    If the app is moved or upgraded, matplotlib notices the fonts it cached are
    gone and rebuilds the cache once by itself.
    """
    folder = cache_dir() / "matplotlib"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return  # keep the hook's temporary folder: slow, but works
    os.environ["MPLCONFIGDIR"] = str(folder)


#: Set once the app has started its log, so the worker processes it spawns
#: (which inherit the environment) append to that log instead of rotating it.
_LOG_STARTED_ENV = "MEANAP_APP_LOG_STARTED"


def _log_to_file() -> None:
    """Send stdout/stderr to the log file, keeping the previous run's copy."""
    path = log_file()
    child = os.environ.get(_LOG_STARTED_ENV) == "1"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not child:
            path.replace(path.with_suffix(".previous.log"))
        stream = open(path, "a" if child else "w", buffering=1,  # noqa: SIM115
                      encoding="utf-8", errors="replace")
        os.environ[_LOG_STARTED_ENV] = "1"
    except OSError:
        stream = open(os.devnull, "w")  # noqa: SIM115 - nowhere to write: drop it
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
