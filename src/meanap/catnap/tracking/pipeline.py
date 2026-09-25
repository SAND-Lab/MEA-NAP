"""Run cross-day cell tracking over a dataset.

Ties the pieces together in the order the design requires:

1. group recordings into chains (``chains``)
2. rasterise iscell-filtered footprints (``footprint``)
3. solve robust per-session offsets (``register``)
4. **gate**: chains in which no session would move by ``min_shift_px`` or
   more are passed through untouched -- correcting an offset you cannot
   measure injects error
5. stage the shifted ROIs on a padded canvas and run ROICaT with its own
   registration disabled (``roicat``)
6. **complete**: fold together two clusters that are one cell tracked in two
   pieces on disjoint days, then attach the unmatched cell sitting exactly
   where a tracked cluster should be on a day it is missing from
   (``complete``) -- ROICaT declines both on footprint similarity, and by
   activity they are indistinguishable from the matches it accepts
7. validate against activity the matcher never saw (``validate``)
8. write per-chain results, a manifest, and QC pages (``viewer``)

Every chain records **why** it was treated the way it was, so a surprising match
rate can be traced back to its offset and gate decision rather than guessed at.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from meanap.catnap.tracking.chains import Chain, build_chains
from meanap.catnap.tracking.complete import (
    COMPLETION_RADIUS_PX,
    complete_clusters,
    merge_split_clusters,
)
from meanap.catnap.tracking.footprint import DENSITY_BIN_PX, density_map
from meanap.catnap.tracking.register import (
    MIN_SHIFT_PX,
    RELIABLE_NCC,
    padded_frame,
    shift_stat,
    solve_offsets,
    verify_offsets,
)
from meanap.catnap.tracking.roicat import match_rates, run_chain, stage_session
from meanap.catnap.tracking.validate import (
    NEUCOEFF,
    auc_vs_null,
    event_metrics,
    fingerprints,
    reduce_session,
)
from meanap.catnap.tracking.network import (
    MIN_SHARED_CELLS,
    NODE_METRICS,
    edges_above,
    metric_stability,
    metric_stability_null,
    node_metrics,
    role_stability,
    shared_indices,
    stability,
    subnetwork,
)
from meanap.catnap.tracking.quality import (
    chain_quality,
    compare_metrics,
    footprint_overlap,
)
from meanap.catnap.tracking.viewer import (
    CellCard,
    SessionView,
    build_payload,
    crop_footprint,
    masks_image_png,
    mean_image_png,
    roi_id_png,
    select_cards,
    write_page,
)

ProgressFn = Callable[[str], None]


class SessionSource(Protocol):
    """Where a recording's ROIs and mean image come from.

    Abstracted so the pipeline can run against a local tree, a derived-data
    root, or a share link without knowing which.
    """

    def stat(self, recording: str) -> np.ndarray: ...
    def mean_image(self, recording: str) -> np.ndarray: ...
    def frame_px(self, recording: str) -> int: ...


@dataclass
class ChainResult:
    """One chain's outcome, with the reasoning that produced it."""

    chain: str
    divs: list[int]
    genotype: str = ""
    prep: str = ""
    registered: bool = False
    measured_shift_px: float = 0.0
    residual_shift_px: float = 0.0
    offsets: list[list[int]] = field(default_factory=list)
    n_roi: list[int] = field(default_factory=list)
    frac_tracked: list[float] = field(default_factory=list)
    pairwise: dict = field(default_factory=dict)
    #: Fingerprint AUC against the nearest-neighbour null. A *descriptor*, not a
    #: gate: ~0.68 is the dataset average and is far too weak to accept or
    #: reject an individual match. It is independent of ``pairwise``, and the
    #: two disagree -- a high match rate does not mean well-matched cells.
    fingerprint_auc: float = float("nan")
    n_fingerprints: int = 0
    #: Cluster members added by position after ROICaT (``complete.py``), as
    #: ``{cluster, div, roi, dist_px}``. Every count above includes them; the
    #: by-pair table also carries ``shared_roicat`` so they can be left out.
    rescued: list = field(default_factory=list)
    #: The fingerprint test run on the rescued members alone. On the Mecp2 run
    #: it matches the accepted matches' (0.675 vs 0.684); a chain where it does
    #: not is one where position alone was not enough.
    rescued_fingerprint_auc: float = float("nan")
    n_rescued_fingerprints: int = 0
    #: Clusters folded into another because they are one cell tracked in two
    #: pieces on disjoint days, as ``{cluster, absorbed, dist_px, divs}`` --
    #: ``divs`` being the days that came from the absorbed half.
    merged: list = field(default_factory=list)
    #: The fingerprint test across the joins alone.
    merged_fingerprint_auc: float = float("nan")
    n_merged_fingerprints: int = 0
    #: Chain quality as a vector (separability / coverage / persistence /
    #: residual shift). Not collapsed into one number: the parts fail
    #: independently, and a composite was measured to add nothing (see
    #: ``quality.py``).
    quality: dict = field(default_factory=dict)
    #: Whether the correlation structure among tracked cells survives across
    #: days, per day-pair, each with its spatial null. Far stronger evidence
    #: than the per-cell fingerprint (AUC 0.94 against 0.68) because a whole
    #: matrix of edges averages out what swamps a single cell's row.
    network_stability: list = field(default_factory=list)
    #: The same cells' network on each day, laid out on the first day's
    #: coordinates, small enough to travel in a bundle.
    network: dict = field(default_factory=dict)
    #: Whether each node measure, and the cartography role, holds across days.
    #: Roles carry Cohen's kappa as well as raw agreement: these subnetworks are
    #: ~90% peripheral, so two unrelated labellings already agree ~85%.
    network_metric_stability: list = field(default_factory=list)
    note: str = ""

    @property
    def median_match(self) -> float:
        rates = [v["frac_of_smaller"] for v in self.pairwise.values()]
        return float(np.median(rates)) if rates else 0.0


