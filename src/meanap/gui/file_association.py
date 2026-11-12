"""Make double-clicking a ``.meanap`` bundle open it in MEA-NAP.

The desktop app's installers do this themselves: the Windows installer writes
the registry keys (``packaging/windows/meanap.iss``) and the macOS app declares
the file type in its ``Info.plist`` (``packaging/meanap.spec``). This module is
for everyone else, which is everyone on Linux (there is no Linux desktop app)
and anyone running MEA-NAP from a clone or ``pip install`` on Windows.

Everything it writes is in the user's own folders, so no administrator rights
are needed, and :func:`unregister` removes all of it again.

* **Linux** follows the freedesktop.org conventions: a MIME type for
  ``*.meanap``, a ``.desktop`` launcher that accepts it, and an icon, all under
  ``$XDG_DATA_HOME`` (``~/.local/share``), then MEA-NAP is made the default
  application for the type with ``xdg-mime``.
* **Windows** writes the same keys the installer does, under
  ``HKEY_CURRENT_USER\\Software\\Classes``.
* **macOS** is not supported from Python: Finder only associates file types
  with an ``.app``, so the desktop app is the way to get this on a Mac.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from meanap.frozen import is_frozen

__all__ = [
    "MIME_TYPE", "PROG_ID", "Status", "launch_command", "register", "status",
    "supported", "unregister",
]

MIME_TYPE = "application/x-meanap-bundle"
#: The Windows ProgID; the installer uses the same one.
PROG_ID = "MEANAP.Bundle"
DESKTOP_FILE = "meanap.desktop"
ICON_NAME = "meanap"
_MIME_ICON = MIME_TYPE.replace("/", "-")
_ASSETS = Path(__file__).resolve().parent / "assets"
ICON_FILE = _ASSETS / "meanap-icon.png"


@dataclass(frozen=True)
class Status:
    registered: bool
    #: What to tell the user, whether or not it is registered.
    message: str


def supported() -> bool:
    """Whether :func:`register` can do anything on this computer."""
    return sys.platform.startswith("linux") or sys.platform == "win32"


def launch_command() -> list[str]:
    """The command that opens MEA-NAP, as this process was started.

    Absolute paths throughout, because the file manager runs it without the
    shell or virtual environment this process has.
    """
    if is_frozen():
        return [sys.executable]
    if sys.platform == "win32":
        # pythonw.exe, so double-clicking a bundle does not also open a console.
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        python = str(pythonw) if pythonw.is_file() else sys.executable
        return [python, "-m", "meanap.gui.app"]
    return [sys.executable, "-m", "meanap.gui.app"]


# ── Linux ────────────────────────────────────────────────────────────────────

def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _linux_paths() -> dict[str, Path]:
    data = _data_home()
    return {
        "mime": data / "mime" / "packages" / "meanap.xml",
        "desktop": data / "applications" / DESKTOP_FILE,
        "app_icon": data / "icons" / "hicolor" / "256x256" / "apps" / f"{ICON_NAME}.png",
        "file_icon": data / "icons" / "hicolor" / "256x256" / "mimetypes" / f"{_MIME_ICON}.png",
    }


_MIME_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="{MIME_TYPE}">
    <comment>MEA-NAP run bundle</comment>
    <sub-class-of type="application/zip"/>
    <icon name="{_MIME_ICON}"/>
    <glob pattern="*.meanap" weight="80"/>
  </mime-type>
</mime-info>
"""


def _desktop_entry() -> str:
    # %f: one local file per launch; a second double-click reaches the running
    # window through its single-instance socket (see gui.single_instance).
    command = " ".join(shlex.quote(part) for part in launch_command())
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=MEA-NAP\n"
        "Comment=MEA network analysis pipeline\n"
        f"Exec={command} %f\n"
        f"Icon={ICON_NAME}\n"
        f"MimeType={MIME_TYPE};\n"
        "Categories=Science;Education;\n"
        "Terminal=false\n"
    )


