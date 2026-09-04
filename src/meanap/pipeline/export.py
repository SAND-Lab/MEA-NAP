"""Turn a bundle back into an ordinary output folder.

An express run keeps only the ``.meanap``, because every figure in it is a pure
function of the data it carries and re-drawing one takes about a tenth of a
second. That is the right trade for the person who ran the analysis. It is the
wrong trade for the person they send it to who has no MEA-NAP: to them a bundle
is a zip of arrays.

So this unpacks the trade. It draws every figure the bundle can produce, into
the same folder layout the pipeline itself writes, and finishes with the
self-contained ``report.html`` browser — a folder anyone can open with nothing
installed.

Nothing here knows how to draw anything. Every figure comes from
:mod:`meanap.pipeline.render`, which calls the pipeline's own plotting code, so
an exported folder is the folder a full run would have written rather than a
lookalike.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from meanap.timescale import timescale_folder

__all__ = ["ExportResult", "export_output_folder", "default_export_dest",
           "unpack_bundle_data"]


@dataclass
class ExportResult:
    """What an export produced."""

    dest: Path
    figures: int = 0
    #: ``(family or figure, reason)`` for anything that could not be drawn. A
    #: bundle from an older version may simply not carry what a family needs.
    skipped: list[tuple[str, str]] = field(default_factory=list)
    report: Path | None = None

    @property
    def ok(self) -> bool:
        return self.figures > 0


def default_export_dest(bundle: Path | str) -> Path:
    """Where an export lands if the caller doesn't say: beside the bundle.

    ``Run.meanap`` → ``Run/``, stepping to ``Run_v2`` only if a folder is
    already there. The bundle itself is not a collision — it is what is being
    exported, and refusing its own name would make every export ``_v2``.
    """
    bundle = Path(bundle)
    parent, stem = bundle.parent, bundle.stem

    candidate = parent / stem
    if not candidate.exists():
        return candidate
    for n in range(2, 100):
        candidate = parent / f"{stem}_v{n}"
        if not candidate.exists():
            return candidate
    return parent / f"{stem}_export"


def export_output_folder(
    source,
    dest: Path | str | None = None,
    *,
    fmt: str = "png",
    report: bool = True,
    log: Callable[[str], None] = print,
    progress: Callable[[int, int], None] | None = None,
) -> ExportResult:
    """Draw a bundle out into a full output folder and return what was made.

    *source* is a ``.meanap`` path or an already-open
    :class:`~meanap.pipeline.bundle.RunBundle`. Data files are copied first, so
    a folder is useful even if a figure family later fails; each family is
    guarded, because one plot that cannot be drawn should cost its own figure
    and nothing else.
    """
    from meanap.pipeline.bundle import RunBundle, open_bundle
    from meanap.pipeline.render import load_context

    opened = None
    if isinstance(source, RunBundle):
        bundle = source
        origin = Path(source.root)
    else:
        opened = bundle = open_bundle(source)
        origin = Path(source)

    try:
        if dest is None:
            if opened is None:
                # An already-open bundle lives in a temporary directory, so
                # "beside it" would put the export somewhere that disappears.
                raise ValueError(
                    "Pass a destination: an open RunBundle has no permanent "
                    "location to put the export beside.")
            dest = default_export_dest(origin)
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)

        # The data first: CSVs, metrics JSON, the .npz state, params, and any
        # figures the bundle carried as images rather than as data.
        copied = _copy_data(Path(bundle.root), dest)
        log(f"Copied {copied} data file(s) to {dest}")

        ctx = load_context(bundle)
        result = ExportResult(dest=dest)
        _draw_everything(ctx, dest, result, fmt=fmt, log=log, progress=progress)

        if report:
            result.report = _write_report(dest, log)
        log(f"Exported {result.figures} figure(s) to {dest}")
        if result.skipped:
            log(f"  {len(result.skipped)} family/families produced nothing:")
            for what, why in result.skipped:
                log(f"    {what}: {why}")
        return result
    finally:
        if opened is not None:
            opened.close()


def unpack_bundle_data(
    bundle: Path | str,
    dest: Path | str,
    *,
    log: Callable[[str], None] = print,
) -> int:
    """Put a bundle's *data* back into an output folder, drawing nothing.

    This is the half of an export a continued run needs. Express mode keeps the
    ``.meanap`` and removes the folder, but continuing decides what to skip by
    looking for each recording's artefact *in the output folder* — so without
    this the two features cancel out and everything is recomputed. Every
    artefact continuing looks for travels in the bundle verbatim
    (``<rec>_spikes.npz``, ``<rec>_adjM.npz``, ``<rec>_catnap.npz``,
    ``netmet_results.json``): only the reconstructable *figures* are dropped,
    and no skip decision is made on a figure.

    Files already in *dest* are left alone. A folder that still exists is the
    newer copy of the two — the bundle beside it was written from an earlier
    state of it — and a run that overwrote a finished recording's artefact with
    a stale one would produce a wrong answer rather than a slow one.

    ``manifest.json`` is not restored: it describes the run the bundle was
    written from, and this run is about to be a different one. Whatever writes
    the next bundle writes the manifest to match.

    Returns how many files were put back.
    """
    from meanap.pipeline.bundle import MANIFEST_NAME, open_bundle

    dest = Path(dest)
    with open_bundle(bundle) as opened:
        root = Path(opened.root)
        n = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name == MANIFEST_NAME:
                continue
            target = dest / path.relative_to(root)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            n += 1
    log(f"Restored {n} data file(s) from {Path(bundle).name}.")
    return n


def _copy_data(root: Path, dest: Path) -> int:
    """Everything the bundle holds, verbatim. The manifest goes too — it is
    what marks the folder as having come from one."""
    n = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        target = dest / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        n += 1
    return n


def _draw_everything(ctx, dest: Path, result: ExportResult, *, fmt: str,
                     log, progress) -> None:
    """Every figure the bundle can produce, in the pipeline's own layout."""
    from meanap.pipeline import render as R

    # Counted up front so the caller can show a bar rather than a spinner.
    jobs: list[tuple[str, Callable[[], None]]] = []

    for name in ctx.recordings:
        rec = ctx.recordings[name]
        for lag in ctx.lags(name):
            # render_figure appends "4A_IndividualNetworkAnalysis/<group>/<rec>/
            # <lag>mslag" itself (step4._plot_recording_lag), so it gets the
            # step folder; everything else below takes the exact directory.
            net_dir = dest / "4_NetworkActivity"
            lag_dir = (net_dir / "4A_IndividualNetworkAnalysis"
                       / rec.group / name / timescale_folder(lag, ctx.params))
            for spec in R.available_figures(ctx, name, lag):
                base = spec.name.format(lag=lag)
                for variant in R.figure_variants(ctx, name, lag, base):
                    jobs.append((
                        f"{name} {lag}ms {base} ({variant})",
                        lambda n=name, l=lag, b=base, v=variant, d=net_dir:
                            R.render_figure(ctx, n, l, b, d, fmt=fmt, variant=v)))
            for spec in R.available_subnetwork_figures(ctx, name, lag):
                jobs.append((
                    f"{name} {lag}ms {spec.name}",
                    lambda n=name, l=lag, s=spec.name,
                           d=lag_dir / "cellTypeSubnetworks":
                        R.render_subnetwork_figure(ctx, n, l, s, d, fmt=fmt)))
            if R.available_subnetwork_figures(ctx, name, lag):
                # The whole 4A set again, once per cell type. Recomputed rather
                # than reassembled — see render_subnetwork_figure_set.
                jobs.append((
                    f"{name} {lag}ms per-subnetwork figure set",
                    lambda n=name, l=lag, d=net_dir:
                        R.render_subnetwork_figure_set(ctx, n, l, d, fmt=fmt)))
            if lag in R.available_edge_check_lags(ctx, name):
                jobs.append((
                    f"{name} {lag}ms thresholding check",
                    lambda n=name, l=lag, d=dest / "3_EdgeThresholdingCheck":
                        R.render_edge_check_figure(ctx, n, l, d, fmt=fmt)))

        activity_dir = dest / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
        for spec in R.available_activity_figures(ctx, name):
            jobs.append((
                f"{name} {spec.name}",
                lambda n=name, s=spec.name, d=activity_dir:
                    R.render_activity_figure(ctx, n, s, d, fmt=fmt)))

        check_dir = (dest / "1_SpikeDetection" / "1B_SpikeDetectionChecks"
                     / rec.group / name)
        for spec in R.available_spike_check_figures(ctx, name):
            jobs.append((
                f"{name} {spec.name}",
                lambda n=name, s=spec.name, d=check_dir:
                    R.render_spike_check_figure(ctx, n, s, d, fmt=fmt)))

    for fam in R.available_group_families(ctx):
        jobs.append((f"family {fam.key}",
                     lambda k=fam.key: R.render_group_family(ctx, k, dest, fmt=fmt)))

    # Step 5, when the run has been through the statistics step. Its tables
    # travel in the bundle and its figures do not, so this is where they come
    # back — into the same 5_StatsAndML/<lag>/ layout the step itself writes,
    # beside the CSVs that were carried.
    for stats_lag in R.available_stats_lags(ctx):
        stats_dir = dest / R.STATS_DIRNAME / stats_lag
        for figure in R.available_stats_figures(ctx, stats_lag):
            jobs.append((
                f"statistics {stats_lag} {figure.key}",
                lambda sl=stats_lag, k=figure.key, d=stats_dir:
                    R.render_stats_figure(ctx, sl, k, d, fmt=fmt)))

    total = len(jobs)
    for i, (what, run) in enumerate(jobs):
        if progress is not None:
            progress(i, total)
        try:
            made = run()
        except Exception as e:                       # noqa: BLE001
            # One figure failing must not cost the other several hundred.
            result.skipped.append((what, f"{type(e).__name__}: {e}"))
            continue
        result.figures += len(made) if isinstance(made, list) else 1
    if progress is not None:
        progress(total, total)


def _write_report(dest: Path, log) -> Path | None:
    """The self-contained HTML browser — the point of exporting at all.

    Guarded: the figures are already on disk and useful without it, so a report
    that fails to generate is a missing convenience rather than a failed export.
    """
    from meanap.pipeline.report import generate_report

    try:
        return generate_report(dest)
    except Exception as e:                           # noqa: BLE001
        log(f"Warning: could not generate report.html: {e}")
        return None
