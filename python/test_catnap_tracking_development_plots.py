"""Cell types across development: type logic, chain-level summaries, statistics.

The statistics tests guard two decisions that are easy to undo by accident:

* means are means of chain means, not of cells;
* the mixed model gives each chain its own slope. Without one, a chain that
  happens to hold more of one type passes its trajectory to that type.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from meanap.catnap.tracking import development_plots as dp


def _calls(**cols) -> pd.DataFrame:
    return pd.DataFrame({f"celltype_{m}": v for m, v in cols.items()})


# ── types ─────────────────────────────────────────────────────────────────────

def test_kleene_logic_keeps_unknown_unknown():
    calls = _calls(PV=["+", "-", "+", ""], GAD=["", "", "-", ""], NeuN=["+", "+", "+", "+"])
    markers = ["GAD", "NeuN", "PV"]
    # a PV+ cell is inhibitory whatever its GAD; a PV- cell with unknown GAD is not known
    assert dp.evaluate("PV+ | GAD+", calls, markers).tolist() == [1, 0.5, 1, 0.5]
    # excitatory needs GAD known negative: unknown is never read as negative
    assert dp.evaluate("NeuN+ & ~GAD+", calls, markers).tolist() == [0.5, 0.5, 1, 0.5]


def test_spreadsheet_spellings_resolve():
    calls = _calls(NeuN=["+", "-", ""])
    for expr in ("NeuN_Positive", "NeuN Positive", "NeuN+"):
        assert dp.evaluate(expr, calls, ["NeuN"]).tolist() == [1, 0, 0.5]
    assert dp.evaluate("NeuN_Negative", calls, ["NeuN"]).tolist() == [0, 1, 0.5]


def test_definitions_per_marker_and_from_the_run():
    names = [d.name for d in dp.type_definitions(["GAD", "NeuN"], "E/I")]
    assert names == ["GAD", "NeuN", "ExcitatoryInhibitory"]
    custom = dp.type_definitions(["NeuN"], {"A": "NeuN+", "B": "NeuN-"})[-1]
    assert custom.name == "CellTypeGroups" and custom.types == {"A": "NeuN+", "B": "NeuN-"}


def test_types_too_small_to_compare_are_dropped():
    n = dp.MIN_TYPE_CELLS
    df = pd.DataFrame({"chain": "c", "cluster": range(n + 1),
                       "celltype_M": ["+"] * n + ["-"]})
    assert dp.typed(df, dp.type_definitions(["M"])[0]).empty


# ── summaries ─────────────────────────────────────────────────────────────────

def test_mean_is_of_chain_means_not_cells():
    df = pd.DataFrame({"Grp": "g", "CellType": "T", "DIV": 10,
                       "chain": ["a"] * 10 + ["b"], "metric": [1.0] * 10 + [3.0]})
    row = dp.chain_means(df, "metric").iloc[0]
    assert row["mean"] == 2.0 and row["nChains"] == 2


def test_slope_is_per_week_on_recorded_age():
    df = pd.DataFrame({"chain": "a", "cluster": 1, "Grp": "g", "CellType": "T",
                       "DIVrecorded": [7, 14, 21], "m": [1.0, 2.0, np.nan]})
    s = dp.cell_slopes(df, "m")
    assert s["slopePerWeek"].iloc[0] == pytest.approx(1.0) and s["nDays"].iloc[0] == 2


def test_dropping_out_of_the_network_is_a_transition():
    df = pd.DataFrame({"chain": "a", "cluster": 1, "Grp": "g", "CellType": "T",
                       "DIVrecorded": [7, 14, 21], "NdCartDiv": [6.0, np.nan, 1.0]})
    t = dp.role_transitions(df).query("n > 0")
    pairs = set(zip(t["from"].astype(str), t["to"].astype(str)))
    assert pairs == {("Kinless hub", "inactive"), ("inactive", "Peripheral")}


# ── statistics ────────────────────────────────────────────────────────────────

def _development(seed: int, type_effect: float, chain_slope_sd: float,
                 unbalanced: bool) -> pd.DataFrame:
    """Chains of cells over four weekly days; ``type_effect`` per week for B."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(12):
        chain_slope = rng.normal(0, chain_slope_sd)
        share_b = (0.85 if c % 2 else 0.15) if unbalanced else 0.5
        # unbalanced: chains rich in B also develop faster, by construction
        if unbalanced:
            chain_slope = abs(chain_slope) * (1 if c % 2 else -1)
        for k in range(12):
            ct = "B" if rng.random() < share_b else "A"
            base = rng.normal(0, 1)
            for w, div in enumerate((7, 14, 21, 28)):
                slope = chain_slope + (type_effect if ct == "B" else 0)
                rows.append({"chain": f"c{c}", "cluster": k, "Grp": "g", "CellType": ct,
                             "DIVrecorded": div, "DIV": div,
                             "m": base + slope * w + rng.normal(0, 0.3)})
    return pd.DataFrame(rows)


