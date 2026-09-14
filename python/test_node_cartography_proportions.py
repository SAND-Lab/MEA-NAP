"""Regression test for grouped node-cartography composition plots.

Run with::

    uv run python -X utf8 python/test_node_cartography_proportions.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from meanap.pipeline.plotting_step4 import (
    _node_cartography_proportion_frame,
    plot_node_cartography_proportions,
    plot_node_cartography_proportions_by_age,
)


def main() -> int:
    # WT DIV14 has two recordings with opposite R1/R2 compositions. Pooling
    # counts (rather than averaging arbitrary percentages) must yield 50/50.
    df = pd.DataFrame({
        "Grp": ["WT", "WT", "KO"],
        "DIV": ["14", "14", "21"],
        "Lag": ["1000mslag", "1000mslag", "1000mslag"],
        "NCpn1count": [8, 2, 1], "NCpn2count": [2, 8, 1],
        "NCpn3count": [0, 0, 1], "NCpn4count": [0, 0, 1],
        "NCpn5count": [0, 0, 1], "NCpn6count": [0, 0, 0],
    })
    pooled = _node_cartography_proportion_frame(df)
    wt = pooled[(pooled["Grp"] == "WT") & (pooled["DIV"] == "14")]
    assert np.isclose(wt["Proportion"].sum(), 1.0)
    assert np.isclose(wt.loc[wt["Role"] == 1, "Proportion"].iloc[0], 0.5)

    with tempfile.TemporaryDirectory() as tmp:
        files = plot_node_cartography_proportions(df, Path(tmp))
        assert len(files) == 1
        assert files[0].name == "NodeCartographyProportions1000mslag.png"
        assert files[0].is_file() and files[0].stat().st_size > 0
        age_files = plot_node_cartography_proportions_by_age(df, Path(tmp))
        assert len(age_files) == 1
        assert age_files[0].name == "NodeCartographyProportionsByAge1000mslag.png"
        assert age_files[0].is_file() and age_files[0].stat().st_size > 0

    print("Node-cartography composition plot: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
