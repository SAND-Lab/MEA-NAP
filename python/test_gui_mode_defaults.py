"""Settings that are shared between the pipelines but want different values.

The Connectivity tab is on screen in all three modes, but the lag values it
holds mean different things in each: an STTC window that is right for spikes
(~10 ms) finds almost nothing in calcium, where a transient lasts on the order
of a second. So the lags follow the mode — while still yielding to anything the
user typed, since they are also the field people most often tune by hand.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.gui.modes import MODES, apply_mode_to_params  # noqa: E402
from meanap.params import Params  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def lags(window: MainWindow) -> str:
    return window._connectivity_panel.lag_vals.text()


EPHYS = ", ".join(str(v) for v in MODES["meanap"].default_lags)
CALCIUM = ", ".join(str(v) for v in MODES["catnap"].default_lags)


# ── The defaults themselves ───────────────────────────────────────────────────

print("\nThe per-mode defaults")

check("CAT-NAP's lags are far longer than the ephys ones",
      min(MODES["catnap"].default_lags) > 10 * max(MODES["meanap"].default_lags),
      f"{MODES['catnap'].default_lags} vs {MODES['meanap'].default_lags}")
check("MEA-Stim runs the ephys pipeline, so it keeps the ephys lags",
      MODES["meastim"].default_lags == MODES["meanap"].default_lags, "")


# ── Switching modes in a running window ───────────────────────────────────────

print("\nSwitching modes")

window = MainWindow("meanap")
check("an MEA-NAP window starts on the ephys lags", lags(window) == EPHYS, lags(window))

window._apply_mode("catnap")
check("switching to CAT-NAP lengthens them", lags(window) == CALCIUM, lags(window))
check("…and a run started right after would use them",
      window._collect_params().func_con_lag_val == list(MODES["catnap"].default_lags),
      str(window._collect_params().func_con_lag_val))
check("…and the window says so rather than changing the field silently",
      "lag" in window.statusBar().currentMessage().lower(),
      window.statusBar().currentMessage())

window._apply_mode("meanap")
check("switching back restores the ephys lags", lags(window) == EPHYS, lags(window))

window._apply_mode("meastim")
check("a mode that shares the defaults leaves the field alone",
      lags(window) == EPHYS, lags(window))


# ── What the user typed always wins ───────────────────────────────────────────

print("\nWhat the user typed")

window._apply_mode("meanap")
window._connectivity_panel.lag_vals.setText("5, 20")
window._apply_mode("catnap")
check("hand-set lags survive the switch", lags(window) == "5, 20", lags(window))

window._connectivity_panel.lag_vals.setText("10, ")  # mid-edit, unparseable
window._apply_mode("meanap")
check("a half-typed field is not rewritten either", lags(window) == "10, ", repr(lags(window)))

params = Params()
params.suite2p_mode = True
params.func_con_lag_val = [750]
window._load_params(params)
check("a loaded parameter file beats the mode default",
      lags(window) == "750" and window._mode == "catnap", lags(window))


# ── Launching straight into a mode ────────────────────────────────────────────

print("\nLaunching in a mode")

catnap_window = MainWindow("catnap")
check("`--mode catnap` opens on the calcium lags",
      lags(catnap_window) == CALCIUM, lags(catnap_window))
check("…in the params too, not just on screen",
      catnap_window._collect_params().func_con_lag_val
      == list(MODES["catnap"].default_lags),
      str(catnap_window._collect_params().func_con_lag_val))


# ── Reset ─────────────────────────────────────────────────────────────────────

print("\nResetting to defaults")

catnap_window._connectivity_panel.lag_vals.setText("42")
# _on_new asks for confirmation, so exercise what it does once confirmed.
reset = Params()
apply_mode_to_params(catnap_window._mode, reset)
reset.func_con_lag_val = list(MODES[catnap_window._mode].default_lags)
catnap_window._load_params(reset)
check("resetting in CAT-NAP stays in CAT-NAP, on its lags",
      catnap_window._mode == "catnap" and lags(catnap_window) == CALCIUM,
      f"{catnap_window._mode} / {lags(catnap_window)}")


# ── The field says what it sets ───────────────────────────────────────────────

print("\nNaming the timescale field")


def field_names(window: MainWindow) -> tuple[str, str]:
    panel = window._connectivity_panel
    return panel._sttc_box.title(), panel._lag_label.text()


fresh = MainWindow("catnap")
fresh._catnap_panel._activity_combo.setCurrentText("peaks")
check("CAT-NAP on peaks computes STTC, so the field is a lag",
      field_names(fresh) == ("Spike time tiling coefficient (STTC)",
                             "Lag values (ms)"), str(field_names(fresh)))

fresh._catnap_panel._activity_combo.setCurrentText("F")
check("switching to a correlation activity relabels it as a bin",
      field_names(fresh) == ("Correlation binning", "Bin length (ms)"),
      str(field_names(fresh)))

fresh._apply_mode("meanap")
check("the ephys pipeline is STTC whatever the 2P activity is set to",
      field_names(fresh) == ("Spike time tiling coefficient (STTC)",
                             "Lag values (ms)"), str(field_names(fresh)))

fresh._apply_mode("catnap")
check("…and switching back restores the bin labelling",
      field_names(fresh) == ("Correlation binning", "Bin length (ms)"),
      str(field_names(fresh)))

corr_params = Params()
corr_params.suite2p_mode = True
corr_params.twop_activity = "spks"
fresh._load_params(corr_params)
check("loading a correlation params file relabels the field too",
      field_names(fresh) == ("Correlation binning", "Bin length (ms)"),
      str(field_names(fresh)))


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All mode-default checks passed.")
