"""Compare the CSV outputs of the MATLAB and Python MEA-NAP test-pipeline runs.

Aligns each pair of CSVs on their key columns, then reports per-column
agreement (max absolute / relative difference, correlation) plus any columns
present in only one of the two runs.

    uv run python parityRun/compare_parity.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
MATLAB_DIR = REPO_ROOT / "parityRun" / "OutputData_MATLAB_parity"
# Which Python run to compare against MATLAB. Pass a folder name as argv[1] to
# compare the "Python steps 2-4 on MATLAB's own spike times" run instead:
#   uv run python parityRun/compare_parity.py OutputData_Python_fromMatlabSpikes
PYTHON_DIR = REPO_ROOT / "parityRun" / (
    sys.argv[1] if len(sys.argv) > 1 else "OutputData_Python_parity"
)

# CSV name -> key columns used to align rows between the two runs
CSVS = {
    "NeuronalActivity_RecordingLevel.csv": ["FileName"],
    "NeuronalActivity_NodeLevel.csv": ["FileName", "Channel"],
    "NetworkActivity_RecordingLevel.csv": ["FileName", "Lag"],
    "NetworkActivity_NodeLevel.csv": ["FileName", "Lag", "Channel"],
}

# Metrics that cannot be bit-reproducible across the two runs because they
# depend on an independently-seeded RNG stream (or, for NMF, a different
# solver entirely). Reported separately rather than counted as failures.
STOCHASTIC = {
    "nMod", "Q", "PL", "CC", "SW", "SWw",
    "PCmean", "PCmeanTop10", "PCmeanBottom10", "PC", "Z",
    "percentZscoreGreaterThanZero", "percentZscoreLessThanZero",
    "NCpn1", "NCpn2", "NCpn3", "NCpn4", "NCpn5", "NCpn6",
    "num_nnmf_components", "nComponentsRelNS",
}

TOL = 1e-6  # relative tolerance for calling a column an exact match


def compare_series(a: pd.Series, b: pd.Series) -> dict:
    """Compare two aligned numeric columns."""
    x = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)

    both_nan = np.isnan(x) & np.isnan(y)
    one_nan = np.isnan(x) ^ np.isnan(y)
    valid = ~np.isnan(x) & ~np.isnan(y)

    res = {
        "n": int(len(x)),
        "n_both_nan": int(both_nan.sum()),
        "n_nan_mismatch": int(one_nan.sum()),
        "n_compared": int(valid.sum()),
    }
    if valid.sum() == 0:
        res.update(max_abs_diff=np.nan, max_rel_diff=np.nan, corr=np.nan,
                   matlab_mean=np.nan, python_mean=np.nan)
        return res

    xv, yv = x[valid], y[valid]
    abs_diff = np.abs(xv - yv)
    denom = np.maximum(np.abs(xv), np.abs(yv))
    rel_diff = np.where(denom > 0, abs_diff / np.where(denom > 0, denom, 1.0), 0.0)

    if xv.size > 1 and np.std(xv) > 0 and np.std(yv) > 0:
        corr = float(np.corrcoef(xv, yv)[0, 1])
    else:
        corr = np.nan

    res.update(
        max_abs_diff=float(abs_diff.max()),
        max_rel_diff=float(rel_diff.max()),
        corr=corr,
        matlab_mean=float(xv.mean()),
        python_mean=float(yv.mean()),
    )
    return res


# MATLAB's step-4 saveNetMet.m writes NetworkActivity_*.csv with
# FileName/Grp/DIV/Channel columns, but step 4B's combineExpNetworkData.m then
# OVERWRITES the same two filenames with its own group-level schema, which is
# what actually survives on disk. The Python port implements saveNetMet.m's
# schema only, so rename MATLAB's surviving columns back to compare like for like.
MATLAB_COLUMN_ALIASES = {
    "recordingName": "FileName",
    "eGrp": "Grp",
    "AgeDiv": "DIV",
    "activeChannel": "Channel",
}


def find_csv(root: Path, name: str) -> Path:
    """Locate a CSV under an output tree.

    MATLAB writes all four CSVs to the output root; the Python port writes
    them inside the per-step folders (2_NeuronalActivity/, 4_NetworkActivity/),
    so fall back to a recursive search.
    """
    direct = root / name
    if direct.exists():
        return direct
    matches = sorted(root.rglob(name))
    return matches[0] if matches else direct


def normalise_lag(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce the Lag column to a plain number.

    MATLAB writes Lag as numeric ms (10); the Python port writes the adjacency
    field name instead ("10mslag"), so the two can only be joined after
    stripping the suffix.
    """
    if "Lag" in df.columns:
        df = df.copy()
        df["Lag"] = (df["Lag"].astype(str)
                     .str.replace("mslag", "", regex=False)
                     .str.strip())
        df["Lag"] = pd.to_numeric(df["Lag"], errors="coerce")
    return df


