"""What happens when a suite2p .npy is empty, truncated, or half-written.

An interrupted run, a full disk, or a copy that stopped part-way all leave the
same thing behind: a file at its final name that no longer holds what its name
promises. The failure that motivated this was a batch over a Dropbox share
dying on one recording with numpy's own message —

    EOFError: No data left in file

— which names neither the file nor the recording, and, because nothing removed
the bad file, recurred on every subsequent run.

Three defences are checked here: the writes that produce these files are atomic
so the state stops being reachable; the reads name the file when it happens
anyway; and files the pipeline can rebuild are rebuilt rather than raised over.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from meanap.catnap.loader import (  # noqa: E402
    UnreadableSuite2pFile, _load_npy, load_suite2p,
)
from meanap.pipeline.atomic import atomic_save, guard_readable  # noqa: E402
from meanap.remote.base import RemoteEntry  # noqa: E402
from meanap.remote.preflight import _check_catnap, _empty_required  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


N_CELLS, N_FRAMES = 6, 400


def make_plane0(root: Path, *, denoised: bool = False) -> Path:
    d = root / "suite2p" / "plane0"
    d.mkdir(parents=True)
    rng = np.random.default_rng(0)
    np.save(d / "F.npy", rng.random((N_CELLS, N_FRAMES)).astype(np.float32) + 1.0)
    np.save(d / "spks.npy", rng.random((N_CELLS, N_FRAMES)).astype(np.float32))
    np.save(d / "iscell.npy", np.ones((N_CELLS, 2)))
    np.save(d / "stat.npy", np.array(
        [{"med": [int(rng.integers(0, 64)), int(rng.integers(0, 64))]}
         for _ in range(N_CELLS)], dtype=object), allow_pickle=True)
    np.save(d / "ops.npy", np.array({"fs": 30.0}, dtype=object), allow_pickle=True)
    if denoised:
        np.save(d / "Fdenoised.npy", rng.random((N_CELLS, N_FRAMES)))
        np.save(d / "timePoints.npy", np.arange(N_FRAMES) / 30.0)
        for name in ("peakStartFrames.npy", "peakEndFrames.npy",
                     "peakHeights.npy", "eventAreas.npy"):
            np.save(d / name, np.full((N_CELLS, 2), 1.0))
    return d


# ── The message names the file ────────────────────────────────────────────────

print("\nThe error names what went wrong, and where")

tmp = Path(tempfile.mkdtemp())
d = make_plane0(tmp / "rec_empty")
(d / "F.npy").write_bytes(b"")

try:
    load_suite2p(d)
    check("an empty F.npy is reported, not swallowed", False, "no error raised")
except UnreadableSuite2pFile as e:
    msg = str(e)
    check("an empty F.npy names the file", "F.npy" in msg, msg)
    check("…and says it is empty rather than 'No data left in file'",
          "empty (0 bytes)" in msg, msg)
    check("…and says what to do about it",
          "interrupted" in msg and "re-export" in msg, msg)

# Truncation is the other half of the same accident, and numpy words it
# differently — both have to land in the same place.
d = make_plane0(tmp / "rec_trunc")
whole = (d / "iscell.npy").read_bytes()
(d / "iscell.npy").write_bytes(whole[: len(whole) // 2])
try:
    load_suite2p(d)
    check("a truncated file is reported too", False, "no error raised")
except UnreadableSuite2pFile as e:
    check("a truncated file names the file too", "iscell.npy" in str(e), str(e))

check("a healthy folder still loads",
      load_suite2p(make_plane0(tmp / "rec_ok")).F.shape == (N_CELLS, N_FRAMES), "")


# ── Half-written denoising output ─────────────────────────────────────────────

print("\nDenoising that stopped part-way")

# The four peak arrays are written together and read together. A folder holding
# some of them was interrupted; reading the survivors would analyse a recording
# against half a peak set.
d = make_plane0(tmp / "rec_halfpeaks", denoised=True)
(d / "peakEndFrames.npy").unlink()
try:
    load_suite2p(d)
    check("a partial peak set is refused", False, "loaded anyway")
except UnreadableSuite2pFile as e:
    check("a partial peak set is refused, naming what is missing",
          "peakEndFrames.npy" in str(e), str(e))
    check("…and says how to recover",
          "denoise again" in str(e), str(e))

check("a complete denoised folder still loads",
      load_suite2p(make_plane0(tmp / "rec_dn", denoised=True))
      .peak_start_frames.shape == (N_CELLS, 2), "")


# ── Writes that cannot leave this state ───────────────────────────────────────

print("\nThe writes are atomic")

target = tmp / "atomic" / "a.npy"


class Boom(Exception):
    pass


try:
    from meanap.pipeline.atomic import atomic_path
    with atomic_path(target, suffix=".npy") as t:
        np.save(t, np.arange(10))
        raise Boom
except Boom:
    pass
check("an interrupted atomic write leaves no file at the final name",
      not target.exists(), "")
check("…and no scratch file behind either",
      not list(target.parent.glob(".*")), str(list(target.parent.glob(".*"))))

atomic_save(target, np.arange(10))
check("a completed atomic_save lands whole",
      np.array_equal(np.load(target), np.arange(10)), "")

# Denoising writes Fdenoised.npy last, because the loader treats its presence
# as "already denoised" — it must not appear before the files it implies.
src = (Path(__file__).resolve().parents[1]
       / "src" / "meanap" / "catnap" / "denoising.py").read_text()
writes = [ln.strip() for ln in src.splitlines() if ln.strip().startswith("atomic_save(")]
check("denoising writes every output atomically",
      len(writes) == 6 and "np.save(out_dir" not in src,
      f"{len(writes)} atomic writes")
check("…and writes Fdenoised.npy last of all",
      writes and "Fdenoised.npy" in writes[-1], writes[-1] if writes else "none")


# ── Rebuildable artefacts are rebuilt, not raised over ────────────────────────

print("\nThe ops sidecar heals itself")

sidecar = tmp / "ops_fields.npz"
sidecar.write_bytes(b"")
check("a zero-byte sidecar is judged unusable", not guard_readable(sidecar), "")
check("…and is deleted so the next run rebuilds it rather than retripping",
      not sidecar.exists(), "")


# ── Caught before anything is downloaded ──────────────────────────────────────

print("\nPreflight catches it at the source")


class FakeStore:
    """A listing where F.npy is present but zero bytes."""

    def __init__(self, sizes):
        self._sizes = sizes

    def list(self, path):
        return [RemoteEntry(path=f"{path}/{n}", size=s, is_dir=False)
                for n, s in self._sizes.items()]


# Sizes that are internally consistent, so the ROI-mismatch check stays quiet
# and only the emptiness check can speak: 6 ROIs x 400 frames of float32 plus
# numpy's 128-byte header, and iscell as (6, 2) float64.
full = {"F.npy": 128 + N_CELLS * N_FRAMES * 4,
        "iscell.npy": 128 + N_CELLS * 2 * 8,
        "stat.npy": 4096, "ops.npy": 8192}
ok = _check_catnap(FakeStore(full), "rec")
check("a healthy listing passes preflight", ok.ok, ok.unusable or "")

broken = _check_catnap(FakeStore({**full, "F.npy": 0}), "rec")
check("a zero-byte required file makes the recording unusable",
      not broken.ok, "")
check("…and is not reported as merely 'missing'",
      not broken.missing and "zero bytes" in (broken.unusable or ""),
      f"missing={broken.missing} unusable={broken.unusable}")
check("…naming the file so it can be re-exported",
      "F.npy" in (broken.unusable or ""), broken.unusable or "")

check("an optional file being empty does not condemn the recording",
      _check_catnap(FakeStore({**full, "spks.npy": 0}), "rec").ok, "")


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All corrupt-file checks passed.")
