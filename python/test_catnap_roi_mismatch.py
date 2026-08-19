"""Test what CAT-NAP does with a suite2p folder whose files contradict itself.

Run from the repo root::

    uv run python python/test_catnap_roi_mismatch.py

The case this is built from is real. In
``OPME240520_17_20240602_P1_pup2D_Het_MOI50000_DIV13`` of a 382-recording
share link, ``iscell.npy`` holds 5040 rows while ``F.npy``, ``Fneu.npy``,
``spks.npy`` and ``stat.npy`` all hold 5000 — 40 ROIs drawn by hand in the
suite2p GUI reached the classification file and nothing else. suite2p
*prepends* hand-drawn ROIs and stamps them with a classifier probability of
exactly 1.0 (``gui/drawroi.py``), which is why the extra rows are at the front
and why they are identifiable.

Before this, the run died on ``F[iscell]`` inside the adjacency step with a
bare ``IndexError: boolean index did not match indexed array along axis 0``,
having first denoised all 5000 ROIs — minutes of work, an unreadable message,
and the whole batch lost to one bad folder. Three things are pinned here:

  A. the mismatch is refused at *load* time, with both counts and the repair
     named, and the hand-drawn signature reported when it is present;
  B. denoising never starts, because the check runs before it;
  C. the batch loses that recording only — the same treatment as a folder with
     no suite2p output at all.

Everything runs on synthetic folders; no dataset needed.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap.loader import Suite2pOutputMismatch, load_suite2p  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

Check = tuple[str, bool, str]

N_ROIS, N_FRAMES = 12, 200


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _make_suite2p(root: Path, name: str = "rec1", *,
                  n_rois: int = N_ROIS, iscell_rows: int | None = None,
                  drawn: int = 0, drawn_at_end: bool = False) -> Path:
    """A plane0 folder, optionally with ``iscell.npy`` out of step with the rest.

    ``drawn`` rows carry a probability of exactly 1.0, as suite2p writes for a
    hand-drawn ROI; ``drawn_at_end`` puts them where suite2p never does, to
    check the diagnosis is claimed only when it is earned.
    """
    d = root / name / "suite2p" / "plane0"
    d.mkdir(parents=True)
    rng = np.random.default_rng(0)

    np.save(d / "F.npy", rng.random((n_rois, N_FRAMES)).astype(np.float32) + 1.0)
    np.save(d / "spks.npy", rng.random((n_rois, N_FRAMES)).astype(np.float32))
    stat = np.array([{"med": [int(rng.integers(0, 64)), int(rng.integers(0, 64))]}
                     for _ in range(n_rois)], dtype=object)
    np.save(d / "stat.npy", stat, allow_pickle=True)
    np.save(d / "ops.npy", np.array({"fs": 30.0}, dtype=object), allow_pickle=True)

    rows = n_rois if iscell_rows is None else iscell_rows
    prob = rng.random(rows) * 0.9          # nothing reaches 1.0 by chance
    flags = (prob > 0.5).astype(float)
    if drawn:
        at = np.s_[rows - drawn:] if drawn_at_end else np.s_[:drawn]
        prob[at] = 1.0
        flags[at] = 1.0
    np.save(d / "iscell.npy", np.column_stack([flags, prob]))
    return d


def _load_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # A consistent folder must be untouched by the new check.
        good = _make_suite2p(tmp, "good")
        data = load_suite2p(good)
        checks.append(("a consistent folder still loads",
                       data.F.shape == (N_ROIS, N_FRAMES), f"{data.F.shape}"))
        checks.append(("…and its cell mask still selects traces",
                       data.F_cells.shape[0] == data.n_cells, ""))

        # The real shape of the failure: hand-drawn ROIs, prepended.
        _make_suite2p(tmp, "drawn", iscell_rows=N_ROIS + 3, drawn=3)
        try:
            load_suite2p(tmp / "drawn" / "suite2p" / "plane0")
            msg = ""
        except Suite2pOutputMismatch as e:
            msg = str(e)
        checks.append(("a mismatched folder raises Suite2pOutputMismatch",
                       bool(msg), "no exception"))
        checks.append(("…naming both counts",
                       f"{N_ROIS + 3} ROIs" in msg and f"{N_ROIS} ROIs" in msg,
                       msg[:80]))
        checks.append(("…naming the files that disagree",
                       "iscell.npy" in msg and "F.npy" in msg, ""))
        checks.append(("…identifying the hand-drawn ROIs",
                       "drawn by hand" in msg, msg[-200:]))
        checks.append(("…and the row offset they imply",
                       "minus 3" in msg.replace("\n", " "), msg[-200:]))
        checks.append(("…and the repair, in suite2p not here",
                       "suite2p GUI" in msg and "will not realign" in msg, ""))

        # Same mismatch, no signature: still refused, but nothing is invented.
        _make_suite2p(tmp, "tail", iscell_rows=N_ROIS + 3, drawn=3,
                      drawn_at_end=True)
        try:
            load_suite2p(tmp / "tail" / "suite2p" / "plane0")
            msg = ""
        except Suite2pOutputMismatch as e:
            msg = str(e)
        checks.append(("a mismatch that is not the known one is still refused",
                       bool(msg), "no exception"))
        checks.append(("…without claiming a cause it cannot see",
                       "drawn by hand" not in msg, msg[-120:]))

        # Fewer iscell rows than traces is the same contradiction.
        _make_suite2p(tmp, "short", iscell_rows=N_ROIS - 2)
        try:
            load_suite2p(tmp / "short" / "suite2p" / "plane0")
            msg = ""
        except Suite2pOutputMismatch as e:
            msg = str(e)
        checks.append(("a short iscell.npy is caught too", bool(msg), ""))
    return checks


def _early_and_isolated_checks() -> list[Check]:
    """The check must land before denoising, and cost only its own recording."""
    from meanap.catnap import pipeline as catnap_pipeline

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        plane0 = _make_suite2p(tmp, "rec1", iscell_rows=N_ROIS + 3, drawn=3)

        # `_compute_recording` imports this at call time, so patching the
        # module it comes from is what the runner will actually see.
        import meanap.catnap.denoising as denoising

        denoise_calls: list[Path] = []
        real_denoise = denoising.process_suite2p_folder

        def spy(suite2p_dir, *a, **kw):
            denoise_calls.append(Path(suite2p_dir))
            return real_denoise(suite2p_dir, *a, **kw)

        denoising.process_suite2p_folder = spy
        try:
            log: list[str] = []
            params = Params()
            params.twop_activity = "peaks"     # the path that denoises
            out = catnap_pipeline._compute_recording(
                params, RecordingInfo(filename="rec1", div=21.0, group="WT"),
                plane0, log.append, np.random.default_rng(0),
            )
        finally:
            denoising.process_suite2p_folder = real_denoise

        checks.append(("the recording is skipped, not raised through",
                       out is None, f"{type(out)}"))
        checks.append(("denoising never started",
                       denoise_calls == [], f"{denoise_calls}"))
        text = "\n".join(log)
        checks.append(("the skip is logged against the recording",
                       "[rec1] SKIP" in text, text[:120]))
        checks.append(("…carrying the full diagnosis, not just a summary",
                       "iscell.npy" in text and "suite2p GUI" in text, ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP: suite2p folders whose files disagree about their ROIs")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — refused at load, with the diagnosis:", _load_checks),
        ("B — before denoising, and only this recording:",
         _early_and_isolated_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