def _term(rows, name):
    return next(r for r in rows if r["term"] == name)


def test_mixed_model_recovers_a_real_type_by_age_effect():
    rows = dp.mixed_model_rows(_development(1, 0.8, 0.3, False), "m", ["A", "B"])
    t = _term(rows, "age:type=B")
    assert t["estimate"] == pytest.approx(0.8, abs=0.15) and t["p"] < 1e-4
    assert t["converged"]


def test_chain_trajectories_do_not_become_a_type_effect():
    """No type effect at all, but B-rich chains develop faster."""
    rows = dp.mixed_model_rows(_development(2, 0.0, 1.0, True), "m", ["A", "B"])
    assert _term(rows, "age:type=B")["p"] > 0.01


def test_groups_without_every_type_are_left_out_and_said_so():
    df = pd.concat([_development(3, 0.0, 0.3, False),
                    _development(4, 0.0, 0.3, False).assign(Grp="only A", CellType="A",
                                                            chain=lambda d: d.chain + "x")])
    rows = dp.mixed_model_rows(df, "m", ["A", "B"])
    assert rows[0]["groupsFitted"] == "g"
    assert "only A has no B cells" in rows[0]["note"]


def test_within_chain_difference_has_the_right_sign():
    df = _development(5, 0.8, 0.3, False)
    slopes = pd.concat([dp.cell_slopes(df, "m")])
    rows = dp.within_chain_rows(df, "m", ["A", "B"], slopes)
    slope = next(r for r in rows if r["measure"] == "slope" and r["Grp"] == "all")
    assert slope["comparison"] == "A - B" and slope["nChains"] == 12
    # B gains 0.8 per *recording step*, which here is a week
    assert slope["medianDiff"] == pytest.approx(-0.8, abs=0.2) and slope["p"] < 0.01


# ── end to end ────────────────────────────────────────────────────────────────

def test_plot_development_writes_figures_and_tables(tmp_path):
    df = _development(6, 0.5, 0.3, False)
    df = df.assign(celltype_M=np.where(df["CellType"] == "B", "-", "+"),
                   Lag="1000mslag", NdCartDiv=np.where(df["m"] > 0, 6.0, np.nan),
                   FR=df["m"], ND=df["m"] * 2).drop(columns=["CellType", "m"])
    out = dp.plot_development(df, tmp_path, ["FR"], max_workers=1)
    assert set(out) == {"slopes", "mixed", "within"}
    root = tmp_path / "M"
    assert (root / "Activity" / "1_Trajectories" / "FR.png").is_file()
    assert (root / "Activity" / "2_ChangePerCell" / "FR.png").is_file()
    net = root / "Network" / "Lag1000ms"
    assert (net / "1_Trajectories" / "ND.png").is_file()
    assert (net / "3_RoleTransitions.png").is_file()
    # activity metrics are not repeated under the network block, nor the reverse
    assert not (net / "1_Trajectories" / "FR.png").exists()
    assert not (root / "Activity" / "1_Trajectories" / "ND.png").exists()
    for name in ("CellSlopes.csv", "Stats_MixedModel.csv", "Stats_WithinChain.csv"):
        assert (tmp_path / name).is_file()
    mixed = out["mixed"]
    assert set(mixed["metric"]) == {"FR", "ND"} and mixed["converged"].all()
    assert mixed["q"].notna().all() and (mixed["q"] >= mixed["p"]).all()


def test_fdr_is_within_one_question_across_metrics():
    t = pd.DataFrame({"definition": "M", "block": "Activity",
                      "term": ["x", "x", "x", "y"], "metric": ["a", "b", "c", "a"],
                      "p": [0.01, 0.02, np.nan, 0.01]})
    q = dp.add_fdr(t, ["term"])["q"].tolist()
    # term x: two p's, BH gives 0.02 and 0.02; the missing p gets no q
    assert q[0] == pytest.approx(0.02) and q[1] == pytest.approx(0.02)
    assert np.isnan(q[2])
    # term y is its own family of one, so it is not penalised by x
    assert q[3] == pytest.approx(0.01)
