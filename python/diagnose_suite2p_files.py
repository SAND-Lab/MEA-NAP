#!/usr/bin/env python3
"""Find the suite2p/derived .npy that a run choked on.

Written for the failure that says only::

    EOFError: No data left in file

which is numpy's wording for a **zero-byte** ``.npy`` and names neither the
file nor the recording. This walks a data folder (and, if given, the cache and
derived folders beside it) and reports every ``.npy``/``.npz`` that is empty,
truncated, or otherwise unreadable — cheaply, by reading each file's header
rather than its arrays.

    python python/diagnose_suite2p_files.py <folder> [<folder> ...]
    python python/diagnose_suite2p_files.py <folder> --delete-derived

``--delete-derived`` removes the bad files that the pipeline can rebuild by
itself (denoising outputs and the ``ops`` sidecar), so the next run redoes that
recording instead of tripping over the same file again. Raw suite2p output is
never touched: if ``F.npy`` is empty at the source, only a re-export fixes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

#: Files this pipeline produces and can therefore reproduce.
DERIVED = {
    "Fdenoised.npy", "timePoints.npy", "peakStartFrames.npy",
    "peakEndFrames.npy", "peakHeights.npy", "eventAreas.npy",
    "ops_fields.npz",
}


def inspect(path: Path) -> str | None:
    """Why *path* is unreadable, or None if it is fine."""
    try:
        size = path.stat().st_size
    except OSError as e:
        return f"cannot be stat'd ({e})"
    if size == 0:
        return "is EMPTY (0 bytes) — this is what 'No data left in file' means"
    try:
        # mmap_mode reads the header and shape without pulling the array
        # through memory, which matters when the file is a few hundred MB. It
        # refuses object arrays (stat.npy, ops.npy) and .npz, so those fall
        # back to a real load.
        obj = np.load(path, allow_pickle=True, mmap_mode="r")
        if hasattr(obj, "close"):       # NpzFile — check it lists its members
            with obj as z:
                z.files
        else:
            obj.shape                   # memmap: header parsed, nothing read
    except Exception as e:
        # mmap refuses pickled object arrays (stat.npy, ops.npy) for reasons
        # that have nothing to do with the file being damaged, and it words
        # that refusal several ways. Rather than pattern-match the message,
        # fall back to a real load and believe only what that says.
        try:
            np.load(path, allow_pickle=True)
        except Exception as inner:
            return (f"is unreadable ({type(inner).__name__}: {inner})"
                    if not isinstance(inner, ValueError)
                    else f"is TRUNCATED or malformed ({inner})")
        del e
    return None


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    delete = "--delete-derived" in argv
    if not args:
        print(__doc__)
        return 2

    bad: list[tuple[Path, str]] = []
    scanned = 0
    for root in args:
        base = Path(root).expanduser()
        if not base.exists():
            print(f"skipping {base} — no such folder")
            continue
        for path in sorted(base.rglob("*.np[yz]")):
            scanned += 1
            why = inspect(path)
            if why:
                bad.append((path, why))

    print(f"\nScanned {scanned} .npy/.npz files under {', '.join(args)}.\n")
    if not bad:
        print("Every one of them reads. The failure is not an unreadable "
              "array file — re-run with the full traceback and check what "
              "else it names.")
        return 0

    print(f"{len(bad)} unreadable file(s):\n")
    removable = []
    for path, why in bad:
        tag = "  [rebuildable]" if path.name in DERIVED else "  [SOURCE DATA]"
        print(f"  {path}\n      {why}{tag}")
        if path.name in DERIVED:
            removable.append(path)

    print()
    if delete and removable:
        for path in removable:
            path.unlink(missing_ok=True)
        print(f"Deleted {len(removable)} rebuildable file(s). Re-run the "
              f"pipeline; those recordings will be denoised again.")
    elif removable:
        print(f"{len(removable)} of these {'is a file' if len(removable) == 1 else 'are files'} "
              f"MEA-NAP produced and can rebuild. Re-run with "
              f"--delete-derived to remove {'it' if len(removable) == 1 else 'them'}, "
              f"then run the pipeline again.")

    source = [p for p, _ in bad if p.name not in DERIVED]
    if source:
        print(f"\n{len(source)} {'is' if len(source) == 1 else 'are'} raw "
              f"suite2p output. Deleting {'that' if len(source) == 1 else 'those'} "
              f"will not help — if they are empty at the source, the recording "
              f"has to be re-exported from suite2p (or re-downloaded, if the "
              f"copy you have is the damaged one).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