def track_chain(
    chain: Chain,
    source: SessionSource,
    work_dir: Path,
    *,
    min_shift_px: float = MIN_SHIFT_PX,
    reliable_ncc: float = RELIABLE_NCC,
    bin_px: int = DENSITY_BIN_PX,
    validate: bool = True,
    viewer_dir: Path | None = None,
    viewer_cells: int = 0,
    neucoeff: float = NEUCOEFF,
    completion_radius_px: float = COMPLETION_RADIUS_PX,
    reuse_runs: Path | None = None,
    progress: ProgressFn | None = None,
) -> ChainResult:
    """Register (if warranted), match, complete, and summarise one chain.

    ``completion_radius_px`` <= 0 turns the completion step off.
    ``reuse_runs`` names an earlier run's ``work/runs`` directory; a chain whose
    ROICaT clusters are there, produced under the *same* gate decision, reads
    them back instead of spending ten minutes recomputing them. Everything
    after ROICaT is still redone.
    """
    names = [r.name for r in chain.recordings]
    divs = [r.div for r in chain.recordings]
    result = ChainResult(chain=chain.key, divs=divs,
                         genotype=chain.genotype, prep=chain.prep)

    stats = [source.stat(n) for n in names]
    frame_px = source.frame_px(names[0])
    maps = [density_map(s, frame_px, bin_px=bin_px) for s in stats]

    offsets = solve_offsets(maps, reliable_ncc=reliable_ncc, bin_px=bin_px)
    result.measured_shift_px = offsets.max_session_shift_px
    result.registered = offsets.should_register(min_shift_px)

    if result.registered:
        residual = verify_offsets(maps, offsets.offsets, bin_px=bin_px)
        result.residual_shift_px = residual["median_after_px"]
        result.offsets = offsets.offsets.tolist()
        height, width, pad_y, pad_x = padded_frame(offsets.offsets, frame_px)
        staged = [shift_stat(s, int(o[0]), int(o[1]), pad_y, pad_x, (height, width))
                  for s, o in zip(stats, offsets.offsets)]
    else:
        # below the gate the measurement is not distinguishable from noise, so
        # the honest correction is none at all
        result.residual_shift_px = offsets.max_session_shift_px
        result.offsets = [[0, 0]] * len(names)
        result.note = (f"largest session offset {offsets.max_session_shift_px:.1f} px "
                       f"is below the {min_shift_px:.0f} px gate; passed through unregistered")
        height = width = frame_px
        staged = stats

    chain_dir = work_dir / "staged" / chain.key
    for name, div, stat in zip(names, divs, staged):
        stage_session(chain_dir / f"DIV{div:02d}", stat,
                      source.mean_image(name), height, width)

    if progress:
        progress(f"{chain.key}: {'registered' if result.registered else 'passed through'} "
                 f"({offsets.max_session_shift_px:.1f} px)")

    # exactly one registration happens: ours if we registered, ROICaT's if we
    # deliberately did not
    run = None
    if reuse_runs is not None:
        run = _reuse_clusters(Path(reuse_runs), work_dir / "runs" / chain.key,
                              chain.key, pre_registered=result.registered,
                              offsets=result.offsets)
    if run is None:
        run = run_chain(chain_dir, work_dir / "runs" / chain.key, chain.key,
                        pre_registered=result.registered)
    labels = [np.asarray(s, dtype=int) for s in run["labels_bySession"]]
    if not labels:
        result.note = (result.note + "; " if result.note else "") + "no clusters found"
        return result

    before = match_rates(labels, divs)
    if completion_radius_px > 0:
        # The lookup wants the best geometry there is. A registered chain's
        # staged ROIs already share a frame; a passed-through chain's were
        # handed to ROICaT unshifted (its residual is below the gate), but its
        # solved offsets are still the best estimate of where a cell should be.
        centroids = [np.array([r["med"][:2] for r in st], dtype=float) for st in staged]
        if not result.registered:
            centroids = [c - np.asarray(o, dtype=float)
                         for c, o in zip(centroids, offsets.offsets)]
        # merge first: a cluster made whole has a better expected position
        # for completion to look at
        absorbed_days = {}
        for s, lab in enumerate(labels):
            for c in set(int(x) for x in lab if x >= 0):
                absorbed_days.setdefault(c, []).append(divs[s])
        labels, merges = merge_split_clusters(labels, centroids,
                                              radius_px=completion_radius_px)
        result.merged = [{"cluster": m.cluster, "absorbed": m.absorbed,
                          "dist_px": round(m.dist_px, 1),
                          "divs": sorted(absorbed_days.get(m.absorbed, []))}
                         for m in merges]
        labels, rescues = complete_clusters(labels, centroids,
                                            radius_px=completion_radius_px)
        result.rescued = [{"cluster": r.cluster, "div": divs[r.session],
                           "roi": r.roi, "dist_px": round(r.dist_px, 1)}
                          for r in rescues]
    rates = match_rates(labels, divs)
    result.n_roi = rates["n_roi"]
    result.frac_tracked = rates["frac_tracked"]
    result.pairwise = rates["pairwise"]
    for pair, v in result.pairwise.items():
        v["shared_roicat"] = before["pairwise"][pair]["shared"]

    if validate or viewer_dir is not None:
        try:
            _validate_and_render(chain, source, labels, result,
                                 viewer_dir=viewer_dir, viewer_cells=viewer_cells,
                                 neucoeff=neucoeff, validate=validate)
        except Exception as exc:
            # validation is evidence about the matches, not the matches
            # themselves; losing it must not lose the chain
            result.note = (result.note + "; " if result.note else "") + \
                f"validation failed: {type(exc).__name__}: {exc}"
            if progress:
                progress(f"{chain.key}: validation failed — {exc}")
    return result


