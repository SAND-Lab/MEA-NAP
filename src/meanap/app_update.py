"""The desktop app updating itself: download the new build, install it, reopen.

:func:`meanap.updates.check_app` says which build is newer and which file
holds it for this computer; this module does the rest, without a browser:

1. :func:`download` fetches that file into the app's cache folder and checks
   its size and, where GitHub gives one, its SHA-256.
2. :func:`install` hands it to something that outlives the app — on Windows the
   installer itself, run silently; on macOS a small shell script — and the app
   then quits. Each waits for the app to be gone, puts the new build where the
   old one was, and opens it.
3. On the next start, :func:`take_outcome` says whether that worked.

Downloading it ourselves rather than in a browser also spares the user the
browser's "dangerous download" warning and, on a Mac, the "Open Anyway" step:
both are triggered by the mark a browser puts on what it downloads, and a file
fetched by the app carries none.

Settings and results live outside the app's folder, so they survive.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from meanap import frozen, updates

__all__ = ["UpdateCancelled", "UpdateFailed", "why_not_self_update", "app_bundle",
           "download", "install", "take_outcome", "Outcome"]

_CHUNK = 1 << 20

#: Written just before handing over to the installer; read (and removed) by the
#: next start, which compares the version it is with the one it was meant to be.
_PENDING = "pending-update.json"
#: Written by the macOS script when it had to put the old app back.
_FAILED = "update-failed.txt"


class UpdateCancelled(Exception):
    """The user stopped the download."""


class UpdateFailed(Exception):
    """The download or the hand-over went wrong; the message says how."""


def updates_dir() -> Path:
    return frozen.cache_dir() / "updates"


def app_bundle(executable: str | None = None) -> Path | None:
    """The ``MEA-NAP.app`` folder the running executable sits in (macOS)."""
    path = Path(executable or sys.executable).resolve()
    for parent in path.parents:
        if parent.suffix == ".app":
            return parent
    return None


def why_not_self_update(*, platform: str | None = None,
                        executable: str | None = None) -> str | None:
    """Why this copy cannot replace itself, or ``None`` when it can."""
    platform = platform or sys.platform
    if not frozen.is_frozen():
        return "Only the desktop app updates itself."
    if platform == "win32":
        return None   # the installer knows where it installed the app
    if platform != "darwin":
        return "Updating in place is built for Windows and macOS only."
    bundle = app_bundle(executable)
    if bundle is None:
        return "Could not tell where MEA-NAP is installed."
    if "/AppTranslocation/" in str(bundle) or str(bundle).startswith("/Volumes/"):
        # macOS runs a downloaded app from a hidden read-only copy until it has
        # been moved; and an app opened inside the .dmg is on the .dmg.
        return ("MEA-NAP is running from where it was downloaded, not from "
                "your Applications folder. Drag it into Applications, open it "
                "from there, and it can update itself.")
    if not (os.access(bundle.parent, os.W_OK) and os.access(bundle, os.W_OK)):
        return (f"This account cannot change {bundle.parent}. Download the "
                "new version and install it by hand, or ask an administrator.")
    return None


def download(asset: updates.AppAsset, *,
             progress: Callable[[int, int | None], None] | None = None,
             cancelled: Callable[[], bool] | None = None,
             opener: Callable | None = None) -> Path:
    """Fetch *asset* into the updates folder and return the file.

    *progress* is called with (bytes so far, total or ``None``); *cancelled*
    is polled between chunks. A file that does not match the size or digest
    GitHub gave is deleted, never installed. *opener* is for tests: a callable
    from URL to a readable response.
    """
    import urllib.request

    folder = updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():     # earlier downloads, finished or not
        if old.is_file() and old.name not in (_PENDING, _FAILED):
            old.unlink(missing_ok=True)
    target = folder / asset.name
    part = target.with_name(target.name + ".part")

    if opener is None:
        def opener(url):
            request = urllib.request.Request(url, headers={"User-Agent": "MEA-NAP"})
            return urllib.request.urlopen(request, timeout=updates.NETWORK_TIMEOUT_S,
                                          context=updates._ssl_context())
    digest = hashlib.sha256()
    done = 0
    try:
        with opener(asset.url) as response, open(part, "wb") as out:
            total = asset.size or _content_length(response)
            while chunk := response.read(_CHUNK):
                if cancelled is not None and cancelled():
                    raise UpdateCancelled
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except UpdateCancelled:
        part.unlink(missing_ok=True)
        raise
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise UpdateFailed(f"The download stopped: {exc}") from exc
    if asset.size is not None and done != asset.size:
        part.unlink(missing_ok=True)
        raise UpdateFailed(f"The download was incomplete ({done:,} of {asset.size:,} bytes).")
    if asset.sha256 is not None and digest.hexdigest() != asset.sha256.lower():
        part.unlink(missing_ok=True)
        raise UpdateFailed("The downloaded file is not the one GitHub lists "
                           "(its checksum differs). Nothing was installed.")
    part.replace(target)
    return target


def _content_length(response) -> int | None:
    try:
        return int(response.headers.get("Content-Length"))
    except (AttributeError, TypeError, ValueError):
        return None


def install(installer: Path, *, version: str, running: str,
            platform: str | None = None, executable: str | None = None,
            popen: Callable = subprocess.Popen) -> None:
    """Start replacing this app with *installer*; the caller must then quit.

    Returns once the hand-over is running. *version* is the tag being
    installed, recorded so the next start can tell whether it took.
    """
    platform = platform or sys.platform
    folder = updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / _FAILED).unlink(missing_ok=True)
    (folder / _PENDING).write_text(json.dumps({"to": version, "from": running}))
    detached = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL, "close_fds": True}
    try:
        if platform == "win32":
            # /RELAUNCH=1 is read by meanap.iss, whose usual "Launch MEA-NAP"
            # tick box is skipped when silent. The installer waits for, and if
            # need be closes, this app (CloseApplications) before replacing it.
            flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            popen([str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   "/CLOSEAPPLICATIONS", "/RELAUNCH=1", f"/LOG={folder / 'install.log'}"],
                  creationflags=flags, **detached)
        elif platform == "darwin":
            bundle = app_bundle(executable)
            if bundle is None:
                raise UpdateFailed("Could not tell where MEA-NAP is installed.")
            script = folder / "install.sh"
            script.write_text(_mac_script())
            log = open(folder / "install.log", "w")  # noqa: SIM115 - the child owns it
            popen(["/bin/sh", str(script), str(os.getpid()), str(installer),
                   str(bundle), str(folder / _FAILED)],
                  start_new_session=True, **{**detached, "stdout": log, "stderr": log})
        else:
            raise UpdateFailed("Updating in place is built for Windows and macOS only.")
    except OSError as exc:
        (folder / _PENDING).unlink(missing_ok=True)
        raise UpdateFailed(f"Could not start the installer: {exc}") from exc
    except UpdateFailed:
        (folder / _PENDING).unlink(missing_ok=True)
        raise


def _mac_script() -> str:
    """Wait for the app to quit, swap in the new one from the .dmg, open it.

    The new app is copied beside the old before anything is moved, so the
    swap itself is two renames in one folder; if either fails the old app is
    put back and opened, with the reason left for :func:`take_outcome`.
    """
    return """\
