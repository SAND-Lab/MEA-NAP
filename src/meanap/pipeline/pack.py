"""Pack a finished output folder into a ``.meanap`` bundle.

Express mode writes a bundle because it never drew the figures. A normal run
writes an output folder and nothing else — 111 MB and several hundred PNGs on a
two-recording batch, against the ~3 MB of numbers every one of them was drawn
from. So the question comes up as soon as someone wants to email their results,
or attach them to a paper: *can I have the shareable file without re-running the
analysis?*

They can, and nothing has to be recomputed. Everything a bundle carries is
already on disk when a run finishes, and :func:`~meanap.pipeline.bundle.write_bundle`
has always been folder-in, file-out. The one piece it could not supply for
itself is the manifest, which the runner built from live pipeline state — the
recordings it analysed, the pipeline it ran, the timescales it used. This
module recovers that from the folder:

=========================================================  ======================
``params.json``                                            settings → pipeline, lags
``4_NetworkActivity/NetworkActivity_RecordingLevel.csv``   the recordings
``2_NeuronalActivity/2A_IndividualNeuronalAnalysis``       whether 2P traces travel
=========================================================  ======================

That is the same set :mod:`meanap.pipeline.render` reads to draw a figure out of
an unbundled folder, for the same reason: a finished output folder describes
itself, and anything that has to guess is guessing about a run it is holding.

This is the counterpart of :mod:`meanap.pipeline.export`, which goes the other
way. The asymmetry worth knowing is that neither of these destroys its input —
an *express run* removes its output folder once the bundle reads back, because
keeping both is keeping two copies of the same run, but a folder bundled by hand
is a folder the user still wants. It is left exactly where it was.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from meanap.params import PARAMS_FILENAME, Params, load_params
from meanap.pipeline.bundle import (
    BUNDLE_SUFFIX, MANIFEST_NAME, build_manifest, open_bundle, write_bundle,
)
from meanap.pipeline.spreadsheet import RecordingInfo

__all__ = ["BundleResult", "bundle_output_folder", "default_bundle_dest",
           "unbundlable_reason"]

#: The recording-level table, which every run that reached step 4 writes. It is
#: the folder's own record of which recordings the analysis covered — better
#: than the spreadsheet, which may since have been edited, and better than the
#: file listing, which includes recordings a continued run has dropped.
_RECORDING_CSV = Path("4_NetworkActivity") / "NetworkActivity_RecordingLevel.csv"

#: What the viewer needs before it can open a bundle at all.
_METRICS_JSON = Path("4_NetworkActivity") / "netmet_results.json"

#: CAT-NAP's per-unit peak-detection figures, the one family that travels as
#: pictures. Laid out ``<group>/<recording>/*.png`` — see
#: :func:`meanap.pipeline.render.available_trace_figures`.
_TRACE_DIR = Path("2_NeuronalActivity") / "2A_IndividualNeuronalAnalysis"


@dataclass
class BundleResult:
    """What packing a folder produced."""

    dest: Path
    recordings: int = 0
    size_bytes: int = 0
    #: Things that are true of the bundle and that the user should know, rather
    #: than reasons to have refused. A folder that stopped before step 4 still
    #: bundles usefully — it just cannot be *viewed* — and saying so is more
    #: use than declining to write it.
    warnings: list[str] = field(default_factory=list)

    @property
    def size_mb(self) -> float:
        return self.size_bytes / 1e6


def default_bundle_dest(output_root: Path | str) -> Path:
    """Where a bundle lands if the caller doesn't say: beside the folder.

    ``Run/`` → ``Run.meanap``, stepping to ``Run_v2.meanap`` only if one is
    already there. An express run of the same name leaves a bundle whose folder
    was then deleted, so overwriting by default would destroy the only surviving
    copy of a different run.

    ``with_suffix`` rather than appending, matching
    :func:`~meanap.pipeline.bundle.write_bundle` and
    :func:`~meanap.pipeline.output_folders.output_paths_for` — the GUI finds a
    run's bundle by that name, and a file written under any other rule would
    simply not be found.
    """
    root = Path(output_root)
    candidate = root.with_suffix(BUNDLE_SUFFIX)
    if not candidate.exists():
        return candidate
    for n in range(2, 100):
        candidate = root.with_name(f"{root.name}_v{n}").with_suffix(BUNDLE_SUFFIX)
        if not candidate.exists():
            return candidate
    return root.with_name(f"{root.name}_new").with_suffix(BUNDLE_SUFFIX)


def bundle_output_folder(
    output_root: Path | str,
    dest: Path | str | None = None,
    *,
    log: Callable[[str], None] = print,
    verify: bool = True,
) -> BundleResult:
    """Pack a finished output folder into one shareable ``.meanap`` file.

    *dest* defaults to :func:`default_bundle_dest`. The folder is read, never
    moved or emptied — the only thing written into it is ``manifest.json``,
    which :func:`~meanap.pipeline.bundle.write_bundle` leaves behind so the
    folder and the bundle agree about what the run was.

    Figures the viewer can redraw are left out, so bundling a *full* run gives
    the same small file an express run would have written rather than a zipped
    copy of every PNG.

    With *verify* (the default) the file is opened again before this returns —
    the same check an express run makes before it deletes anything. A bundle is
    a thing people email, so "it was written" is not the claim worth making;
    "it opens" is. One that does not is removed rather than left to be sent.

    Raises :class:`ValueError` if *output_root* is not a MEA-NAP output folder,
    or if the bundle will not read back.
    """
    root = Path(output_root)
    reason = unbundlable_reason(root)
    if reason is not None:
        raise ValueError(reason)

    warnings: list[str] = []
    stored = _stored_manifest(root)
    params = _read_params(root)
    if params is None:
        # A folder exported from a bundle written by a version that redacted
        # more than it does now, or one whose params were removed by hand. The
        # manifest still says which pipeline and which lags, which is what the
        # viewer reads; the settings panel in it will simply be empty.
        params = Params()
        warnings.append(
            f"no {PARAMS_FILENAME} in the folder — the bundle carries the run's "
            "metrics but not the settings that produced them")

    mode = _mode(params, root, stored)
    lags = _lags(params, root, stored)
    recordings = _recordings(root, stored)
    if not recordings:
        warnings.append(
            f"no recordings found — expected {_RECORDING_CSV.as_posix()}. The "
            "bundle will open, but with nothing in it to look at")
    if not (root / _METRICS_JSON).exists():
        warnings.append(
            f"no {_METRICS_JSON.as_posix()} — this run did not reach step 4, so "
            "the viewer cannot open the bundle. It is still valid as something "
            "to resume from")

    manifest = build_manifest(
        params, recordings, mode=mode, lags=lags,
        embedded_figures=["2p_traces"] if _has_trace_figures(root) else [],
    )

    dest = Path(dest) if dest is not None else default_bundle_dest(root)
    log(f"Packing {root} into {dest.name} …")
    written = write_bundle(root, manifest, dest)

    if verify:
        _verify(written)

    result = BundleResult(dest=written, recordings=len(recordings),
                          size_bytes=written.stat().st_size, warnings=warnings)
    log(f"Bundle written: {written}  ({result.size_mb:.1f} MB, "
        f"{result.recordings} recording{'' if result.recordings == 1 else 's'})")
    log(f"  The output folder is untouched. Open the bundle with: "
        f'meanap-viewer "{written}"')
    return result


def unbundlable_reason(output_root: Path | str) -> str | None:
    """Why *output_root* cannot be packed, or ``None`` if it can.

    Asked separately from the pack itself so a caller can find out before it
    commits the user to anything. The GUI asks where to save the bundle first,
    and discovering only afterwards that there was never going to be one is a
    dialog spent for nothing.
    """
    root = Path(output_root)
    if not root.is_dir():
        return f"Not an output folder: {root}"
    if _read_params(root) is None and not _stored_manifest(root):
        return _not_an_output_folder(root)
    return None


# ── Reading a folder's own account of itself ─────────────────────────────────

def _not_an_output_folder(root: Path) -> str:
    """Why this folder cannot be bundled, said in terms of what to do instead.

    The two ways to arrive here are the two worth telling apart. Pointing at
    the *parent* of the output folders is the ordinary slip. Pointing at a
    MATLAB run is not a slip at all — the folder is a perfectly good analysis,
    it simply predates a format only the Python pipeline writes, and "does not
    look like an output folder" would read as an accusation that it is broken.
    """
    if any(root.glob("Parameters_*.mat")) or any(root.glob("Parameters_*.csv")):
        return (
            f"{root.name} is a MATLAB MEA-NAP output folder. Bundles are packed "
            "from the data the Python pipeline writes (params.json, "
            "netmet_results.json, the .npz files), which a MATLAB run does not "
            "produce — so this folder cannot be bundled without re-running the "
            "analysis in Python."
        )
    return (
        f"{root.name} does not look like a MEA-NAP output folder: it has no "
        f"{PARAMS_FILENAME} and no {MANIFEST_NAME}. Pick the folder a run "
        "wrote — the one holding 1_SpikeDetection, 4_NetworkActivity and so "
        "on — rather than the folder those runs are written into."
    )


def _read_params(root: Path) -> Params | None:
    """The run's settings, or ``None`` if the folder does not carry them."""
    path = root / PARAMS_FILENAME
    if not path.exists():
        return None
    try:
        return load_params(path)[0]
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _stored_manifest(root: Path) -> dict:
    """A manifest already in the folder, if any.

    Folders acquire one two ways: exported out of a bundle, or bundled before.
    It is a *fallback* rather than the answer — bundling a folder again after
    recordings were added must describe the folder as it is now, not as it was
    when it was last packed.
    """
    path = root / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        with open(path) as fh:
            loaded = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _mode(params: Params, root: Path, stored: dict) -> str:
    """Which pipeline wrote this folder."""
    if (root / PARAMS_FILENAME).exists():
        return "catnap" if params.suite2p_mode else "ephys"
    stored_mode = stored.get("mode")
    if isinstance(stored_mode, str) and stored_mode:
        return stored_mode
    # No settings and no manifest to ask: CAT-NAP is the pipeline that writes
    # <rec>_catnap.npz, and nothing else does.
    return "catnap" if any((root / "ExperimentMatFiles").glob("*_catnap.npz")) \
        else "ephys"