def _reuse_clusters(runs_dir: Path, dest_dir: Path, name: str,
                    *, pre_registered: bool, offsets: list | None = None
                    ) -> dict | None:
    """Read back an earlier run's ROICaT clusters for this chain, if they were
    produced from the same staging.

    The gate decision is recorded in ROICaT's own ``params_used.json``: a
    pre-registered chain ran with ``NullRegistration``, a passed-through one
    with ``PhaseCorrelation``. The staged geometry is checked against the
    earlier run's chain result when it is there (``<run>/chains/<name>.json``,
    next to ``work/``): the offsets may differ by a common translation, which
    the matcher cannot see, and by nothing else.
    """
    import shutil

    src = runs_dir / name
    clusters = src / f"{name}.tracking.results_clusters.json"
    params = src / f"{name}.tracking.params_used.json"
    if not clusters.exists() or not params.exists():
        return None
    try:
        method = json.loads(params.read_text())["aligner"]["fit_geometric"]["method"]
    except (KeyError, ValueError, TypeError):
        return None
    if (method == "NullRegistration") != pre_registered:
        return None
    earlier = runs_dir.parent.parent / "chains" / f"{name}.json"
    if pre_registered and offsets is not None and earlier.exists():
        try:
            before = np.asarray(json.loads(earlier.read_text())["offsets"], dtype=float)
        except (KeyError, ValueError, TypeError):
            return None
        now = np.asarray(offsets, dtype=float)
        if before.shape != now.shape:
            return None
        delta = now - before
        if np.abs(delta - delta[0]).max() > 1.0:
            return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in (clusters, params):
        if f.resolve() != (dest_dir / f.name).resolve():
            shutil.copy2(f, dest_dir / f.name)
    by_session = json.loads(clusters.read_text()).get("labels_bySession") or []
    return {"labels_bySession": [np.asarray(s, dtype=int).tolist() for s in by_session]}