def align(ml: pd.DataFrame, py: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Align two frames on `keys`; fall back to row order if keys don't match."""
    usable = [k for k in keys if k in ml.columns and k in py.columns]
    if usable:
        ml_k = ml.set_index(usable).sort_index()
        py_k = py.set_index(usable).sort_index()
        common = ml_k.index.intersection(py_k.index)
        if len(common) > 0:
            return ml_k.loc[common], py_k.loc[common], f"keys={usable} ({len(common)} rows)"

    n = min(len(ml), len(py))
    return ml.iloc[:n], py.iloc[:n], f"ROW ORDER fallback ({n} rows) — key columns did not intersect"


def main() -> None:
    report: dict = {}

    for csv_name, keys in CSVS.items():
        ml_path, py_path = find_csv(MATLAB_DIR, csv_name), find_csv(PYTHON_DIR, csv_name)
        print("=" * 78)
        print(csv_name)
        print("=" * 78)

        if not ml_path.exists() or not py_path.exists():
            missing = [str(p.relative_to(REPO_ROOT)) for p in (ml_path, py_path) if not p.exists()]
            print(f"  MISSING: {missing}\n")
            report[csv_name] = {"error": f"missing: {missing}"}
            continue

        ml = pd.read_csv(ml_path).rename(columns=MATLAB_COLUMN_ALIASES)
        ml, py = normalise_lag(ml), normalise_lag(pd.read_csv(py_path))
        print(f"  MATLAB: {ml.shape[0]} rows x {ml.shape[1]} cols")
        print(f"  Python: {py.shape[0]} rows x {py.shape[1]} cols")

        ml_a, py_a, how = align(ml, py, keys)
        print(f"  Aligned on {how}")

        ml_only = [c for c in ml.columns if c not in py.columns]
        py_only = [c for c in py.columns if c not in ml.columns]
        if ml_only:
            print(f"  Columns only in MATLAB: {ml_only}")
        if py_only:
            print(f"  Columns only in Python: {py_only}")

        shared = [c for c in ml_a.columns if c in py_a.columns]
        rows = []
        for col in shared:
            if not (pd.api.types.is_numeric_dtype(ml_a[col]) or pd.api.types.is_numeric_dtype(py_a[col])):
                continue
            r = compare_series(ml_a[col], py_a[col])
            r["column"] = col
            r["stochastic"] = col in STOCHASTIC
            rows.append(r)

        if rows:
            df = pd.DataFrame(rows).set_index("column")
            print()
            print(df[["n_compared", "n_nan_mismatch", "matlab_mean", "python_mean",
                      "max_abs_diff", "max_rel_diff", "corr", "stochastic"]]
                  .to_string(float_format=lambda v: f"{v:.6g}"))

            exact = [r["column"] for r in rows
                     if not np.isnan(r.get("max_rel_diff", np.nan)) and r["max_rel_diff"] <= TOL
                     and r["n_nan_mismatch"] == 0]
            print(f"\n  Exact match (rel diff <= {TOL:g}, no NaN mismatch): "
                  f"{len(exact)}/{len(rows)} numeric columns")

        report[csv_name] = {
            "matlab_shape": list(ml.shape),
            "python_shape": list(py.shape),
            "alignment": how,
            "matlab_only_columns": ml_only,
            "python_only_columns": py_only,
            "columns": rows,
        }
        print()

    out = REPO_ROOT / "parityRun" / f"parity_comparison_{PYTHON_DIR.name}.json"
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2, default=float)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