def _lags(params: Params, root: Path, stored: dict) -> list[int]:
    """The timescales this folder holds results for.

    The metrics are asked first, and the settings only fill in for a folder
    whose step 4 wrote nothing. ``func_con_lag_val`` is what was *requested*;
    the keys of ``netmet_results.json`` are what the run came back with, and a
    manifest that claims a lag the bundle has no metrics for gives the viewer a
    control that selects an empty figure list.
    """
    from_metrics = _lags_from_metrics(root)
    if from_metrics:
        return from_metrics
    if (root / PARAMS_FILENAME).exists():
        return [int(v) for v in params.func_con_lag_val]
    return [int(v) for v in stored.get("lags", [])]


def _lags_from_metrics(root: Path) -> list[int]:
    """Lags read back from the run's own metrics, as ``25mslag`` → ``25``."""
    path = root / _METRICS_JSON
    if not path.exists():
        return []
    try:
        with open(path) as fh:
            results = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    lags: set[int] = set()
    for per_lag in (results or {}).values():
        if not isinstance(per_lag, dict):
            continue
        for key in per_lag:
            text = str(key).removesuffix("mslag")
            try:
                lags.add(int(float(text)))
            except ValueError:
                continue
    return sorted(lags)


def _recordings(root: Path, stored: dict) -> list[RecordingInfo]:
    """The recordings this folder's results actually cover."""
    # render already answers this for a plain folder, which is how the viewer
    # opens one. Shared rather than reimplemented so the two cannot come to
    # disagree about which recordings a folder holds.
    from meanap.pipeline.render import _recordings_from_csv

    rows = _recordings_from_csv(root) or stored.get("recordings", [])
    out = []
    for row in rows:
        name = row.get("filename")
        if not name:
            continue
        try:
            div = float(row.get("div") or 0)
        except (TypeError, ValueError):
            div = 0.0
        out.append(RecordingInfo(filename=str(name), div=div,
                                 group=str(row.get("group") or "")))
    return out


def _has_trace_figures(root: Path) -> bool:
    """Whether CAT-NAP peak-detection traces are here to be carried as images.

    They are the one family the bundle cannot redraw — they need the full
    fluorescence matrices — so the manifest has to declare them as embedded or
    the viewer will not offer what the bundle is in fact carrying.
    """
    return any((root / _TRACE_DIR).glob("*/*/*.png"))


def _verify(written: Path) -> None:
    """Open the bundle we just wrote, and remove it if it will not open.

    Leaving a broken file in place is the worse failure: it is the right size,
    it has the right name, and the first sign of trouble is the person it was
    sent to.
    """
    try:
        # Opening is the check: it unzips every entry, finds the manifest and
        # refuses a format this version cannot read. Nothing is asserted about
        # the contents here — an empty run is reported as a warning by the
        # caller, not treated as a corrupt file.
        open_bundle(written).close()
    except Exception as exc:  # noqa: BLE001 - re-raised with the context
        written.unlink(missing_ok=True)
        raise ValueError(
            f"The bundle was written but would not read back ({exc}). It has "
            f"been removed rather than left to be sent; {written.parent} is "
            "otherwise untouched."
        ) from exc
