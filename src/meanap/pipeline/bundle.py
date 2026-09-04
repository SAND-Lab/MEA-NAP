"""The ``.meanap`` run bundle — one shareable file per analysis run.

A full run's output folder is mostly pictures: 92 MB and 603 PNGs for one
recording of the CAT-NAP example dataset, against roughly 1 MB of the data
those pictures were drawn from. Every network figure is a pure function of that
data, so carrying the pictures around is carrying a ~90× redundant copy.

Express mode (``Params.express_mode``) therefore skips every figure that can be
rebuilt and writes only the data, plus the handful of quality-control figures
that *cannot* be rebuilt because they depend on raw recordings far too large to
carry — the 2P traces.

The spike-detection checks look like they belong in that category, and were
treated as if they did. But almost none of the voltage they are drawn from is
actually *visible* in them: the example-trace panels clip to a ±30 ms window,
the waveform panel uses one channel, and the frequency panel needs only spike
times. They now travel as the slices they display — tens of kilobytes against
roughly twenty times that in pictures. See :mod:`meanap.pipeline.plotting`.

:func:`write_bundle` packs the folder into a single file that can be emailed,
attached to a paper, or dropped in a shared drive, and :func:`open_bundle`
turns it back into something the pipeline and the viewer can both read.

**Layout.** A bundle is a zip whose entries mirror an output folder:

===================================  =========================================
``manifest.json``                    format version, mode, recordings, lags,
                                     which figure families are reconstructable
``params.json``                      the settings the run used
``ExperimentMatFiles/<rec>_catnap.npz``   adjacency, coords, activity stats
``ExperimentMatFiles/<rec>_background.npz``  mean projection (optional)
``4_NetworkActivity/…``              metrics JSON + the CSVs
``2_NeuronalActivity/…``             activity CSVs + kept trace figures
``1_SpikeDetection/1A_…``            spike times + the check-figure payload
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
from meanap.timescale import timescale_kind

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
    # Rebuilt from <rec>_step1checks.npz in 1A, which travels instead. The
    # pictures were over half of a bundle's bytes; the payload is ~20x smaller.
    "1_SpikeDetection/1B_SpikeDetectionChecks",
)

#: Folders whose *data* travels but whose figures do not. Unlike
#: :data:`_RECONSTRUCTABLE_DIRS`, which drops a folder entirely because the data
#: behind it lives elsewhere, these hold both: the statistics step writes its
#: results as CSVs *and* as figures into one folder, and every figure is a pure
#: function of the CSVs beside it (see :mod:`meanap.stats.figures`). Carrying
#: the CSVs is ~100 kB against ~4 MB of PNGs for the same information.
_DATA_ONLY_DIRS = (
    "5_StatsAndML",
)

#: Extensions treated as figures under :data:`_DATA_ONLY_DIRS`.
_FIGURE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".svg", ".pdf", ".eps"})

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
    "1B_spike_detection_checks",    # ephys: example traces, frequencies, waveforms
    "3_edge_threshold_checks",      # ephys: probabilistic-thresholding stability
    "cell_type_subnetwork_per_rec",  # CAT-NAP: per-recording subnetwork figures
    "5_stats",                      # step 5: comparisons, structure, decoding, attribution
)

#: Figure families express mode drops that the viewer cannot rebuild, so they
#: are simply absent until the run is repeated without express mode. Stated in
#: the manifest rather than left to be discovered: silently missing figures are
#: the failure mode this whole feature has to avoid.
#:
#: Empty, as of the run bundle carrying the step-1, step-3 and subnetwork
#: payloads. Kept rather than deleted because the manifest field is part of the
#: format, and a future family that cannot be rebuilt belongs here.
UNRECONSTRUCTABLE_FAMILIES: tuple[str, ...] = ()


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
    from meanap.version import version_stamp

    return {
        "format": FORMAT_VERSION,
        "mode": mode,
        # Which pipeline, at which version, produced this. ``format`` above is
        # the *bundle layout*; this is the code. A reader years from now needs
        # both, and they move independently.
        **version_stamp(mode),
        "express": bool(params.express_mode),
        "lags": [int(v) for v in (lags if lags is not None else params.func_con_lag_val)],
        # What those numbers *are*: STTC coincidence windows ("lag"), or the
        # bin lengths a CAT-NAP correlation run averaged traces into ("bin").
        # The viewer labels its controls from this rather than assuming — see
        # meanap.timescale. Absent in bundles written before this field, which
        # readers should treat as "lag".
        "timescale": timescale_kind(params),
        "recordings": [
            {"filename": r.filename, "group": r.group, "div": r.div}
            for r in recordings
        ],
        "reconstructable": list(RECONSTRUCTABLE_FAMILIES),
        "not_reconstructable": list(UNRECONSTRUCTABLE_FAMILIES),
        "embedded_figures": list(embedded_figures or []),
    }


#: Two families are reconstructable only when their step left a payload behind.
#: An output folder written before those existed has the pictures and no
#: payload, so each pair moves together: either drop the folder and claim the
#: family, or keep the folder and don't. Entries are
#: ``(figure dir, family name, embedded name, payload probe)``.
_SPIKE_CHECK_DIR = "1_SpikeDetection/1B_SpikeDetectionChecks"
_EDGE_CHECK_DIR = "3_EdgeThresholdingCheck"


def _has_spike_check_payload(root: Path) -> bool:
    from meanap.pipeline.plotting import CHECKS_SUFFIX
    from meanap.pipeline.resume import SPIKE_SUBDIR

    return any((root / SPIKE_SUBDIR).glob(f"*{CHECKS_SUFFIX}"))


def _has_edge_check_payload(root: Path) -> bool:
    from meanap.pipeline.plotting_step3 import EDGE_CHECK_SUFFIX

    return any((root / "ExperimentMatFiles").glob(f"*{EDGE_CHECK_SUFFIX}"))


_PAYLOAD_FAMILIES = (
    (_SPIKE_CHECK_DIR, "1B_spike_detection_checks", "spike_detection_checks",
     _has_spike_check_payload),
    (_EDGE_CHECK_DIR, "3_edge_threshold_checks", "edge_threshold_checks",
     _has_edge_check_payload),
)


def _strip_activity_prefix(posix: str) -> str:
    """``ByActivityType/denoisedF/4_NetworkActivity/x`` → ``4_NetworkActivity/x``."""
    from meanap.catnap.activities import BY_ACTIVITY_DIR

    prefix = f"{BY_ACTIVITY_DIR}/"
    if not posix.startswith(prefix):
        return posix
    rest = posix[len(prefix):]
    _measure, sep, tail = rest.partition("/")
    return tail if sep else posix


def _keep_as_images(root: Path) -> tuple[str, ...]:
    """Figure dirs to pack verbatim because their payload isn't there.

    Only when the pictures actually exist: a run that never produced them has
    nothing to keep and nothing to say about it.
    """
    return tuple(
        figure_dir for figure_dir, _fam, _emb, has_payload in _PAYLOAD_FAMILIES
        if not has_payload(root) and any((root / figure_dir).rglob("*.png"))
    )


def _is_reconstructable_member(rel: Path, keep: tuple[str, ...] = ()) -> bool:
    # A multi-measure CAT-NAP run puts each extra measure's complete run folder
    # under ByActivityType/<measure>/, so the same figure families sit one level
    # deeper. Stripping that prefix before matching drops them from the bundle
    # exactly as the primary measure's are dropped — they are reconstructable
    # from the same data, which travels in that subtree beside them. Without
    # this an extra measure's pictures would be the largest thing in the bundle.
    posix = _strip_activity_prefix(rel.as_posix())
    dirs = tuple(d for d in _RECONSTRUCTABLE_DIRS if d not in keep)
    if any(posix.startswith(d) for d in dirs):
        return True
    # Data-only folders keep everything that is not a picture.
    return (any(posix.startswith(d) for d in _DATA_ONLY_DIRS)
            and rel.suffix.lower() in _FIGURE_SUFFIXES)


def _claim_stats(manifest: dict, root: Path) -> dict:
    """Say the bundle carries step-5 figures, when the folder has step-5 data.

    ``reconstructable`` is otherwise a static list of what this *version* can
    rebuild, filled in by :func:`build_manifest`. The statistics step runs after
    a run finishes, though, so a folder is often bundled again once it has been
    through it — carrying a manifest built before the folder had any statistics
    in it. Topping the list up here means that re-bundle does not under-report
    what it contains.
    """
    if not any((root / "5_StatsAndML").rglob("*.csv")):
        return manifest
    families = list(manifest.get("reconstructable", []))
    if "5_stats" in families:
        return manifest
    out = dict(manifest)
    out["reconstructable"] = families + ["5_stats"]
    return out


def _adjust_manifest(manifest: dict, keep: tuple[str, ...]) -> dict:
    """Say which families this bundle carries as images rather than as data.

    Only for those. ``reconstructable`` otherwise describes what this *version*
    can rebuild rather than what a given bundle happens to contain — a CAT-NAP
    run has no step 1 and no opinion about it, and per-recording availability is
    already answered by the ``available_*`` functions.
    """
    if not keep:
        return manifest

    out = dict(manifest)
    reconstructable = list(out.get("reconstructable", []))
    not_reconstructable = list(out.get("not_reconstructable", []))
    embedded = list(out.get("embedded_figures", []))

    for figure_dir, family, embedded_name, _probe in _PAYLOAD_FAMILIES:
        if figure_dir not in keep:
            continue
        reconstructable = [f for f in reconstructable if f != family]
        if family not in not_reconstructable:
            not_reconstructable.append(family)
        if embedded_name not in embedded:
            embedded.append(embedded_name)

    out["reconstructable"] = reconstructable
    out["not_reconstructable"] = not_reconstructable
    out["embedded_figures"] = embedded
    return out


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

    The exception is folders written before a step saved the payload its checks
    are rebuilt from — step 1's detection checks, step 3's thresholding checks.
    Those are packed as images after all, and the manifest is amended to match,
    because dropping them would simply lose them.

    Returns the path written.
    """
    root = Path(output_root)
    if not root.is_dir():
        raise ValueError(f"Not an output folder: {root}")

    dest = Path(dest) if dest is not None else root.with_suffix(BUNDLE_SUFFIX)
    dest.parent.mkdir(parents=True, exist_ok=True)

    keep = _keep_as_images(root)
    manifest = _adjust_manifest(manifest, keep)
    manifest = _claim_stats(manifest, root)

    with open(root / MANIFEST_NAME, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if _is_reconstructable_member(rel, keep):
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