def _run_quietly(*command: str) -> bool:
    """Run a desktop-database tool if it is installed; whether it succeeded."""
    if shutil.which(command[0]) is None:
        return False
    try:
        return subprocess.run(command, capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _register_linux() -> Status:
    paths = _linux_paths()
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    paths["mime"].write_text(_MIME_XML)
    paths["desktop"].write_text(_desktop_entry())
    shutil.copyfile(ICON_FILE, paths["app_icon"])
    shutil.copyfile(ICON_FILE, paths["file_icon"])

    data = _data_home()
    _run_quietly("update-mime-database", str(data / "mime"))
    _run_quietly("update-desktop-database", str(data / "applications"))
    _run_quietly("gtk-update-icon-cache", "-q", "-t", str(data / "icons" / "hicolor"))
    defaulted = _run_quietly("xdg-mime", "default", DESKTOP_FILE, MIME_TYPE)
    message = ("Double-clicking a .meanap file now opens it in MEA-NAP."
               if defaulted else
               "MEA-NAP is registered for .meanap files. If double-clicking one "
               "still opens something else, right-click it, choose Open With, and "
               "pick MEA-NAP as the default.")
    return Status(True, message)


def _unregister_linux() -> Status:
    for path in _linux_paths().values():
        path.unlink(missing_ok=True)
    data = _data_home()
    _run_quietly("update-mime-database", str(data / "mime"))
    _run_quietly("update-desktop-database", str(data / "applications"))
    return Status(False, "MEA-NAP no longer opens .meanap files when they are double-clicked.")


def _status_linux() -> Status:
    desktop = _linux_paths()["desktop"]
    if not (_linux_paths()["mime"].is_file() and desktop.is_file()):
        return Status(False, "Double-clicking a .meanap file doesn't open MEA-NAP yet.")
    if f"Exec={' '.join(shlex.quote(p) for p in launch_command())} %f" not in desktop.read_text():
        return Status(False, "Double-clicking a .meanap file opens a different copy of "
                             "MEA-NAP. Set it up again to use this one.")
    return Status(True, "Double-clicking a .meanap file opens it in MEA-NAP.")


# ── Windows ──────────────────────────────────────────────────────────────────

def _windows_command() -> str:
    return " ".join(f'"{part}"' for part in launch_command()) + ' "%1"'


def _register_windows() -> Status:
    import winreg

    def put(subkey: str, value: str, name: str = "") -> None:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{subkey}") as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    icon = launch_command()[0]
    put(".meanap", PROG_ID)
    put(r".meanap\OpenWithProgids", "", PROG_ID)
    put(PROG_ID, "MEA-NAP run bundle")
    put(rf"{PROG_ID}\DefaultIcon", f'"{icon}",0')
    put(rf"{PROG_ID}\shell\open\command", _windows_command())
    _notify_windows_shell()
    return Status(True, "Double-clicking a .meanap file now opens it in MEA-NAP.")


def _unregister_windows() -> Status:
    import winreg

    for subkey in (rf"{PROG_ID}\shell\open\command", rf"{PROG_ID}\shell\open",
                   rf"{PROG_ID}\shell", rf"{PROG_ID}\DefaultIcon", PROG_ID,
                   r".meanap\OpenWithProgids", ".meanap"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{subkey}")
        except OSError:
            pass
    _notify_windows_shell()
    return Status(False, "MEA-NAP no longer opens .meanap files when they are double-clicked.")


def _status_windows() -> Status:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"Software\Classes\{PROG_ID}\shell\open\command") as key:
            command, _ = winreg.QueryValueEx(key, "")
    except OSError:
        return Status(False, "Double-clicking a .meanap file doesn't open MEA-NAP yet.")
    if command != _windows_command():
        return Status(False, "Double-clicking a .meanap file opens a different copy of "
                             "MEA-NAP. Set it up again to use this one.")
    return Status(True, "Double-clicking a .meanap file opens it in MEA-NAP.")


def _notify_windows_shell() -> None:
    """Tell Explorer the associations changed, so icons update without a log-out."""
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass


# ── Either ───────────────────────────────────────────────────────────────────

_UNSUPPORTED = Status(False, "On a Mac, double-clicking a .meanap file opens MEA-NAP "
                             "once the MEA-NAP desktop app is installed.")


def register() -> Status:
    """Make this copy of MEA-NAP open ``.meanap`` files when they are double-clicked."""
    if sys.platform.startswith("linux"):
        return _register_linux()
    if sys.platform == "win32":
        return _register_windows()
    return _UNSUPPORTED


def unregister() -> Status:
    """Undo :func:`register`."""
    if sys.platform.startswith("linux"):
        return _unregister_linux()
    if sys.platform == "win32":
        return _unregister_windows()
    return _UNSUPPORTED


def status() -> Status:
    """Whether double-clicking a bundle opens this copy of MEA-NAP."""
    if sys.platform.startswith("linux"):
        return _status_linux()
    if sys.platform == "win32":
        return _status_windows()
    return _UNSUPPORTED