#!/bin/sh
pid=$1 dmg=$2 app=$3 failed=$4
fail() { echo "$1" > "$failed"; [ -d "$app" ] && open "$app"; exit 1; }
while kill -0 "$pid" 2>/dev/null; do sleep 0.5; done
mnt=$(mktemp -d) || fail "Could not make a temporary folder."
hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$mnt" "$dmg" \\
  || fail "Could not open the downloaded disk image."
new="$app.new.$$" old="$app.old.$$"
ditto "$mnt/MEA-NAP.app" "$new"; copied=$?
hdiutil detach "$mnt" -quiet || hdiutil detach "$mnt" -force -quiet
[ $copied -eq 0 ] || { rm -rf "$new"; fail "Could not copy the new MEA-NAP out of the disk image."; }
# Fetched by the app, not a browser, it should carry no quarantine mark; make sure.
xattr -dr com.apple.quarantine "$new" 2>/dev/null
mv "$app" "$old" || { rm -rf "$new"; fail "Could not move the old MEA-NAP aside."; }
mv "$new" "$app" || { mv "$old" "$app"; fail "Could not put the new MEA-NAP in place."; }
rm -rf "$old" "$dmg"
open "$app"
"""


@dataclass(frozen=True)
class Outcome:
    ok: bool
    message: str


def take_outcome(running: str | None = None) -> Outcome | None:
    """How the last update went, once, on the first start after it; else ``None``."""
    folder = updates_dir()
    pending = folder / _PENDING
    if not pending.exists():
        return None
    try:
        meant = json.loads(pending.read_text()).get("to")
    except (OSError, ValueError, AttributeError):
        meant = None
    failed = folder / _FAILED
    reason = failed.read_text().strip() if failed.exists() else ""
    pending.unlink(missing_ok=True)
    failed.unlink(missing_ok=True)
    running = running or updates.app_running_version()
    if meant and running == meant and not reason:
        return Outcome(True, f"MEA-NAP was updated to {meant}.")
    log = folder / "install.log"
    return Outcome(False, (
        f"The update to {meant or 'the new version'} did not finish"
        + (f": {reason}" if reason else ".")
        + f" This is still {running}. You can download the new version from "
        f"{updates.RELEASES_PAGE} and install it by hand."
        + (f"\n\nDetails: {log}" if log.exists() else "")))

