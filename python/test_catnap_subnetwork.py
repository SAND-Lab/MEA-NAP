"""Test the CAT-NAP cell-type subnetwork analysis.

Run from the repo root::

    uv run python python/test_catnap_subnetwork.py

This feature has **no MATLAB counterpart** (MATLAB only draws cell types as
rings on the network plot), so unlike the other ``test_pipeline_*`` scripts
there is no parity ground truth. Instead these are correctness and
self-consistency checks:

  - group expressions parse and evaluate with the right precedence;
  - the marker membership matrix matches the source spreadsheet row-for-row;
  - induced subgraphs really are the ``adjM`` restricted to their nodes, and
    the metrics come out of the *shared* step-4 routine;
  - edge-mix blocks partition every edge of the network exactly once;
  - the long-format node table accounts for every active node, including
    nodes with overlapping memberships.

Section A runs on synthetic data and always executes. Section B runs against
the real example dataset in the gitignored ``local/`` folder and **skips
gracefully** when it is absent (so this is a no-op in CI).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.catnap import subnetwork as sn  # noqa: E402
from meanap.params import Params  # noqa: E402

DATASET_DIR = REPO_ROOT / "local" / "example2pdataWCellTypes"
RECORDING = "OPME230825_1_20230915_P1_pup4A_Het_MOI50000_DIV21"
CELLTYPE_CSV = DATASET_DIR / RECORDING / f"PutativeCellType_{RECORDING}_PositiveOnly.csv"
SUITE2P_DIR = DATASET_DIR / RECORDING / "suite2p" / "plane0"
EXPDATA_MAT = (DATASET_DIR / "OutputData22May2026" / "ExperimentMatFiles"
               / f"{RECORDING}_OutputData22May2026.mat")

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


# ── Section A: synthetic ──────────────────────────────────────────────────────

def _toy_table() -> pd.DataFrame:
    """8 ROIs (0-indexed ids 0-7) with deliberately overlapping markers.

    NeuN+ : 0 1 2 3 4 5      GAD+ : 4 5      PV+ : 5 6      Mecp2+ : 0 6
    So ROI 5 is NeuN+/GAD+/PV+ (triple), ROI 6 is PV+ but not NeuN+, and
    ROI 7 belongs to nothing.
    """
    return pd.DataFrame({
        "NeuN+": pd.Series([0, 1, 2, 3, 4, 5], dtype=float),
        "GAD+": pd.Series([4, 5], dtype=float),
        "PV+": pd.Series([5, 6], dtype=float),
        "Mecp2+": pd.Series([0, 6], dtype=float),
    })


def _expression_checks() -> list[Check]:
    channels = np.arange(1, 9)  # 1-indexed ROI numbers 1..8 ↔ ids 0..7
    matrix, names = sn.build_marker_matrix(_toy_table(), channels)
    checks: list[Check] = []

    def ev(expr):
        return sn.eval_group_expression(expr, matrix, names)

    checks.append(("marker matrix shape (8, 4)", matrix.shape == (8, 4),
                   str(matrix.shape)))
    checks.append(("NeuN+ membership = ids 0-5",
                   np.array_equal(np.nonzero(matrix[:, names.index("NeuN+")])[0],
                                  np.arange(6)), ""))

    cases = [
        ("GAD+", [4, 5]),
        ("GAD+ | PV+", [4, 5, 6]),
        ("GAD+ & PV+", [5]),
        ("~GAD+", [0, 1, 2, 3, 6, 7]),
        ("NeuN+ & ~GAD+", [0, 1, 2, 3]),
        # & binds tighter than |, so this is GAD+ OR (PV+ AND Mecp2+) = {4,5,6}
        ("GAD+ | PV+ & Mecp2+", [4, 5, 6]),
        # parentheses override that: (GAD+ OR PV+) AND Mecp2+ = {6}
        ("(GAD+ | PV+) & Mecp2+", [6]),
        ("NeuN+ & ~GAD+ & ~PV+", [0, 1, 2, 3]),
        ("!GAD+ & !PV+ & !Mecp2+", [1, 2, 3, 7]),   # ! alias for ~
        ("gad+", [4, 5]),                            # case-insensitive fallback
    ]
    for expr, expected in cases:
        got = np.nonzero(ev(expr))[0].tolist()
        checks.append((f"expr {expr!r} → {expected}", got == expected, f"got {got}"))

    for bad in ["GAD+ &", "(GAD+", "GAD+ | Foo+", "", "GAD+ PV+ )"]:
        try:
            ev(bad)
            ok, detail = False, "no error raised"
        except sn.GroupExpressionError as e:
            ok, detail = True, str(e)
        checks.append((f"invalid expr {bad!r} rejected", ok, detail))

    ei = sn.default_ei_groups(names)
    checks.append(("default_ei_groups builds E/I from present markers",
                   ei is not None and set(ei) == {"Excitatory", "Inhibitory"}, str(ei)))
    checks.append(("default_ei_groups → None with no inhibitory marker",
                   sn.default_ei_groups(["NeuN+", "Mecp2+"]) is None, ""))

    groups = sn.resolve_groups(_toy_table(), channels, "E/I")
    exc = np.nonzero(groups.masks[:, groups.names.index("Excitatory")])[0].tolist()
    inh = np.nonzero(groups.masks[:, groups.names.index("Inhibitory")])[0].tolist()
    checks.append(("E/I preset: excitatory = NeuN+ minus GAD+/PV+",
                   exc == [0, 1, 2, 3], f"got {exc}"))
    checks.append(("E/I preset: inhibitory = GAD+ ∪ PV+", inh == [4, 5, 6], f"got {inh}"))

    default = sn.resolve_groups(_toy_table(), channels, None)
    checks.append(("default grouping = one per spreadsheet column",
                   default.names == names, str(default.names)))

    empty = sn.resolve_groups(_toy_table(), channels, {"Nobody": "GAD+ & Mecp2+",
                                                      "Some": "GAD+"})
    checks.append(("empty groups dropped, others kept",
                   empty.names == ["Some"], str(empty.names)))
    return checks


def _structure_checks() -> list[Check]:
    """Induced subgraph / edge-mix / node-split invariants on a random graph."""
    rng = np.random.default_rng(0)
    channels = np.arange(1, 9)
    groups = sn.resolve_groups(_toy_table(), channels, "E/I")

    adj = rng.random((8, 8))
    adj = (adj + adj.T) / 2
    adj[adj < 0.45] = 0.0          # make it sparse
    np.fill_diagonal(adj, 0.0)

    checks: list[Check] = []

    # Induced subgraph == adjM restricted to the group's nodes.
    idx = groups.indices("Inhibitory")
    expected = adj[np.ix_(idx, idx)]
    params = Params(min_activity_level=0.0, exclude_edges_below_threshold=True)
    results = sn.compute_subnetwork_metrics(
        adj, np.full(8, 100.0), 10.0, groups, params, min_nodes=2, rng=rng,
    )
    inh = results["Inhibitory"]
    got_nodes = inh["subnetworkNodeIndex"]
    checks.append(("induced subgraph node set matches group mask",
                   np.array_equal(got_nodes, idx), f"{got_nodes} vs {idx}"))
    sub = inh.get("adjMsub")
    active = inh["activeChannelIndex"]
    checks.append(("induced subgraph weights == adjM[group, group]",
                   sub is not None and np.allclose(sub, expected[np.ix_(active, active)]), ""))
    checks.append(("fullNetworkIndex maps back into the whole network",
                   np.array_equal(inh["fullNetworkIndex"], idx[active]), ""))
    checks.append(("node degree computed on the subgraph, not the full net",
                   "ND" in inh and len(inh["ND"]) == inh["aN"], ""))

    # Edge mix: every above-zero upper-triangle edge lands in exactly one block
    # when the groups are disjoint (E/I is, by construction).
    disjoint = not (groups.masks[:, 0] & groups.masks[:, 1]).any()
    mix = sn.compute_edge_mix(adj, groups)
    iu = np.triu_indices(8, k=1)
    assigned = groups.masks.any(axis=1)
    counted = int(mix["nEdges"].sum())
    # Only edges whose BOTH endpoints are in some group can appear in a block.
    both = np.outer(assigned, assigned)
    truth = int(((adj[iu] > 0) & both[iu]).sum())
    checks.append(("E/I groups are disjoint", disjoint, ""))
    checks.append(("edge-mix blocks partition the edges exactly once",
                   counted == truth, f"{counted} vs {truth}"))
    n_possible = int(mix["nPossible"].sum())
    n_exp = int((both[iu]).sum())
    checks.append(("edge-mix nPossible == possible pairs among grouped nodes",
                   n_possible == n_exp, f"{n_possible} vs {n_exp}"))

    # Within-group strength fraction is a proper fraction.
    frac = sn.within_group_strength_fraction(adj, groups)
    all_frac = np.concatenate([v[np.isfinite(v)] for v in frac.values()])
    checks.append(("within-group strength fraction ∈ [0, 1]",
                   bool(((all_frac >= 0) & (all_frac <= 1)).all()), ""))

    # Node split: long format, every active node represented, overlaps duplicated.
    full = results[sn.WHOLE_NETWORK] if sn.WHOLE_NETWORK in results else None
    from meanap.pipeline.step4 import compute_network_metrics
    full = compute_network_metrics(adj, np.full(8, 100.0), 10.0, 0.0, 2,
                                   params=params, rng=rng)
    node_df = sn.split_node_metrics(full, groups, channels, adj_m=adj)
    active_full = np.asarray(full["activeChannelIndex"])
    covered = set(node_df["NodeIndex"])
    checks.append(("every active node appears in the node table",
                   covered == set(active_full.tolist()),
                   f"{sorted(covered)} vs {sorted(active_full.tolist())}"))
    checks.append(("node table is long format (Group column present)",
                   "Group" in node_df.columns, str(list(node_df.columns)[:4])))
    unassigned = node_df.loc[node_df["Group"] == "Unassigned", "NodeIndex"].tolist()
    checks.append(("ungrouped node 7 lands in 'Unassigned'",
                   7 in unassigned or 7 not in active_full, str(unassigned)))

    # Overlapping groups must duplicate the node, one row per membership.
    overlap = sn.resolve_groups(_toy_table(), channels,
                                {"GAD": "GAD+", "PV": "PV+"})
    odf = sn.split_node_metrics(full, overlap, channels, adj_m=adj)
    node5 = odf[odf["NodeIndex"] == 5]
    checks.append(("node in two groups yields two rows",
                   set(node5["Group"]) == {"GAD", "PV"}, str(list(node5["Group"]))))

    summary = pd.DataFrame(sn.subnetwork_summary_rows(results))
    checks.append(("summary has one row per group (+ whole network)",
                   set(summary["Group"]) == {"Excitatory", "Inhibitory"},
                   str(list(summary["Group"]))))
    checks.append(("summary collapses node arrays to *_mean scalars",
                   "ND_mean" in summary.columns
                   and summary["ND_mean"].map(np.isscalar).all(), ""))
    return checks


# ── Section B: real dataset ───────────────────────────────────────────────────

def _dataset_checks() -> list[Check]:
    import scipy.io as sio

    checks: list[Check] = []
    table = sn.load_cell_type_table(CELLTYPE_CSV)
    checks.append(("cell-type CSV loads with 5 marker columns",
                   list(table.columns) == ["NeuN+", "Mecp2+", "PV+", "SST+", "GAD+"],
                   str(list(table.columns))))

    # The PositiveOnly *xlsx* has prose in the "NeuN-" style columns; the loader
    # must drop them rather than emitting a marker with no ids.
    xlsx = DATASET_DIR / f"PutativeCellType_{RECORDING}_PositiveOnly.xlsx"
    if xlsx.exists():
        x_table = sn.load_cell_type_table(xlsx)
        checks.append(("xlsx prose-only columns dropped",
                       list(x_table.columns) == ["NeuN+", "Mecp2+", "PV+", "SST+", "GAD+"],
                       str(list(x_table.columns))))

    mat = sio.loadmat(EXPDATA_MAT, struct_as_record=False, squeeze_me=True)
    channels = np.asarray(mat["channels"]).ravel()
    adj = np.asarray(mat["adjMs"].adjM1000mslag, dtype=float)

    groups = sn.resolve_groups(table, channels, None)
    counts = groups.counts()
    checks.append(("per-column groups resolve on the real recording",
                   set(groups.names) == set(table.columns), str(groups.names)))
    # Cross-check one marker by hand: how many of its ROI ids survived the
    # iscell + no-peaks filtering into `channels`.
    gad_ids = table["GAD+"].dropna().to_numpy(dtype=int) + 1
    expected_gad = int(np.isin(gad_ids, channels).sum())
    checks.append((f"GAD+ count matches CSV∩channels ({expected_gad})",
                   counts.get("GAD+") == expected_gad,
                   f"{counts.get('GAD+')} vs {expected_gad}"))

    ei = sn.resolve_groups(table, channels, "E/I")
    exc = ei.masks[:, ei.names.index("Excitatory")]
    inh = ei.masks[:, ei.names.index("Inhibitory")]
    checks.append(("E/I split is non-empty on the real recording",
                   exc.sum() > 0 and inh.sum() > 0,
                   f"E={int(exc.sum())} I={int(inh.sum())}"))
    checks.append(("E and I are disjoint", not (exc & inh).any(), ""))
    print(f"      (E={int(exc.sum())} cells, I={int(inh.sum())} cells, "
          f"ungrouped={int((~ei.masks.any(axis=1)).sum())} of {len(channels)})")

    mix = sn.compute_edge_mix(adj, ei)
    checks.append(("edge mix has 3 blocks for 2 groups (E-E, E-I, I-I)",
                   len(mix) == 3, str(len(mix))))
    within = mix[mix["Kind"] == "within"]["Density"].to_numpy()
    between = mix[mix["Kind"] == "between"]["Density"].to_numpy()
    checks.append(("all densities are finite fractions",
                   bool(np.all((within >= 0) & (within <= 1))
                        and np.all((between >= 0) & (between <= 1))), ""))
    print("      edge-mix densities: "
          + ", ".join(f"{r.GroupA}-{r.GroupB}={r.Density:.3f}" for r in mix.itertuples()))
    return checks


def main() -> int:
    print("=" * 70)
    print("CAT-NAP cell-type subnetwork analysis")
    print("=" * 70)

    total_pass = total = 0
    # Built lazily so each section's report prints before the next one runs.
    for title, build in [
        ("Section A1 — group expressions:", _expression_checks),
        ("Section A2 — subgraph / edge-mix / node-split structure:", _structure_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    if CELLTYPE_CSV.exists() and EXPDATA_MAT.exists():
        p, n = _report("Section B — real example dataset:", _dataset_checks())
        total_pass += p
        total += n
    else:
        print(f"\nSection B — SKIPPED (dataset not found at {DATASET_DIR})")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