def _validate_and_render(
    chain: Chain,
    source: SessionSource,
    labels: list[np.ndarray],
    result: ChainResult,
    *,
    viewer_dir: Path | None,
    viewer_cells: int,
    neucoeff: float,
    validate: bool,
) -> None:
    """Score matches against activity the matcher never saw, and draw the page."""
    names = [r.name for r in chain.recordings]
    sessions, rates, ieis, traces = [], [], [], []
    for name in names:
        F, fs = source.traces(name, neucoeff=neucoeff)
        stat = source.stat(name)
        centroids = np.array([r["med"][:2] for r in stat], dtype=float)
        sessions.append(reduce_session(F, centroids))
        traces.append(F)
        peaks = source.peak_starts(name)
        if peaks is not None:
            rate, iei = event_metrics(peaks, F.shape[1], fs)
        else:
            rate = np.full(F.shape[0], np.nan)
            iei = np.full(F.shape[0], np.nan)
        rates.append(rate)
        ieis.append(iei)

    index = [{int(c): i for i, c in enumerate(lab) if c >= 0} for lab in labels]
    # The spatial metrics have to be measured in the *registered* frame. The
    # source hands back raw coordinates, so a chain we shifted by 40 px would
    # otherwise report every matched pair as 40 px apart.
    offsets = (result.offsets if result.registered and result.offsets
               else [[0, 0]] * len(sessions))
    aligned = [np.asarray(s.centroids, dtype=float) - np.asarray(off, dtype=float)
               for s, off in zip(sessions, offsets)]

    from meanap.catnap.tracking.validate import nearest_other

    stats_for_metrics = [source.stat(name) for name in names]
    matched, null, per_cluster = [], [], {}
    # the rescued members get their own AUC: it is the check that position
    # alone was enough on this chain, kept apart from the pooled number
    rescued_at = {(int(r["cluster"]), int(r["div"])) for r in result.rescued}
    rescued_matched, rescued_null = [], []
    merged_at = {(int(m["cluster"]), int(d)) for m in result.merged for d in m["divs"]}
    merged_matched, merged_null = [], []
    # every metric, for matched pairs and for their spatial nulls, so a cell can
    # be placed against both populations rather than shown as a bare number
    pools: dict[str, dict[str, list]] = {}
    per_cluster_metrics: dict[int, dict[str, list]] = {}

    def _record(key, kind, value):
        if value is not None and np.isfinite(value):
            pools.setdefault(key, {"matched": [], "null": []})[kind].append(float(value))

    for a in range(len(sessions)):
        for b in range(a + 1, len(sessions)):
            rows = fingerprints(sessions[a], sessions[b], index[a], index[b])
            for row in rows:
                matched.append(row["matched"])
                null.append(row["nearest"])
                per_cluster.setdefault(row["cluster"], []).append(row["matched"])
                if ((row["cluster"], result.divs[a]) in rescued_at
                        or (row["cluster"], result.divs[b]) in rescued_at):
                    rescued_matched.append(row["matched"])
                    rescued_null.append(row["nearest"])
                # a pair that straddles the join -- one day from each half
                elif (((row["cluster"], result.divs[a]) in merged_at)
                        != ((row["cluster"], result.divs[b]) in merged_at)):
                    merged_matched.append(row["matched"])
                    merged_null.append(row["nearest"])
                _record("fingerprint", "matched", row["matched"])
                _record("fingerprint", "null", row["nearest"])

                cluster = row["cluster"]
                i, j = index[a][cluster], index[b][cluster]
                jn = nearest_other(sessions[b].centroids, j)
                for kind, jj in (("matched", j), ("null", jn)):
                    vals = {
                        "d_event_rate": abs(rates[a][i] - rates[b][jj]),
                        "d_iei": abs(ieis[a][i] - ieis[b][jj]),
                        "d_pop_coupling": abs(sessions[a].pop_coupling[i]
                                              - sessions[b].pop_coupling[jj]),
                        "centroid_shift": float(np.linalg.norm(
                            aligned[a][i] - aligned[b][jj])),
                        "footprint_iou": footprint_overlap(
                            stats_for_metrics[a][i], stats_for_metrics[b][jj],
                            offsets[a], offsets[b]),
                    }
                    for key, value in vals.items():
                        _record(key, kind, value)
                    if kind == "matched":
                        store = per_cluster_metrics.setdefault(cluster, {})
                        for key, value in vals.items():
                            if np.isfinite(value):
                                store.setdefault(key, []).append(float(value))

    if validate and matched:
        result.fingerprint_auc = auc_vs_null(np.array(matched), np.array(null))
        result.n_fingerprints = len(matched)
        if rescued_matched:
            result.rescued_fingerprint_auc = auc_vs_null(
                np.array(rescued_matched), np.array(rescued_null))
            result.n_rescued_fingerprints = len(rescued_matched)
        if merged_matched:
            result.merged_fingerprint_auc = auc_vs_null(
                np.array(merged_matched), np.array(merged_null))
            result.n_merged_fingerprints = len(merged_matched)
        spans = [len(v) for v in _cluster_spans(labels).values()]
        result.quality = asdict(chain_quality(
            chain.key, fingerprint_auc=result.fingerprint_auc,
            pair_rates=[v["frac_of_smaller"] for v in result.pairwise.values()],
            cluster_spans=spans, n_sessions=len(labels),
            residual_shift_px=result.residual_shift_px,
            n_fingerprints=result.n_fingerprints))

    _network_summary(result, sessions, labels)

    if viewer_dir is None:
        return

    scores = {c: float(np.median(v)) for c, v in per_cluster.items()}
    null_arr = np.asarray(null, dtype=float)
    stats = stats_for_metrics
    np_pools = {k: {kind: np.asarray(v, dtype=float) for kind, v in sides.items()}
                for k, sides in pools.items()}
    null_only = {k: sides.get("null", np.array([])) for k, sides in np_pools.items()}
    matched_only = {k: sides.get("matched", np.array([])) for k, sides in np_pools.items()}
    frame_px = source.frame_px(names[0])

    present: dict[int, list[tuple[int, int]]] = {}
    for k, lab in enumerate(labels):
        for i, c in enumerate(lab):
            if c >= 0:
                present.setdefault(int(c), []).append((k, i))

    cards = []
    for cluster, entries in present.items():
        if len(entries) < 2:
            continue
        score = scores.get(cluster, float("nan"))
        pct = (float((null_arr < score).mean() * 100)
               if null_arr.size and np.isfinite(score) else float("nan"))
        values = {"fingerprint": score}
        for key, vals in per_cluster_metrics.get(cluster, {}).items():
            values[key] = float(np.median(vals))
        cards.append(CellCard(
            positions=[(k, float(sessions[k].centroids[i][0]),
                        float(sessions[k].centroids[i][1])) for k, i in entries],
            cluster=cluster,
            divs=[result.divs[k] for k, _ in entries],
            crops=[crop_footprint(stats[k][i], frame_px) for k, i in entries],
            traces=[traces[k][i] for k, i in entries],
            metrics=[{"rate": rates[k][i], "iei": ieis[k][i],
                      "pop": sessions[k].pop_coupling[i]} for k, i in entries],
            fingerprint=score, percentile=pct,
            comparisons=compare_metrics(values, null_only, matched_only),
            rescued_divs=[result.divs[k] for k, _ in entries
                          if (cluster, result.divs[k]) in rescued_at],
            merged_divs=[result.divs[k] for k, _ in entries
                         if (cluster, result.divs[k]) in merged_at]))
    if not cards:
        return

    views = []
    for k, name in enumerate(names):
        views.append(SessionView(
            div=result.divs[k],
            mean_png=mean_image_png(source.mean_image(name)),
            masks_tracked_png=masks_image_png(stats[k], frame_px, labels[k],
                                              tracked=True),
            masks_other_png=masks_image_png(stats[k], frame_px, labels[k],
                                            tracked=False),
            centroids=sessions[k].centroids,
            cluster_of=labels[k],
            recording=name,
            masks_id_png=roi_id_png(stats[k], frame_px),
            roi_index=(source.roi_index(name) if hasattr(source, "roi_index")
                       else None)))

    chosen = select_cards(cards, viewer_cells)
    good = sum(1 for c in chosen if np.isfinite(c.fingerprint) and c.fingerprint >= 0.5)
    subtitle = (
        (f"{len(cards)} tracked cells, worst first. " if len(chosen) == len(cards)
         else f"{len(chosen)} of {len(cards)} tracked cells shown, worst first. ")
        + f"{good} score r &ge; 0.50. "
        f"{'Registered' if result.registered else 'Passed through unregistered'}; "
        f"largest field-of-view shift {result.measured_shift_px:.1f} px."
        + (f" {len(result.rescued)} cell-days added by position."
           if result.rescued else "")
        + (f" {len(result.merged)} split cells joined."
           if result.merged else ""))
    title = f"Tracked cells — {chain.key}"
    fs = source.frame_rate(names[0])
    write_page(viewer_dir / f"{chain.key}.html", title, subtitle, chosen, fs,
               sessions=views, frame_px=frame_px, pools=np_pools)

    # The same contents as data, so the bundle can carry one chain's evidence
    # without carrying a rendered copy of it. The page is a view of this; the
    # viewer rebuilds the page from it, which is how every other figure family
    # in a bundle works.
    payload = build_payload(title, subtitle, chosen, fs, views, np_pools)
    payload["frame"] = int(frame_px)
    payload["chainKey"] = chain.key
    payload_dir = viewer_dir.parent / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    (payload_dir / f"{chain.key}.json").write_text(json.dumps(payload))


