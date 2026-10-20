"""Every new import / event-stim / stim-network field survives a GUI round trip.

``MainWindow._collect_params`` starts from a fresh ``Params()``, so a field
with no widget is silently reset on every GUI run. This loads non-default
values for each field this feature added and checks they come back.

    QT_QPA_PLATFORM=offscreen .venv/bin/python python/test_gui_sorted_import_params.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.params import Params  # noqa: E402

NON_DEFAULT = dict(
    spike_source="import", sorted_data_folder="/data/sorted",
    sorted_data_format="phy", sorted_drop_labels=["noise", "mua"],
    channel_layout="FromFile",
    stimulation_mode=True, stim_detection_method="maxwellTTL",
    stim_events_folder="/data/events", stim_event_ttl_rule="fall:7",
    stim_event_min_interval=0.2, stim_event_condition_mode="alternate",
    stim_event_condition_labels=["ON", "OFF"],
    stim_network=False, stim_network_window=[0.05, 0.75],
    stim_network_null="circular", stim_network_rep_num=321, stim_network_alpha=0.01,
)


def test_new_fields_round_trip() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow("meanap")
    # stimulation_mode switches the window to MEA-Stim, as loading a file would.
    window._load_params(Params(**NON_DEFAULT))
    got = window._collect_params()
    bad = {k: (getattr(got, k), v) for k, v in NON_DEFAULT.items() if getattr(got, k) != v}
    assert not bad, bad
    window.close()
    del app


if __name__ == "__main__":
    test_new_fields_round_trip()
    print("OK")
