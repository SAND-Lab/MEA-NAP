"""The ``.meanap`` run bundle — one shareable file per analysis run.

A full run's output folder is mostly pictures: 92 MB and 603 PNGs for one
recording of the CAT-NAP example dataset, against roughly 1 MB of the data
those pictures were drawn from. Every network figure is a pure function of that
data, so carrying the pictures around is carrying a ~90× redundant copy.

Express mode (``Params.express_mode``) therefore skips every figure that can be
rebuilt and writes only the data, plus the handful of quality-control figures
that *cannot* be rebuilt because they depend on raw recordings far too large to
carry — the 2P traces, and on the electrophysiology side the spike-detection
checks. :func:`write_bundle` then packs the folder into a single file that can
be emailed, attached to a paper, or dropped in a shared drive, and
:func:`open_bundle` turns it back into something the pipeline and the viewer
can both read.

**Layout.** A bundle is a zip whose entries mirror an output folder:

===================================  =========================================
``manifest.json``                    format version, mode, recordings, lags,
                                     which figure families are reconstructable
``params.json``                      the settings the run used
``ExperimentMatFiles/<rec>_catnap.npz``   adjacency, coords, activity stats
``ExperimentMatFiles/<rec>_background.npz``  mean projection (optional)
``4_NetworkActivity/…``              metrics JSON + the CSVs
``2_NeuronalActivity/…``             activity CSVs + kept trace figures
``1_SpikeDetection/1B_…``            kept spike-detection checks (ephys)
===================================  =========================================

Mirroring the folder rather than inventing a schema buys three things: the
existing ``report.py`` browser works on an extracted bundle unchanged; resuming
from a bundle needs no new lookup logic, because :mod:`meanap.pipeline.resume`
already knows these paths; and anyone without this software can open the zip
and find plain CSVs.

**Opening extracts.** Bundles are ~1 MB, so :func:`open_bundle` unpacks to a
temporary directory and hands back a real path. That keeps every consumer —
resume, the renderer, the report browser — working on ordinary files rather
than each growing its own zip-aware I/O path.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from meanap.params import PARAMS_FILENAME, Params, load_params, redact

__all__ = [
    "BUNDLE_SUFFIX",
    "MANIFEST_NAME",
    "FORMAT_VERSION",
    "RECONSTRUCTABLE_FAMILIES",
    "UNRECONSTRUCTABLE_FAMILIES",
    "RunBundle",
    "write_bundle",
    "open_bundle",
    "is_bundle",
]

BUNDLE_SUFFIX = ".meanap"
MANIFEST_NAME = "manifest.json"
FORMAT_VERSION = 1

#: Folders whose figures are reconstructable from the bundle's data, and so are
#: never packed even when a *full* (non-express) run is bundled. Everything else
#: in the output folder is carried verbatim.
_RECONSTRUCTABLE_DIRS = (
    "4_NetworkActivity/4A_IndividualNetworkAnalysis",
    "4_NetworkActivity/4B_GroupComparisons",
    "2_NeuronalActivity/2B_GroupComparisons",
    "3_EdgeThresholdingCheck",
)

#: Figure families a viewer can rebuild from a bundle. Must correspond to what
#: :mod:`meanap.pipeline.render` actually implements — ``test_bundle_render.py``
#: asserts that, because a manifest that overclaims is worse than one that says
#: nothing: it promises a figure the viewer will never produce.
#:
#: (Not derived from ``render.GROUP_FAMILIES`` directly because ``render``
#: imports this module, and the cycle isn't worth breaking for four strings.)
RECONSTRUCTABLE_FAMILIES = (
    "4A_individual_network",        # the per-recording network figure set
    "4B_group_comparisons",         # network metrics by group and age
    "2B_activity_comparisons",      # activity by group and age (both pipelines)
    "cell_type_activity",           # CAT-NAP: activity split by cell type
    "cell_type_subnetwork_groups",  # CAT-NAP: subnetwork *group* comparisons
    "2A_individual_activity",       # ephys: rasters, heatmaps, burst detail
)

#: Figure families express mode drops that the viewer cannot currently rebuild,
#: so they are simply absent until the run is repeated without express mode.
#: Stated in the manifest rather than left to be discovered: silently missing
#: figures are the failure mode this whole feature has to avoid.
#:
#: The first is *not* fundamental — its inputs are in the bundle, the
#: reconstruction is just not wired up yet. The last two genuinely cannot be
#: rebuilt at any size: they depend on raw data a bundle deliberately omits.
UNRECONSTRUCTABLE_FAMILIES = (
    "cell_type_subnetwork_per_rec",   # CAT-NAP: per-recording subnetwork figures
    "3_edge_threshold_checks",        # needs the surrogate distributions
    "1B_spike_detection_checks",      # needs the raw voltage (kept as images)
)


def is_bundle(path: Path | str) -> bool:
    """Whether *path* looks like a bundle file (as opposed to an output folder)."""
    p = Path(path)
    return p.is_file() and p.suffix == BUNDLE_SUFFIX


@dataclass
class RunBundle:
    """An opened bundle: a real directory plus the manifest that describes it.

    Use as a context manager (or call :meth:`close`) so the extracted copy is
    cleaned up; ``root`` stays valid until then.
    """

    root: Path
    manifest: dict
    params: Params
    #: Params keys the bundle carried that this version doesn't know — a
    #: version-skew signal worth surfacing rather than silently dropping.
    unknown_param_keys: list[str] = field(default_factory=list)
    _tempdir: str | None = None

    # ── description ──────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        """``"catnap"``, ``"ephys"`` … — which pipeline produced this run."""
        return str(self.manifest.get("mode", "unknown"))

    @property
    def recordings(self) -> list[dict]:
        """``[{"filename", "group", "div"}, …]`` as recorded at write time."""
        return list(self.manifest.get("recordings", []))

    @property
    def lags(self) -> list[int]:
        return [int(v) for v in self.manifest.get("lags", [])]

    def can_reconstruct(self, family: str) -> bool:
        return family in self.manifest.get("reconstructable", [])

    # ── lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._tempdir is not None:
            shutil.rmtree(self._tempdir, ignore_errors=True)
            self._tempdir = None

    def __enter__(self) -> "RunBundle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def build_manifest(
    params: Params,
    recordings: list,
    *,
    mode: str,
    lags: list[int] | None = None,
    embedded_figures: list[str] | None = None,
) -> dict:
    """The manifest for a run, describing what a viewer can and cannot redraw.

    ``embedded_figures`` names the families packed as images because they are
    *not* reconstructable — the honest counterpart to ``reconstructable``.
    """
    return {
        "format": FORMAT_VERSION,
        "mode": mode,
        "express": bool(params.express_mode),
        "lags": [int(v) for v in (lags if lags is not None else params.func_con_lag_val)],
        "recordings": [
            {"filename": r.filename, "group": r.group, "div": r.div}
            for r in recordings
        ],
        "reconstructable": list(RECONSTRUCTABLE_FAMILIES),
        "not_reconstructable": list(UNRECONSTRUCTABLE_FAMILIES),
        "embedded_figures": list(embedded_figures or []),
    }


def _is_reconstructable_member(rel: Path) -> bool:
    posix = rel.as_posix()
    return any(posix.startswith(d) for d in _RECONSTRUCTABLE_DIRS)


def write_bundle(
    output_root: Path | str,
    manifest: dict,
    dest: Path | str | None = None,
) -> Path:
    """Pack an output folder into a single ``.meanap`` file.

    ``dest`` defaults to ``<output_root>.meanap`` beside the folder. Figures
    under the reconstructable folders are skipped even if present, so bundling
    a full (non-express) run still produces a small file rather than a zipped
    copy of every PNG.

    Returns the path written.
    """
    root = Path(output_root)
    if not root.is_dir():
        raise ValueError(f"Not an output folder: {root}")

    dest = Path(dest) if dest is not None else root.with_suffix(BUNDLE_SUFFIX)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(root / MANIFEST_NAME, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if _is_reconstructable_member(rel):
                continue
            if rel.as_posix() == PARAMS_FILENAME:
                # The copy in the output folder keeps everything — it never
                # leaves this machine. The copy that travels does not.
                with open(path) as fh:
                    zf.writestr(PARAMS_FILENAME,
                                json.dumps(redact(json.load(fh)), indent=2,
                                           sort_keys=True))
                continue
            zf.write(path, rel.as_posix())

    return dest


def open_bundle(path: Path | str) -> RunBundle:
    """Extract a bundle to a temporary directory and read its manifest.

    Raises :class:`ValueError` with an actionable message on anything that
    isn't a readable bundle of a format this version understands — a bundle is
    something users hand to each other, so the failure modes are "someone sent
    me the wrong file" and "someone sent me a newer file", and both deserve to
    be said plainly.
    """
    src = Path(path)
    if not src.is_file():
        raise ValueError(f"Bundle not found: {src}")
    if not zipfile.is_zipfile(src):
        raise ValueError(
            f"{src.name} is not a MEA-NAP bundle (not a zip archive). Bundles are "
            f"written by an express-mode run and end in '{BUNDLE_SUFFIX}'."
        )

    tmp = tempfile.mkdtemp(prefix="meanap-bundle-")
    try:
        with zipfile.ZipFile(src) as zf:
            _extract_safely(zf, Path(tmp))

        root = Path(tmp)
        manifest_path = root / MANIFEST_NAME
        if not manifest_path.exists():
            raise ValueError(
                f"{src.name} has no {MANIFEST_NAME} — it is a zip, but not a "
                "MEA-NAP bundle."
            )
        with open(manifest_path) as fh:
            manifest = json.load(fh)

        fmt = int(manifest.get("format", 0))
        if fmt > FORMAT_VERSION:
            raise ValueError(
                f"{src.name} is a format-{fmt} bundle; this version reads up to "
                f"format {FORMAT_VERSION}. Update MEA-NAP to open it."
            )

        params, unknown = Params(), []
        if (root / PARAMS_FILENAME).exists():
            params, unknown = load_params(root / PARAMS_FILENAME)

        return RunBundle(root=root, manifest=manifest, params=params,
                         unknown_param_keys=unknown, _tempdir=tmp)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _extract_safely(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract, refusing entries that would escape *dest*.

    Bundles travel between people, so a malicious or merely malformed archive
    with ``../`` or absolute paths must not be able to write outside the
    temporary directory (the "zip slip" problem). Python's ``extractall`` has
    guarded against this since 3.6.2 for most cases, but the check is cheap and
    the consequence of being wrong is arbitrary file overwrite.
    """
    dest = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if not target.is_relative_to(dest):
            raise ValueError(
                f"Refusing to extract '{member.filename}': it points outside the "
                "extraction directory."
            )
    zf.extractall(dest)