def track_dataset(
    recordings: list[str],
    source: SessionSource,
    out_dir: Path,
    *,
    min_shift_px: float = MIN_SHIFT_PX,
    tracked_threshold: float = 0.10,
    validate: bool = True,
    viewer_cells: int = 0,
    neucoeff: float = NEUCOEFF,
    completion_radius_px: float = COMPLETION_RADIUS_PX,
    reuse_runs: Path | None = None,
    workers: int = 1,
    threads_per_worker: int = 4,
    cell_type_folders=(),
    progress: ProgressFn | None = None,
) -> dict:
    """Track every multi-DIV chain and write results under ``out_dir``.

    ``workers`` > 1 runs chains in parallel subprocesses. Subprocesses rather
    than threads: ROICaT re-extracts its model into the shared temp directory on
    every run, and torch sizes its thread pools to the whole machine — see
    :mod:`meanap.catnap.tracking.__main__`. A chain whose result is already on
    disk is skipped, so an interrupted run continues where it stopped.
    ``reuse_runs`` points at an earlier run's ``work/runs`` so that chains whose
    gate decision has not changed reuse their ROICaT clusters (see
    :func:`track_chain`). ``cell_type_folders`` are searched for each
    recording's cell-type file, and the tracked cells labelled from them
    (:mod:`meanap.catnap.tracking.celltypes`).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chains = build_chains(recordings)
    if progress:
        progress(f"{len(chains)} chains with 2+ DIVs")

    ordered = sorted(chains.values(), key=lambda c: c.key)
    if workers > 1:
        results = _track_parallel(
            ordered, recordings, source, out_dir,
            min_shift_px=min_shift_px, validate=validate,
            viewer_cells=viewer_cells, neucoeff=neucoeff,
            completion_radius_px=completion_radius_px, reuse_runs=reuse_runs,
            workers=workers, threads_per_worker=threads_per_worker,
            progress=progress)
    else:
        results = _track_serial(
            ordered, source, out_dir, min_shift_px=min_shift_px,
            validate=validate, viewer_cells=viewer_cells, neucoeff=neucoeff,
            completion_radius_px=completion_radius_px, reuse_runs=reuse_runs,
            progress=progress)

    usable = [r for r in results if r.pairwise and r.median_match >= tracked_threshold]
    summary = {
        "chains": len(results),
        "registered": sum(1 for r in results if r.registered),
        "failed": sum(1 for r in results if r.note.startswith("failed")),
        "day_pairs": sum(len(r.pairwise) for r in results),
        "tracked_threshold": tracked_threshold,
        "min_shift_px": min_shift_px,
        "usable_chains": len(usable),
        "usable_by_genotype": {
            g: sum(1 for r in usable if r.genotype == g)
            for g in sorted({r.genotype for r in results if r.genotype})
        },
        # Recovery covaries with prep and prep covaries with genotype, so a
        # group comparison built on tracked cells inherits that. Reported here
        # so the imbalance is visible rather than discovered later.
        "chains_by_genotype": {
            g: sum(1 for r in results if r.genotype == g)
            for g in sorted({r.genotype for r in results if r.genotype})
        },
    }
    aucs = [r.fingerprint_auc for r in results if np.isfinite(r.fingerprint_auc)]
    if aucs:
        summary["median_fingerprint_auc"] = float(np.median(aucs))
    summary["rescued_cell_days"] = sum(len(r.rescued) for r in results)
    rescued_aucs = [r.rescued_fingerprint_auc for r in results
                    if np.isfinite(r.rescued_fingerprint_auc)]
    if rescued_aucs:
        summary["median_rescued_fingerprint_auc"] = float(np.median(rescued_aucs))
    summary["merged_clusters"] = sum(len(r.merged) for r in results)
    merged_aucs = [r.merged_fingerprint_auc for r in results
                   if np.isfinite(r.merged_fingerprint_auc)]
    if merged_aucs:
        summary["median_merged_fingerprint_auc"] = float(np.median(merged_aucs))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    _write_csv(out_dir, results)
    if any(cell_type_folders):
        from meanap.catnap.tracking.celltypes import annotate_tracking_dir

        # payloads from before cell types carry no raw ROI index, so a chain
        # skipped as already done still needs iscell.npy to be labelled
        roots = [getattr(source, "raw_data", None)]
        report = annotate_tracking_dir(out_dir, cell_type_folders,
                                       suite2p_roots=[r for r in roots if r],
                                       log=progress or (lambda _m: None))
        summary["cell_types"] = report.summary()
    return summary


def _track_serial(ordered, source, out_dir, *, min_shift_px, validate,
                  viewer_cells, neucoeff, completion_radius_px, reuse_runs,
                  progress) -> list[ChainResult]:
    results: list[ChainResult] = []
    for i, chain in enumerate(ordered, 1):
        dest = out_dir / "chains" / f"{chain.key}.json"
        if dest.exists():          # resumable: a long run survives interruption
            results.append(ChainResult(**json.loads(dest.read_text())))
            continue
        try:
            res = track_chain(chain, source, out_dir / "work",
                              min_shift_px=min_shift_px, validate=validate,
                              viewer_dir=out_dir / "viewer",
                              viewer_cells=viewer_cells, neucoeff=neucoeff,
                              completion_radius_px=completion_radius_px,
                              reuse_runs=reuse_runs, progress=progress)
        except Exception as exc:               # one bad chain must not end the run
            res = ChainResult(chain=chain.key, divs=chain.divs,
                              genotype=chain.genotype, prep=chain.prep,
                              note=f"failed: {type(exc).__name__}: {exc}")
            if progress:
                progress(f"{chain.key}: FAILED — {type(exc).__name__}: {exc}")
        # a remote source caches each recording it fetched; the chain is done
        # with them now, and holding a whole dataset open would defeat streaming
        release = getattr(source, "release", None)
        if release is not None:
            for rec in chain.recordings:
                try:
                    release(rec.name)
                except Exception:      # releasing is housekeeping, never fatal
                    pass
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(asdict(res), indent=1))
        results.append(res)
        if progress:
            progress(f"[{i}/{len(ordered)}] {chain.key}: median "
                     f"{res.median_match:.3f}")
    return results


def _track_parallel(ordered, recordings, source, out_dir, *, min_shift_px,
                    validate, viewer_cells, neucoeff, completion_radius_px,
                    reuse_runs, workers, threads_per_worker, progress
                    ) -> list[ChainResult]:
    """Run chains in parallel subprocesses, longest first.

    Longest first because cost tracks total ROI count: starting the big chains
    last leaves one straggler running alone at the end of the batch.
    """
    import os
    import shutil
    import subprocess
    import sys
    import tempfile
    from concurrent.futures import ThreadPoolExecutor, as_completed

    raw_data = getattr(source, "raw_data", None)
    if raw_data is None:
        if progress:
            progress("this source cannot be used from a subprocess; running serially")
        return _track_serial(ordered, source, out_dir, min_shift_px=min_shift_px,
                             validate=validate, viewer_cells=viewer_cells,
                             neucoeff=neucoeff,
                             completion_radius_px=completion_radius_px,
                             reuse_runs=reuse_runs, progress=progress)

    todo, results = [], []
    for chain in ordered:
        dest = out_dir / "chains" / f"{chain.key}.json"
        if dest.exists():
            results.append(ChainResult(**json.loads(dest.read_text())))
        else:
            todo.append(chain)
    if not todo:
        return results

    def roi_count(chain) -> int:
        try:
            return sum(len(source.stat(r.name)) for r in chain.recordings)
        except Exception:
            return 0

    todo.sort(key=roi_count, reverse=True)
    (out_dir / "chains").mkdir(parents=True, exist_ok=True)
    spec_dir = out_dir / "work" / "specs"
    spec_dir.mkdir(parents=True, exist_ok=True)

    shared_zip = Path(tempfile.gettempdir()) / "ROInet.zip"
    tmp_root = Path(tempfile.gettempdir()) / "meanap_tracking_tmp"

    env_base = dict(os.environ)
    env_base.update({var: str(threads_per_worker) for var in (
        "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")})
    # A child does not inherit the parent's sys.path, so a meanap imported from
    # a source checkout (rather than installed) is invisible to it. Pass the
    # directory the package actually came from.
    import meanap
    pkg_parent = str(Path(meanap.__file__).resolve().parents[1])
    existing = env_base.get("PYTHONPATH", "")
    if pkg_parent not in existing.split(os.pathsep):
        env_base["PYTHONPATH"] = (f"{pkg_parent}{os.pathsep}{existing}"
                                  if existing else pkg_parent)

    def launch(chain):
        dest = out_dir / "chains" / f"{chain.key}.json"
        spec = spec_dir / f"{chain.key}.json"
        spec.write_text(json.dumps({
            "chain": chain.key,
            "recordings": [r.name for r in ordered_recordings(recordings)],
            "raw_data": str(raw_data),
            "derived_root": str(getattr(source, "derived_root", "") or ""),
            "work_dir": str(out_dir / "work"),
            "viewer_dir": str(out_dir / "viewer"),
            "dest": str(dest),
            "min_shift_px": min_shift_px, "validate": validate,
            "viewer_cells": viewer_cells, "neucoeff": neucoeff,
            "completion_radius_px": completion_radius_px,
            "reuse_runs": str(reuse_runs) if reuse_runs else "",
        }))
        env = dict(env_base)
        tmp = tmp_root / chain.key
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        # a private TMPDIR per chain, with the model symlinked in so no worker
        # re-downloads it and none can overwrite another's extraction
        if shared_zip.exists():
            link = tmp / "ROInet.zip"
            if not link.exists():
                link.symlink_to(shared_zip)
        env["TMPDIR"] = str(tmp)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "meanap.catnap.tracking", "--spec", str(spec)],
                capture_output=True, text=True, timeout=7200, env=env)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return chain, proc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(launch, c): c for c in todo}
        for i, future in enumerate(as_completed(futures), 1):
            chain, proc = future.result()
            dest = out_dir / "chains" / f"{chain.key}.json"
            if proc.returncode == 0 and dest.exists():
                res = ChainResult(**json.loads(dest.read_text()))
            else:
                tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
                res = ChainResult(chain=chain.key, divs=chain.divs,
                                  genotype=chain.genotype, prep=chain.prep,
                                  note=f"failed: {tail[0][:200]}")
                dest.write_text(json.dumps(asdict(res), indent=1))
            results.append(res)
            if progress:
                state = ("median %.3f" % res.median_match if res.pairwise
                         else res.note or "no result")
                progress(f"[{i}/{len(todo)}] {chain.key}: {state}")
    return results


def ordered_recordings(recordings) -> list:
    """The recording names a subprocess needs to rebuild the same chains."""
    from meanap.catnap.tracking.chains import parse_recording

    out = []
    for name in recordings:
        try:
            out.append(parse_recording(name))
        except ValueError:
            continue
    return out


#: Edges kept per day in the stored network. The strongest tenth of a
#: 100-cell network is ~500 edges; past that a picture is a solid block and the
#: payload grows for nothing.
MAX_STORED_EDGES = 500


def _network_summary(result: ChainResult, sessions, labels: list[np.ndarray]) -> None:
    """Per-day-pair edge stability, and the network the viewer draws."""
    for a in range(len(sessions)):
        for b in range(a + 1, len(sessions)):
            st = stability(sessions[a].corr, sessions[b].corr,
                           labels[a], labels[b], sessions[b].centroids,
                           div_gap=result.divs[b] - result.divs[a])
            if st.usable:
                result.network_stability.append({
                    "pair": f"DIV{result.divs[a]}-DIV{result.divs[b]}",
                    "divGap": st.div_gap, "nShared": st.n_shared,
                    "nEdges": st.n_edges,
                    "edgeR": round(float(st.edge_r), 4),
                    "nullR": (None if not np.isfinite(st.null_r)
                              else round(float(st.null_r), 4)),
                })

    # Cells tracked into at least two days. Requiring presence on *every* day
    # is a far stricter bar — it excluded 79 of 92 chains — and it is not the
    # only useful question: a network held over three of five days is still a
    # network. The span is chosen in the viewer, so the payload carries which
    # days each cell appears on and lets the reader draw the line.
    spans = _cluster_spans(labels)
    cells = sorted(c for c, days in spans.items() if len(days) >= 2)
    if len(cells) < MIN_SHARED_CELLS:
        return

    index = [{int(c): i for i, c in enumerate(lab) if c >= 0} for lab in labels]
    # one position per cell, from the first day it appears, so every panel puts
    # the same cell in the same place
    xy = []
    for cluster in cells:
        first = spans[cluster][0]
        xy.append(sessions[first].centroids[index[first][cluster]])
    xy = np.asarray(xy, dtype=float)

    days = []
    for k in range(len(sessions)):
        here = [n for n, c in enumerate(cells) if c in index[k]]
        if len(here) < 2:
            days.append({"div": int(result.divs[k]), "threshold": None,
                         "edges": [], "strength": [], "present": here})
            continue
        rows = [index[k][cells[n]] for n in here]
        sub = subnetwork(sessions[k].corr, rows)
        edges, thr = edges_above(sub, 0.9)
        weights = np.array([sub[i, j] for i, j in edges], dtype=float)
        if len(edges) > MAX_STORED_EDGES:
            keep = np.argsort(weights)[::-1][:MAX_STORED_EDGES]
            edges, weights = edges[keep], weights[keep]
        strength = np.nansum(np.where(np.isfinite(sub), sub, 0.0), axis=1) - 1.0
        # graph measures on the same thresholded network the edges come from,
        # so the picture and the numbers describe one graph
        try:
            measures = node_metrics(sub)
        except Exception as exc:      # recorded, never silently degraded
            measures = {"error": f"{type(exc).__name__}: {exc}"}
        day = {
            "div": int(result.divs[k]),
            "threshold": None if not np.isfinite(thr) else round(float(thr), 4),
            # indices are into `cells`, so the client can filter by span
            "edges": [[int(here[i]), int(here[j]), round(float(w), 3)]
                      for (i, j), w in zip(edges, weights)],
            "strength": {str(here[i]): round(float(v), 3)
                         for i, v in enumerate(strength) if np.isfinite(v)},
            "present": here,
        }
        if "error" not in measures:
            day["metrics"] = {
                name: {str(here[i]): measures[name][i] for i in range(len(here))
                       if measures[name][i] is not None}
                for name in NODE_METRICS}
            day["role"] = {str(here[i]): int(measures["role"][i])
                           for i in range(len(here))}
            day["nModules"] = measures["n_modules"]
            day["modularity"] = measures["modularity"]
        else:
            day["metricsError"] = measures["error"]
        days.append(day)

    result.network_metric_stability = _metric_stability_table(
        days, result.divs)
    result.network = {
        "nShared": sum(1 for c in cells if len(spans[c]) == len(sessions)),
        "nCells": len(cells),
        "nSessions": len(sessions),
        "xy": [[round(float(y), 1), round(float(x), 1)] for y, x in xy],
        # which tracked cell each node is, so labels can be joined to nodes
        "clusters": [int(c) for c in cells],
        # how many days each cell was tracked into — the span filter
        "span": [len(spans[c]) for c in cells],
        "days": days,
    }


def _metric_stability_table(days: list[dict], divs: list[int]) -> list[dict]:
    """Per day-pair: does each node measure, and the role, survive?"""
    out = []
    for a in range(len(days)):
        for b in range(a + 1, len(days)):
            if "metrics" not in days[a] or "metrics" not in days[b]:
                continue
            shared = sorted(set(days[a]["role"]) & set(days[b]["role"]))
            if len(shared) < 5:
                continue
            row = {"pair": f"DIV{divs[a]}-DIV{divs[b]}",
                   "divGap": int(divs[b] - divs[a]), "n": len(shared),
                   "metrics": {}}
            for name in NODE_METRICS:
                va = [days[a]["metrics"][name].get(c) for c in shared]
                vb = [days[b]["metrics"][name].get(c) for c in shared]
                obs = metric_stability(va, vb)
                nul = metric_stability_null(va, vb)
                row["metrics"][name] = {
                    "r": None if not np.isfinite(obs) else round(float(obs), 4),
                    "null": None if not np.isfinite(nul) else round(float(nul), 4)}
            row["role"] = role_stability([days[a]["role"][c] for c in shared],
                                         [days[b]["role"][c] for c in shared])
            out.append(row)
    return out


def _cluster_spans(labels: list[np.ndarray]) -> dict[int, list[int]]:
    """Which sessions each cluster appears in."""
    spans: dict[int, list[int]] = {}
    for k, lab in enumerate(labels):
        for c in lab:
            if c >= 0:
                spans.setdefault(int(c), []).append(k)
    return spans


def _write_csv(out_dir: Path, results: list[ChainResult]) -> None:
    import csv

    with open(out_dir / "tracking_by_chain.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["chain", "genotype", "prep", "div", "n_roi", "frac_tracked",
                    "registered", "measured_shift_px", "n_rescued", "n_merged"])
        for r in results:
            for div, n, f in zip(r.divs, r.n_roi, r.frac_tracked):
                w.writerow([r.chain, r.genotype, r.prep, div, n, f,
                            int(r.registered), round(r.measured_shift_px, 1),
                            sum(1 for x in r.rescued if x["div"] == div),
                            sum(1 for m in r.merged if div in m["divs"])])

    with open(out_dir / "tracking_by_pair.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["chain", "genotype", "prep", "pair", "div_gap", "shared",
                    "shared_roicat", "frac_of_smaller", "registered"])
        for r in results:
            for pair, v in r.pairwise.items():
                w.writerow([r.chain, r.genotype, r.prep, pair, v["div_gap"],
                            v["shared"], v.get("shared_roicat", v["shared"]),
                            v["frac_of_smaller"], int(r.registered)])
