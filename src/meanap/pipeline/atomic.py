"""Writes that either land whole or not at all.

Everything the pipeline writes, it used to write in place: open the final path,
stream bytes into it, hope. That is fine until a run is interrupted — Ctrl-C, a
cluster job hitting its wall clock, a laptop lid — and then the file that was
mid-write is left truncated, at its final name, looking exactly like a finished
one.

That is survivable when the only cost is redoing the work. It stops being
survivable once a run can *continue* from what is already on disk, because then
"the file is there" is taken to mean "that recording is done". A truncated
``.npz`` would be skipped and then fail to load in a later step, hours away from
the thing that caused it.

So resumable artefacts are written to a temporary name in the same directory and
then :func:`os.replace`\\ d into place, which is atomic on POSIX and on Windows.
A reader sees the old file or the new one, never a partial one, and an interrupt
leaves the temporary file behind rather than a corrupt result.

Same directory matters: ``os.replace`` is only atomic within a filesystem, and a
temp dir is often a different one.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

__all__ = ["atomic_path", "atomic_write_json", "atomic_savez", "is_readable_npz"]


@contextmanager
def atomic_path(path: Path | str, suffix: str = ""):
    """Yield a temporary path; on clean exit, move it onto *path*.

    ``suffix`` is worth passing when the writer picks its behaviour from the
    extension — ``numpy.savez`` appends ``.npz`` to a name that lacks it, which
    would otherwise move the wrong file into place.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                               suffix=suffix or ".tmp")
    os.close(fd)
    tmp = Path(tmp)
    try:
        yield tmp
        os.replace(tmp, path)
    except BaseException:
        # Includes KeyboardInterrupt: an interrupted write must not leave its
        # scratch file lying around looking like a result.
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path | str, obj: Any, **kwargs) -> Path:
    """Serialise *obj* to *path* as JSON, atomically."""
    path = Path(path)
    with atomic_path(path) as tmp:
        with open(tmp, "w") as fh:
            json.dump(obj, fh, **kwargs)
    return path


def atomic_savez(
    path: Path | str, *, compressed: bool = False, **arrays,
) -> Path:
    """``numpy.savez`` to *path*, atomically.

    ``savez`` insists on an ``.npz`` extension, adding one if the name lacks it,
    so the temporary file is given that extension up front rather than being
    renamed out from under us.
    """
    import numpy as np

    path = Path(path)
    save = np.savez_compressed if compressed else np.savez
    with atomic_path(path, suffix=".npz") as tmp:
        save(tmp, **arrays)
    return path


def is_readable_npz(path: Path | str) -> bool:
    """Whether *path* is an ``.npz`` that opens and lists its members.

    A cheap integrity check for artefacts written before atomic writes existed,
    or by something else. It reads the zip directory, not the arrays, so it
    costs a seek rather than a load.
    """
    import numpy as np

    path = Path(path)
    if not path.is_file():
        return False
    try:
        with np.load(path, allow_pickle=False) as data:
            data.files
    except Exception:                                   # noqa: BLE001
        return False
    return True


def guard_readable(path: Path | str, on_bad: Callable[[str], None] | None = None) -> bool:
    """``True`` if the artefact can be trusted; otherwise remove it and say so.

    Used where a run decides whether to skip already-done work. Deleting the bad
    file rather than leaving it means the recording is redone this time *and*
    next time, instead of tripping the same check on every future run.
    """
    if is_readable_npz(path):
        return True
    path = Path(path)
    if path.exists():
        if on_bad is not None:
            on_bad(f"  {path.name} is unreadable — redoing it "
                   f"(a previous run was probably interrupted mid-write)")
        path.unlink(missing_ok=True)
    return False
