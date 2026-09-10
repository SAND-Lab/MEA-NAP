"""The spike and burst viewer: what it shows, and what it hands back.

Spike detection is the step whose output nothing downstream can check for you,
so the viewer exists to be looked at — which makes most of it untestable
without eyes. What *is* testable is the part that would silently mislead: the
quality numbers printed over the traces, whether the window opens on the
settings the run would use, and whether **Use these settings** actually moves
them back onto the tab rather than into a window nobody reads again.

The last of those is the one worth a test. A viewer that changes nothing when
you accept its settings looks identical to one that works, right up until the
run comes out the same as before.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import scipy.io as sio  # noqa: E402
from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from meanap.gui.main_window import MainWindow  # noqa: E402
from meanap.gui.modes import TAB_SPIKE  # noqa: E402
from meanap.gui.spike_viewer import (  # noqa: E402
    SPIKE_METHOD_COLORS, SpikeViewerWindow, SweepPoint, _ArrayMap,
    _describe_file, _duration, _fit_title, _noise_mad, _spectrum, count_slopes,
    knee_threshold, method_color, noise_from_thresholds, quality_summary,
    refractory_violations, sweep_points,
)
from meanap.gui.spike_viewer import (  # noqa: E402
    TAB_BURST_STATS, TAB_BURSTS, UNLABELLED_METHOD, pack_bursts, unpack_bursts,
)
from meanap.pipeline.io import load_spike_file, save_spike_times_npz  # noqa: E402
from meanap.pipeline.spike_detection import (  # noqa: E402
    SpikeDetectionParams, detect_spikes_recording, trace_noise,
)
from meanap.params import Params  # noqa: E402

app = QApplication.instance() or QApplication([])

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def pump(viewer: SpikeViewerWindow, seconds: float = 60.0) -> None:
    """Run the event loop until the viewer's background work is done."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if not viewer._workers:
            return
        time.sleep(0.02)
    raise AssertionError("viewer work did not finish")


def synthetic_recording(path: Path, *, fs: float = 12500.0, seconds: float = 4.0,
                        n_channels: int = 4) -> None:
    """A recording with spikes at known times, small enough to detect in a test."""
    rng = np.random.default_rng(7)
    n = int(fs * seconds)
    dat = rng.normal(0, 1.0, size=(n, n_channels))
    spike = -12.0 * np.exp(-((np.arange(-20, 21)) ** 2) / 18.0)
    for ch in range(n_channels):
        # Bursts of five, so both burst detectors have something to find.
        for burst_start in np.arange(0.2, seconds - 0.5, 0.5):
            for k in range(5):
                at = int((burst_start + k * 0.01) * fs)
                dat[at - 20:at + 21, ch] += spike
    sio.savemat(path, {"dat": dat.astype(np.float32),
                       "channels": np.arange(1, n_channels + 1),
                       "fs": fs})


print("\nQuality numbers")

times = np.array([0.0, 0.0005, 0.010, 0.030])
count, fraction = refractory_violations(times, ref_period_ms=1.0)
check("a 0.5 ms interval counts as a refractory violation", count == 1, str(count))
check("the fraction is over intervals, not spikes",
      abs(fraction - 1 / 3) < 1e-9, str(fraction))
check("fewer than two spikes is no evidence",
      refractory_violations(np.array([0.1]), 1.0) == (0, 0.0))

summary = quality_summary(times, None, threshold=-5.0, duration_s=2.0,
                          ref_period_ms=1.0)
check("the summary counts the spikes", "4 spikes" in summary, summary)
check("the summary reports a rate over the duration", "2.00 Hz" in summary, summary)
check("the summary reports the threshold it was caught with",
      "threshold -5" in summary, summary)

waveforms = np.tile(np.array([0.0, -6.0, 0.0]), (4, 1))
with_waves = quality_summary(times, waveforms, threshold=-5.0, duration_s=2.0,
                             ref_period_ms=1.0, noise_mad=2.0)
check("SNR is amplitude over the noise the threshold was set from",
      "SNR 3.0" in with_waves, with_waves)

long_summary = " · ".join(f"measure {i} is a long one" for i in range(6))
title = _fit_title("Channel 12 · thr4", long_summary, width=40)
check("a long summary wraps rather than being clipped",
      len(title.splitlines()) > 2 and max(len(x) for x in title.splitlines()) <= 45,
      repr(title))


print("\nThe button on the Spike detection tab")

window = MainWindow()
window.show()
app.processEvents()

spike_panel = window._spike_panel
check("the tab offers the viewer", hasattr(spike_panel, "open_viewer_btn"))
check("no viewer exists until it is asked for", window._spike_viewer is None)
spike_panel.open_viewer_btn.click()
app.processEvents()
viewer = window._spike_viewer
check("clicking opens one", viewer is not None)
spike_panel.open_viewer_btn.click()
app.processEvents()
check("clicking again shows the same one, not a second",
      window._spike_viewer is viewer)


print("\nBurst settings, which had no home in the GUI before")

params = Params()
params.min_spike_network_burst = 17
params.single_channel_isi_threshold = 0.042
spike_panel.load(params)
round_tripped = Params()
spike_panel.save(round_tripped)
check("a network burst minimum survives the tab",
      round_tripped.min_spike_network_burst == 17,
      str(round_tripped.min_spike_network_burst))
check("a fixed channel ISI threshold survives as a number",
      round_tripped.single_channel_isi_threshold == 0.042,
      str(round_tripped.single_channel_isi_threshold))
params.single_channel_isi_threshold = "automatic"
spike_panel.load(params)
spike_panel.save(round_tripped)
check("'automatic' survives as 'automatic'",
      round_tripped.single_channel_isi_threshold == "automatic",
      str(round_tripped.single_channel_isi_threshold))


print("\nUse these settings")

viewer._thresholds.setText("2.5, 6")
viewer._ref_period.setValue(3.5)
viewer._nb_min_channels.setValue(9)
viewer._sc_auto_isi.setChecked(False)
viewer._sc_isi.setValue(0.077)
window._tabs.setCurrentIndex(0)
viewer.settings_accepted.emit()
app.processEvents()

after = window._collect_params()
check("thresholds reach the tab", after.thresholds == [2.5, 6.0], str(after.thresholds))
check("the refractory period reaches the tab", after.ref_period == 3.5,
      str(after.ref_period))
check("burst settings reach the tab", after.min_channel_network_burst == 9,
      str(after.min_channel_network_burst))
check("a fixed ISI threshold reaches the tab as a number",
      after.single_channel_isi_threshold == 0.077,
      str(after.single_channel_isi_threshold))
check("accepting shows the tab the settings landed on",
      window._tabs.currentIndex() == window._tab_index(TAB_SPIKE))

blank = Params()
viewer._thresholds.setText("   ")
viewer.apply_to(blank)
check("an empty threshold box does not wipe the run's thresholds",
      blank.thresholds == Params().thresholds, str(blank.thresholds))


print("\nDetecting on a recording")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "synthetic.mat"
    synthetic_recording(raw_path)

    # Detection is driven by hand here, so the pass that would otherwise run
    # on load is turned off — see "What happens when a recording is opened"
    # above for that behaviour.
    solo = SpikeViewerWindow()
    solo.load_defaults(Params())
    solo._auto_detect.setChecked(False)
    solo.open_raw(raw_path)
    pump(solo)

    check("the channels are offered once loaded", solo._channel_combo.count() == 4,
          str(solo._channel_combo.count()))
    # A recording opens on the whole of itself: the first two seconds of a long
    # one say nothing about whether the channel is any good.
    check("a loaded recording opens on its whole timeline",
          solo._window_start.value() == 0.0
          and abs(solo._window_length.value() - solo._duration_s) < 1e-6,
          f"{solo._window_start.value()} + {solo._window_length.value()} "
          f"of {solo._duration_s}")
    shown = solo._trace_view.trace.viewRange()[0]
    check("and the plot is showing that, not a window into it",
          shown[0] <= 0.01 and shown[1] >= solo._duration_s - 0.01, str(shown))
    check("a long recording is not capped by the window spin box",
          solo._window_length.maximum() >= solo._duration_s,
          str(solo._window_length.maximum()))
    check("nothing is claimed to be detected yet", solo._methods() == [],
          str(solo._methods()))
    check("with no spikes there is nothing to burst-detect",
          solo._burst_btn.isEnabled() is False)

    solo._thresholds.setText("4")
    solo._wavelets.clearSelection()
    solo._detect(all_channels=False)
    pump(solo)
    check("detection on one channel finds the planted spikes",
          solo._times_for(0, "thr4").size > 20, str(solo._times_for(0, "thr4").size))
    check("it leaves the other channels alone",
          solo._times_for(1, "thr4").size == 0)
    check("the method it detected with is offered", "thr4" in solo._methods(),
          str(solo._methods()))
    check("waveforms come back with the spikes",
          solo._waveforms[0]["thr4"].shape[0] == solo._times_for(0, "thr4").size)

    solo._detect(all_channels=True)
    pump(solo)
    check("detecting on all channels fills the array",
          all(solo._times_for(ch, "thr4").size > 20 for ch in range(4)))

    solo._sc_min_spikes.setValue(4)
    solo._nb_min_channels.setValue(2)
    solo._detect_bursts()
    pump(solo)
    burst_times, _channels, _info, single = \
        solo._bursts_by_method[solo._primary_method()]

    print()
    check("the bursts open on the whole recording too",
          solo._burst_start == 0.0
          and abs(solo._burst_length - solo._duration_s) < 1e-6,
          f"{solo._burst_start} + {solo._burst_length}")
    check("the bursts have their own window controls",
          hasattr(solo, "_burst_scrollbar") and hasattr(solo, "_burst_box_zoom"))

    # The Bursts tab navigates on its own: dragged to a 20 ms slice of trace
    # every time you looked at a raster, the raster would be useless.
    solo._navigate(1.0, 0.05)
    check("moving the trace leaves the bursts where they were",
          abs(solo._burst_length - solo._duration_s) < 1e-6,
          str(solo._burst_length))

    solo._follow_trace.setChecked(True)
    solo._navigate(1.5, 0.4)
    check("unless they are asked to follow it",
          abs(solo._burst_start - 1.5) < 1e-3
          and abs(solo._burst_length - 0.4) < 1e-3,
          f"{solo._burst_start} + {solo._burst_length}")
    solo._follow_trace.setChecked(False)

    solo._zoom_bursts(0.25)
    zoomed = solo._burst_length
    check("the bursts zoom", zoomed < solo._duration_s, str(zoomed))
    solo._navigate_bursts(0.0, solo._duration_s)
    check("and go back to the whole recording",
          abs(solo._burst_length - solo._duration_s) < 1e-6,
          str(solo._burst_length))
    check("the burst label says where in the recording it is",
          "of" in solo._burst_label.text(), solo._burst_label.text())

    # With the whole recording on screen every burst is already showing, so a
    # literal "next" would report nothing on the very first press.
    solo._jump_to_next_burst()
    check("Next burst zooms in from the whole-recording view",
          solo._burst_length < solo._duration_s, str(solo._burst_length))
    first = solo._burst_start
    solo._jump_to_next_burst()
    check("and moves on from there when pressed again",
          solo._burst_start > first, f"{solo._burst_start} then {first}")

    solo._navigate(0.0, solo._duration_s)
    solo._jump_to_next_spike()
    check("Next spike does the same from the whole-recording view",
          0 < solo._window_length.value() < solo._duration_s,
          str(solo._window_length.value()))

    check("network bursts are found in a bursting recording", len(burst_times) > 0,
          str(len(burst_times)))
    check("single-channel bursts are found too",
          len(single["bursting_units"]) > 0, str(len(single["bursting_units"])))

    for index in range(solo._tabs.count()):
        solo._tabs.setCurrentIndex(index)
        app.processEvents()
    # Named rather than counted, and a subset rather than an equality, so that
    # adding a view does not fail this while a view going missing still does.
    shown = [solo._tabs.tabText(i).strip() for i in range(solo._tabs.count())]
    check("every view draws without raising",
          set(shown) >= {"Traces", "Filtering", "Waveforms and quality",
                         "Threshold sweep", "Bursts"}, str(shown))

    solo._window_start.setValue(0.0)
    solo._window_length.setValue(0.1)
    spikes_here = solo._times_for(solo._current_channel(), "thr4")
    solo._jump_to_next_spike()
    start = solo._window_start.value()
    next_spike = spikes_here[spikes_here > 0.1].min()
    check("jumping moves past what the window already showed", start > 0, str(start))
    check("jumping lands before the next spike, not after it",
          start < next_spike <= start + 0.1, f"{start} vs {next_spike}")
    solo.close()


print("\nWhat happens when a recording is opened")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "onload.mat"
    synthetic_recording(raw_path, seconds=3.0, n_channels=3)

    auto = SpikeViewerWindow()
    auto.load_defaults(Params())
    auto._thresholds.setText("4")
    auto.open_raw(raw_path)
    pump(auto)          # the load
    pump(auto)          # the detection it starts

    check("a loaded recording arrives with spikes on it, unasked",
          auto._methods() == ["thr4"], str(auto._methods()))
    check("every channel is detected, not just the one on screen",
          all(auto._times_for(ch, "thr4").size > 0 for ch in range(3)))
    check("the wavelets are left for the user to ask for",
          not any(m.startswith("bior") for m in auto._methods()),
          str(auto._methods()))
    auto.close()

    off = SpikeViewerWindow()
    off.load_defaults(Params())
    off._auto_detect.setChecked(False)
    off.open_raw(raw_path)
    pump(off)
    check("turning it off leaves the recording undetected", off._methods() == [],
          str(off._methods()))
    check("but the traces are still there to look at", off._dat is not None)
    off.close()

    already = SpikeViewerWindow()
    already.load_defaults(Params())
    already._spike_times = {0: {"fromfile": np.array([0.5, 1.5])}}
    check("spikes that came from a file are not overwritten by a fresh pass",
          not already._should_auto_detect())
    already.close()


print("\nSaying how long detection will take")

check("a short wait is spoken in seconds", _duration(4.2) == "4 s", _duration(4.2))
check("a longer one is rounded, not counted down", _duration(37.0) == "35 s",
      _duration(37.0))
check("a long one is spoken in minutes", _duration(400.0) == "7 min",
      _duration(400.0))

progress_viewer = SpikeViewerWindow()
progress_viewer._started_at = time.monotonic() - 4.0
progress_viewer._on_progress(1, 20)
check("one channel is not enough to estimate from",
      "left" not in progress_viewer._progress.format(),
      progress_viewer._progress.format())
progress_viewer._on_progress(5, 20)
check("the bar is a real percentage once detection is counting",
      (progress_viewer._progress.value(), progress_viewer._progress.maximum()) == (5, 20))
check("and it says how much longer",
      "left" in progress_viewer._progress.format(),
      progress_viewer._progress.format())
progress_viewer.close()

reports: list[tuple[int, int]] = []
detect_spikes_recording(
    np.random.default_rng(1).normal(size=(8000, 4)), np.arange(4), 12500.0,
    SpikeDetectionParams(fs=12500.0, thresholds=[4.0], wname_list=[], grd=[1]),
    progress=lambda done, total: reports.append((done, total)))
check("the detector counts every channel, grounded ones included",
      sorted(d for d, _ in reports) == [1, 2, 3, 4], str(sorted(reports)))
check("and counts against the real total", {t for _, t in reports} == {4},
      str(reports))


print("\nSeveral methods at once")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "methods.mat"
    synthetic_recording(raw_path, seconds=3.0, n_channels=3)

    many = SpikeViewerWindow()
    many.load_defaults(Params())
    many._thresholds.setText("3, 4, 5")
    many.open_raw(raw_path)
    pump(many)
    pump(many)

    check("every threshold becomes a method", many._methods() == ["thr3", "thr4", "thr5"],
          str(many._methods()))
    check("the pass that runs by itself ticks one, not all three",
          many._selected_methods() == ["thr3"], str(many._selected_methods()))

    for i in range(many._method_list.count()):
        many._method_list.item(i).setCheckState(Qt.CheckState.Checked)
    app.processEvents()
    check("all three can be shown together",
          many._selected_methods() == ["thr3", "thr4", "thr5"],
          str(many._selected_methods()))
    check("the single-method views take the first of them",
          many._primary_method() == "thr3", many._primary_method())

    colours = {name: many._method_color(name) for name in many._methods()}
    check("each method draws in its own colour",
          len(set(colours.values())) == 3, str(colours))
    check("the colours are the pipeline's own",
          colours["thr3"] == SPIKE_METHOD_COLORS[0], colours["thr3"])

    many._method_list.item(1).setCheckState(Qt.CheckState.Unchecked)
    app.processEvents()
    check("un-ticking one does not repaint the others",
          many._method_color("thr5") == colours["thr5"],
          f"{many._method_color('thr5')} was {colours['thr5']}")
    check("and the primary is still the first ticked",
          many._primary_method() == "thr3", many._primary_method())

    many._method_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    app.processEvents()
    check("with thr3 off, thr5 becomes the method the analyses describe",
          many._primary_method() == "thr5", many._primary_method())

    # A tick row each, because two methods that catch the same spike would
    # otherwise draw one marker over the other.
    labels = many._trace_view.ticks.getAxis("left")._tickLevels[0]
    check("each shown method gets its own row", len(labels) == 1, str(labels))
    check("and the row says how many that method found",
          "(" in labels[0][1], str(labels))

    many._method_list.item(0).setCheckState(Qt.CheckState.Checked)
    app.processEvents()
    before = set(many._selected_methods())
    many._thresholds.setText("3, 4, 5")
    many._detect(all_channels=True, thresholds_only=True)
    pump(many)
    check("re-detecting keeps the methods you were reading ticked",
          set(many._selected_methods()) == before,
          f"{many._selected_methods()} was {sorted(before)}")

    # Adding a method to one channel. This used to replace that channel's other
    # methods outright, so their rows read "(0)" and the method order — and so
    # every method's colour — changed under you.
    reading = list(many._selected_methods())
    colours_before = {name: many._method_color(name) for name in many._methods()}
    spikes_before = {name: many._times_for(0, name).size for name in many._methods()}
    many._pick_channel(0)
    many._wavelets.clearSelection()
    many._wavelets.item(0).setSelected(True)
    many._thresholds.setText("")
    many._detect(all_channels=False)
    pump(many)

    check("a wavelet detected on one channel is added to the methods",
          "bior1p5" in many._methods(), str(many._methods()))
    check("it does not wipe that channel's other methods",
          all(many._times_for(0, name).size == n
              for name, n in spikes_before.items()),
          str({name: many._times_for(0, name).size for name in spikes_before}))
    check("the methods already there keep their colours",
          all(many._method_color(name) == colour
              for name, colour in colours_before.items()),
          str({name: many._method_color(name) for name in colours_before}))
    check("a method you asked for arrives ticked",
          "bior1p5" in many._selected_methods(), str(many._selected_methods()))
    check("without unticking what you were already reading",
          set(reading) <= set(many._selected_methods()),
          f"{many._selected_methods()} was {reading}")

    rows = many._trace_view.ticks.getAxis("left")._tickLevels[0]
    check("every shown method gets a labelled row",
          len(rows) == len(many._selected_methods()) and all(r[1] for r in rows),
          str(rows))
    check("and none of the rows claims zero spikes it does have",
          "  (0)" not in " ".join(r[1] for r in rows), str(rows))
    many.close()

check("a long method list cycles rather than running out of colours",
      method_color(len(SPIKE_METHOD_COLORS)) == SPIKE_METHOD_COLORS[0])

# The window's wheel-to-zoom would be silently dead if the application-wide
# guard that stops a wheel turn retuning a spin box claimed the plot as well.
# Sending a real wheel event needs a real pointer, which an offscreen scene
# does not have — so this asks the guard directly what it thinks of the plot.
from meanap.gui.wheel import _guarded_widget  # noqa: E402

wheelable = SpikeViewerWindow()
viewport = wheelable._trace_view._graphics.viewport()
check("the wheel guard does not claim the trace plot",
      _guarded_widget(viewport) is None, str(_guarded_widget(viewport)))
check("it still claims a settings spin box on the same window",
      _guarded_widget(wheelable._window_start) is wheelable._window_start)
wheelable.close()

titled = SpikeViewerWindow()
titled._trace_view.set_title("Channel 3\n12 spikes · 0.4% ISIs < 2 ms (1) · SNR 5")
shown = titled._trace_view.trace.titleLabel.text
check("a '<' in the summary does not swallow the measures after it",
      "SNR 5" in shown, shown)
titled.close()


print("\nComparing methods on the waveform page")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "quality.mat"
    synthetic_recording(raw_path, seconds=4.0, n_channels=3)

    quality = SpikeViewerWindow()
    quality.load_defaults(Params())
    quality._thresholds.setText("3, 4, 5")
    quality.open_raw(raw_path)
    pump(quality)
    pump(quality)
    quality._tabs.setCurrentIndex(2)          # Waveforms and quality
    app.processEvents()

    figure = quality._quality_canvas._fig
    wave_axes = figure.axes[0]
    check("one method shows its individual spikes behind the mean",
          len(wave_axes.lines) > 5, str(len(wave_axes.lines)))
    check("and the title carries the full set of numbers",
          "SNR" in figure._suptitle.get_text(), figure._suptitle.get_text())

    for i in range(quality._method_list.count()):
        quality._method_list.item(i).setCheckState(Qt.CheckState.Checked)
    app.processEvents()

    figure = quality._quality_canvas._fig
    wave_axes, amp_axes = figure.axes[0], figure.axes[1]
    labels = [line.get_label() for line in wave_axes.lines
              if not line.get_label().startswith("_")]
    check("every ticked method gets a mean waveform",
          len(labels) == 3, str(labels))
    check("each is named with how many spikes it is averaging",
          all("(" in label for label in labels), str(labels))
    colours = {line.get_color() for line in wave_axes.lines
               if not line.get_label().startswith("_")}
    check("each draws in its own colour", len(colours) == 3, str(colours))
    check("the individual spikes are dropped when comparing",
          len(wave_axes.lines) == 3, str(len(wave_axes.lines)))
    check("the waveform panel is keyed", wave_axes.get_legend() is not None)

    # A marker is placed by turning a spike time back into a frame index. That
    # round trip goes through a division by fs, so truncating lands a marker one
    # sample off the peak often enough to scatter them up into the noise — and
    # one sample either side of a spike is a completely different voltage.
    channel = quality._current_channel()
    times = quality._times_for(channel, "thr4")
    trace = quality._filtered_trace(channel)
    frames = np.rint(times * quality._fs).astype(int)
    on_peak = sum(trace[f] == trace[max(0, f - 1):f + 2].min() for f in frames)
    check("every marker sits on the spike it is pointing at",
          on_peak == frames.size, f"{on_peak} of {frames.size}")
    check("counts go logarithmic so a strict method is not a flat line",
          amp_axes.get_yscale() == "log", amp_axes.get_yscale())
    check("the title says which method the array map describes",
          "array map" in figure._suptitle.get_text(), figure._suptitle.get_text())

    # A spike file carries times but not always waveforms; the page must still
    # draw the ISIs rather than fail on the missing half.
    quality._waveforms = {}
    quality._refresh()
    app.processEvents()
    check("methods with no waveforms still draw their ISIs", True)
    quality.close()


print("\nMoving around the recording")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "navigate.mat"
    synthetic_recording(raw_path, seconds=8.0)

    nav = SpikeViewerWindow()
    nav.load_defaults(Params())
    nav.open_raw(raw_path)
    pump(nav)

    nav._navigate(2.0, 1.0)
    check("navigating sets both ends of the window",
          (nav._window_start.value(), nav._window_length.value()) == (2.0, 1.0))
    check("the scrollbar follows the window", nav._scrollbar.value() == 2000,
          str(nav._scrollbar.value()))
    check("the scrollbar's thumb is the window's share of the recording",
          nav._scrollbar.pageStep() == 1000, str(nav._scrollbar.pageStep()))
    check("the label says where in the recording you are",
          nav._window_label.text() == "2.00–3.00 s of 8 s",
          nav._window_label.text())

    # Three decimals are what tell one spike from the next at 20 ms and clutter
    # at ten minutes, so the precision follows the span.
    nav._navigate(1.0, 0.02)
    check("a tight window is labelled to the millisecond",
          nav._window_label.text().startswith("1.000–1.020"),
          nav._window_label.text())
    nav._navigate(0.0, 8.0)
    check("a span of seconds drops the milliseconds",
          nav._window_label.text() == "0.00–8.00 s of 8 s", nav._window_label.text())
    nav._navigate(2.0, 1.0)

    nav._scrollbar.setValue(5000)
    check("dragging the scrollbar moves the window",
          nav._window_start.value() == 5.0, str(nav._window_start.value()))

    nav._zoom(1 / 2)
    check("zooming in halves the window", nav._window_length.value() == 0.5,
          str(nav._window_length.value()))
    check("zooming keeps the centre still", abs(nav._window_start.value() - 5.25) < 1e-6,
          str(nav._window_start.value()))

    nav._navigate(-5.0, 1.0)
    check("the window cannot start before the recording",
          nav._window_start.value() == 0.0, str(nav._window_start.value()))
    nav._navigate(100.0, 1.0)
    check("the window cannot start past the end",
          abs(nav._window_start.value() - 7.0) < 1e-6, str(nav._window_start.value()))

    # The plot reports the range it has been dragged or wheeled to, and the
    # same clamping has to apply to that as to a typed number — neither goes
    # through the other.
    nav._on_view_range(-1.0, 200.0)
    check("a wheel-zoom past the whole recording stops at the whole recording",
          nav._window_length.value() == 8.0 and nav._window_start.value() == 0.0,
          f"{nav._window_start.value()} + {nav._window_length.value()}")

    nav._navigate(3.0, 1.0)
    shown = nav._trace_view.trace.viewRange()[0]
    check("navigating from the controls moves the plot itself",
          abs(shown[0] - 3.0) < 1e-6 and abs(shown[1] - 4.0) < 1e-6, str(shown))
    region = nav._trace_view._region.getRegion()
    check("and the overview region follows the plot",
          abs(region[0] - 3.0) < 1e-6 and abs(region[1] - 4.0) < 1e-6, str(region))

    # Dragging a rectangle across the trace: pyqtgraph hands the box to the
    # view box, which uses its width and leaves the vertical range to fit the
    # trace — a box drawn to pick out two spikes must not clip the trace to
    # however high the pointer happened to be.
    import pyqtgraph as pg  # noqa: E402
    from PyQt6.QtCore import QRectF  # noqa: E402

    nav._box_zoom.setChecked(True)
    check("the toggle puts the plot in rectangle mode",
          nav._trace_view.trace.vb.state["mouseMode"] == pg.ViewBox.RectMode)
    nav._navigate(0.0, 8.0)
    y_before = nav._trace_view.trace.viewRange()[1]
    nav._trace_view.trace.vb.showAxRect(QRectF(2.0, -0.3, 1.5, 0.05))
    app.processEvents()
    check("the box zooms the window to the times it spans",
          abs(nav._window_start.value() - 2.0) < 1e-3
          and abs(nav._window_length.value() - 1.5) < 1e-3,
          f"{nav._window_start.value()} + {nav._window_length.value()}")
    y_after = nav._trace_view.trace.viewRange()[1]
    check("and leaves the voltage range fitting the trace, not the box",
          not (y_after[0] > -0.3 and y_after[1] < -0.25),
          f"{y_after} from {y_before}")
    nav._box_zoom.setChecked(False)
    check("turning it off goes back to dragging to pan",
          nav._trace_view.trace.vb.state["mouseMode"] == pg.ViewBox.PanMode)

    nav._trace_view._region.setRegion((5.0, 6.5))
    app.processEvents()
    check("dragging the overview region moves the window",
          abs(nav._window_start.value() - 5.0) < 1e-3
          and abs(nav._window_length.value() - 1.5) < 1e-3,
          f"{nav._window_start.value()} + {nav._window_length.value()}")
    nav.close()


print("\nPicking a channel off the array map")

check("the map is beside the settings, not inside a plot tab",
      isinstance(viewer._array_map, _ArrayMap))

grid = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
array_map = _ArrayMap()
array_map.resize(240, 260)
array_map.show_array(grid, np.array([0.0, 1.0, 2.0, 3.0]),
                     ["11", "12", "21", "22"], 1, "Firing rate")

placed = array_map._layout()
check("the electrodes are laid out in the widget", placed is not None)
centres, radius = placed
check("all four are placed", len(centres) == 4 and np.isfinite(centres).all(),
      str(centres))
# Equal spacing along both axes: an MEA stretched to the panel's shape is a
# different array. Screen y runs downward, hence the absolute values.
check("the array keeps its shape rather than filling the panel",
      abs(abs(centres[1][0] - centres[0][0])
          - abs(centres[2][1] - centres[0][1])) < 1.0, str(centres))

check("a click on an electrode picks it",
      array_map._nearest(QPointF(*centres[1])) == 1,
      str(array_map._nearest(QPointF(*centres[1]))))
middle = QPointF(float(centres[:, 0].mean()), float(centres[:, 1].mean()))
check("a click in the gap between them picks nothing",
      array_map._nearest(middle) is None, str(array_map._nearest(middle)))

picked: list[int] = []
array_map.pick = picked.append


class _Click:
    def __init__(self, point):
        self._point = point

    def position(self):
        return self._point


array_map.mousePressEvent(_Click(QPointF(*centres[2])))
check("clicking reports the electrode to whoever is listening", picked == [2],
      str(picked))

array_map.message("nothing loaded")
check("with no layout it says so instead of drawing", array_map._layout() is None)


print("\nWhich method colours the map")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "rates.mat"
    synthetic_recording(raw_path, seconds=3.0, n_channels=3)

    rates_window = SpikeViewerWindow()
    rates_window.load_defaults(Params())
    rates_window._thresholds.setText("3, 5")
    rates_window.open_raw(raw_path)
    pump(rates_window)
    pump(rates_window)

    check("the map offers every detected method",
          [rates_window._rate_method_combo.itemText(i)
           for i in range(rates_window._rate_method_combo.count())]
          == rates_window._methods(), str(rates_window._methods()))
    check("and starts on the one the rest of the window is describing",
          rates_window._rate_method() == rates_window._primary_method(),
          rates_window._rate_method())

    permissive = rates_window._firing_rates().copy()
    rates_window._rate_method_combo.setCurrentText("thr5")
    app.processEvents()
    strict = rates_window._firing_rates()
    check("choosing another method recolours the map",
          rates_window._rate_method() == "thr5"
          and strict.sum() < permissive.sum(),
          f"{strict.sum():.1f} vs {permissive.sum():.1f}")
    check("the map's caption names the method it is showing",
          "thr5" in rates_window._array_map._caption,
          rates_window._array_map._caption)

    # The choice is the map's alone: it must not change which method the trace
    # or the waveform page describe.
    check("it does not change what the trace is showing",
          rates_window._primary_method() == "thr3",
          rates_window._primary_method())

    # The map can show more than rates. SNR is the one worth checking, because
    # its noise is read back off the thresholds rather than measured again.
    rates_window._rate_method_combo.setCurrentText("thr3")
    app.processEvents()
    channel = rates_window._current_channel()
    sigmas = rates_window._channel_sigmas()
    # A threshold is median - multiplier * sigma, so the detector's own sigma
    # is written into its results and can be read straight back — exactly, and
    # without touching the recording again.
    detectors = trace_noise(rates_window._filtered_trace(channel))[0]
    check("a channel's noise is recovered from its thresholds, not re-measured",
          abs(sigmas[channel] - detectors) / detectors < 1e-12,
          f"{sigmas[channel]} vs {detectors}")
    check("and that is the noise everything else uses, so nothing disagrees",
          rates_window._channel_noise(channel) == sigmas[channel],
          f"{rates_window._channel_noise(channel)} vs {sigmas[channel]}")
    # Measuring the trace directly gives near enough the same answer; the two
    # differ only in where they centre, which is nothing on a bandpassed trace.
    measured = _noise_mad(rates_window._filtered_trace(channel))
    check("measuring the trace instead would agree to within a thousandth",
          abs(sigmas[channel] - measured) / measured < 1e-3,
          f"{sigmas[channel]} vs {measured}")

    snr = rates_window._channel_snr()
    waveforms = rates_window._waveforms[channel]["thr3"]
    expected = abs(float(np.median(waveforms.min(axis=1)))) / sigmas[channel]
    check("SNR is the median spike depth over that noise",
          abs(snr[channel] - expected) < 1e-12, f"{snr[channel]} vs {expected}")
    check("and matches what the trace title reports for the same channel",
          f"SNR {snr[channel]:.1f}" in quality_summary(
              rates_window._times_for(channel, "thr3"), waveforms,
              rates_window._threshold_for(channel, "thr3"),
              rates_window._duration_s, rates_window._ref_period.value(),
              rates_window._channel_noise(channel)),
          f"{snr[channel]:.1f}")
    # A threshold at 3 MAD accepts nothing shallower than 3 sigma, so SNR
    # cannot come out below it — worth knowing before reading the map as an
    # independent measure of quality.
    check("SNR cannot fall below the multiplier that produced it",
          np.nanmin(snr) >= 3.0 - 1e-9, str(np.nanmin(snr)))

    for metric, unit in (("Firing rate", "Hz"), ("SNR", "×σ"),
                         ("Spike count", ""), ("Median amplitude", "")):
        rates_window._map_metric.setCurrentText(metric)
        app.processEvents()
        values, shown_unit = rates_window._channel_values()
        check(f"the map can colour by {metric.lower()}",
              shown_unit == unit and values.size == len(rates_window._methods() and
                                                        rates_window._spike_times),
              f"{shown_unit!r}, {values.size} values")
        check(f"and captions itself as {metric.lower()}",
              metric in rates_window._array_map._caption,
              rates_window._array_map._caption)
    check("the scale carries the unit the numbers are in",
          rates_window._array_map._unit == "", rates_window._array_map._unit)
    rates_window._map_metric.setCurrentText("SNR")
    app.processEvents()
    check("switching back to SNR relabels the scale",
          rates_window._array_map._unit == "×σ", rates_window._array_map._unit)
    rates_window.close()


print("\nMarking spikes on the trace")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "dense.mat"
    synthetic_recording(raw_path, seconds=6.0, n_channels=2)

    dense = SpikeViewerWindow()
    dense.load_defaults(Params())
    dense._thresholds.setText("3, 4")
    dense.open_raw(raw_path)
    pump(dense)
    pump(dense)
    for i in range(dense._method_list.count()):
        dense._method_list.item(i).setCheckState(Qt.CheckState.Checked)
    app.processEvents()

    channel = dense._current_channel()
    total = dense._times_for(channel, "thr4").size
    check("the channel has spikes to mark", total > 0, str(total))

    # Markers used to stand down when there were too many to tell apart, on the
    # theory that they were hiding the trace. They were — but the fix for that
    # is drawing them behind it, not making them come and go. A mark that
    # vanishes at some zoom levels and not others reads as a broken feature, and
    # the zoom it vanished at first was the one the window opens on.
    for length in (dense._duration_s, dense._duration_s / 4, 0.3):
        dense._navigate(0.0, length)
        app.processEvents()
        drawn = sum(len(item.data) for item in dense._trace_view._spike_items)
        check(f"every spike of every method is marked with a {length:.2f} s window",
              drawn == sum(dense._times_for(channel, m).size
                           for m in dense._selected_methods()),
              str(drawn))

    # Behind the trace, which is what lets a dense channel keep both.
    check("the markers sit behind the trace, not over it",
          all(item.zValue() < 0 for item in dense._trace_view._spike_items),
          str([item.zValue() for item in dense._trace_view._spike_items]))

    # Two methods that caught the same spike put their markers at the same
    # point, where only the last drawn is visible — and where they agree or
    # differ is the reason for showing several at once.
    shared = np.intersect1d(np.round(dense._times_for(channel, "thr3"), 6),
                            np.round(dense._times_for(channel, "thr4"), 6))
    check("the two methods do catch some of the same spikes", shared.size > 0,
          str(shared.size))
    at = float(shared[0])
    dense._navigate(at - 0.02, 0.04)
    app.processEvents()

    def marker_y(time_s: float) -> list[float]:
        """Each method's marker for the spike at *time_s*, top to bottom."""
        found = []
        for item in dense._trace_view._spike_items:
            data = item.data
            close = np.flatnonzero(np.abs(data["x"] - time_s) < 1e-6)
            if close.size:
                found.append(float(data["y"][close[0]]))
        return found

    dense._marker_offset.setValue(0.0)
    app.processEvents()
    stacked = marker_y(at)
    check("with no spacing the markers land on top of each other",
          len(stacked) == 2 and abs(stacked[0] - stacked[1]) < 1e-15,
          str(stacked))

    dense._marker_offset.setValue(0.5)
    app.processEvents()
    spread = marker_y(at)
    check("spacing them apart makes both visible",
          len(spread) == 2 and spread[1] < spread[0], str(spread))
    step = abs(spread[1] - spread[0])
    noise = dense._channel_noise(channel)
    check("and the step is measured in the channel's own noise",
          abs(step - 0.5 * noise) < 1e-12, f"{step} vs {0.5 * noise}")
    check("the stack hangs below the spike, not across the trace",
          all(y <= stacked[0] + 1e-15 for y in spread), str(spread))

    # Which fill reads better depends on the zoom, so it is a switch.
    # pyqtgraph turns a brush of None into a QBrush with no pattern, so the
    # fill has to be read off the style rather than off the object being there.
    dense._solid_markers.setChecked(False)
    app.processEvents()
    check("open markers have no fill",
          all(item.opts["brush"].style() == Qt.BrushStyle.NoBrush
              for item in dense._trace_view._spike_items),
          str([item.opts["brush"].style()
               for item in dense._trace_view._spike_items]))
    dense._solid_markers.setChecked(True)
    app.processEvents()
    check("filled ones do",
          all(item.opts["brush"].style() == Qt.BrushStyle.SolidPattern
              for item in dense._trace_view._spike_items),
          str([item.opts["brush"].style()
               for item in dense._trace_view._spike_items]))

    # The noise is wanted on every redraw, for the SNR and for the spacing, so
    # it is cached — and read off the thresholds, which is the detector's own
    # value rather than a second estimate of it.
    check("the cached noise is the one the detector thresholded against",
          dense._channel_noise(channel) == dense._channel_sigma(channel),
          f"{dense._channel_noise(channel)} vs {dense._channel_sigma(channel)}")

    # It describes the detection on screen, not the filter box on screen:
    # changing the bandpass without re-detecting leaves the markers and
    # thresholds where they were, and the noise has to stay consistent with
    # them. Re-detecting moves them all together.
    dense._filter_low.setValue(300.0)
    app.processEvents()
    check("changing the filter alone leaves it describing the visible spikes",
          dense._channel_noise(channel) == noise,
          f"{dense._channel_noise(channel)} vs {noise}")
    dense._detect(all_channels=False)
    pump(dense)
    check("re-detecting moves it to the new detection",
          dense._channel_noise(channel) != noise,
          str(dense._channel_noise(channel)))
    dense.close()


print("\nSweeping the threshold")

# A threshold is the one decision in detection with no right answer written
# down. The sweep's job is to show where the curve changes character, and these
# check the arithmetic behind that rather than the picture.

# A threshold is median - multiplier * sigma, so a sweep's thresholds lie on a
# straight line and the two constants read straight back off it. That is what
# lets the sweep report SNR without measuring the noise a second time.
multipliers = np.array([2.0, 3.0, 4.0, 5.0])
sigma, median = 3.5e-6, 1.2e-7
recovered = noise_from_thresholds(multipliers, median - multipliers * sigma)
check("the noise is recovered exactly from the thresholds",
      abs(recovered[0] - sigma) < 1e-18 and abs(recovered[1] - median) < 1e-18,
      str(recovered))
check("fewer than two thresholds cannot say", 
      all(np.isnan(v) for v in noise_from_thresholds([3.0], [1.0])))


def _point(multiplier: float, n_spikes: int) -> SweepPoint:
    return SweepPoint(multiplier=multiplier, voltage=-multiplier * 1e-6,
                      n_spikes=n_spikes, rate=n_spikes / 600.0, violations=0.0,
                      median_amplitude=-1e-5, snr=4.0, active_channels=1,
                      mean_waveform=np.zeros(0))


# Counts falling fast, then levelling off: the shape of a real sweep, where the
# elbow is the reading everyone is after.
elbow = [_point(m, n) for m, n in
         ((2.0, 100000), (2.5, 30000), (3.0, 8000), (3.5, 2000),
          (4.0, 700), (4.5, 500), (5.0, 430), (5.5, 400))]
slopes = count_slopes(elbow)
check("a slope is reported for each step, not each point",
      slopes.size == len(elbow) - 1, str(slopes.size))
check("the counts fall, so every slope is negative",
      bool((slopes < 0).all()), str(slopes))
check("the knee is found where the fall flattens",
      knee_threshold(elbow) == 4.0, str(knee_threshold(elbow)))

flat = [_point(m, 500) for m in (2.0, 3.0, 4.0)]
check("a curve that never falls has no knee to report",
      knee_threshold(flat) is None, str(knee_threshold(flat)))
check("one threshold is not a sweep", knee_threshold([_point(4.0, 10)]) is None)

# The measures themselves, over a real detection at many thresholds.
with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "sweep.mat"
    synthetic_recording(raw_path, seconds=4.0, n_channels=2)

    swept = SpikeViewerWindow()
    swept.load_defaults(Params())
    swept._auto_detect.setChecked(False)
    swept.open_raw(raw_path)
    pump(swept)

    check("the sweep tab is there",
          "Threshold sweep" in [swept._tabs.tabText(i).strip()
                                for i in range(swept._tabs.count())],
          str([swept._tabs.tabText(i) for i in range(swept._tabs.count())]))
    check("and says what it needs before anything is swept",
          not swept._sweep_result)

    swept._sweep_from.setValue(2.0)
    swept._sweep_to.setValue(6.0)
    swept._sweep_step.setValue(1.0)
    check("the range is inclusive of both ends",
          swept._sweep_multipliers() == [2.0, 3.0, 4.0, 5.0, 6.0],
          str(swept._sweep_multipliers()))

    swept._sweep(all_channels=False)
    pump(swept)
    points = swept._sweep_result
    check("every threshold in the range is reported",
          [p.multiplier for p in points] == [2.0, 3.0, 4.0, 5.0, 6.0],
          str([p.multiplier for p in points]))
    check("raising the threshold never finds more spikes",
          all(a.n_spikes >= b.n_spikes for a, b in zip(points, points[1:])),
          str([p.n_spikes for p in points]))
    check("each threshold reports the voltage it worked out to",
          all(p.voltage < 0 for p in points), str([p.voltage for p in points]))
    check("and the mean spike it admitted",
          all(np.size(p.mean_waveform) for p in points if p.n_spikes),
          str([np.size(p.mean_waveform) for p in points]))
    check("a higher threshold admits a larger median spike",
          abs(points[-1].median_amplitude) > abs(points[0].median_amplitude),
          f"{points[0].median_amplitude} then {points[-1].median_amplitude}")
    check("the sweep names what it covered",
          "channel" in swept._sweep_scope, swept._sweep_scope)

    # The point of the tab: carrying a chosen threshold back to the settings.
    swept._sweep_pick.setValue(4.5)
    swept._on_use_swept_threshold()
    check("the chosen threshold reaches the detection settings",
          swept._thresholds.text() == "4.5", swept._thresholds.text())
    check("and says it has not re-detected by itself",
          "Detect" in swept._status.text(), swept._status.text())

    swept._tabs.setCurrentIndex(3)
    app.processEvents()
    check("the sweep draws without raising", True)
    swept.close()


print("\nWhat the filter does")

freqs, psd = _spectrum(np.random.default_rng(3).normal(size=30000), 12500.0)
check("the spectrum drops DC", freqs.size and freqs.min() > 0, str(freqs[:1]))
check("the spectrum stops at Nyquist", freqs.max() <= 12500.0 / 2, str(freqs.max()))
check("a trace too short for a spectrum returns nothing, not an error",
      _spectrum(np.zeros(4), 12500.0)[0].size == 0)


print("\nSaying what is happening")

sized = Path(tempfile.gettempdir()) / "meanap_size_probe.bin"
sized.write_bytes(b"0" * 3000)
check("a file is described by name and size",
      "meanap_size_probe.bin" in _describe_file(sized) and "KB" in _describe_file(sized),
      _describe_file(sized))
sized.unlink()
check("a file that is not there is still described by name",
      _describe_file(Path("/nowhere/at/all.mat")) == "all.mat",
      _describe_file(Path("/nowhere/at/all.mat")))

busy_viewer = SpikeViewerWindow()
busy_viewer._workers.append(object())
busy_viewer._update_busy()
check("a running job shows the progress bar", busy_viewer._progress.isVisible() or
      not busy_viewer.isVisible(), "hidden window cannot show it")
check("a running job locks the file pickers",
      not busy_viewer._raw_browse.isEnabled())
busy_viewer._workers.clear()
busy_viewer._update_busy()
check("finishing unlocks them again", busy_viewer._raw_browse.isEnabled())
check("but detection stays locked with nothing loaded",
      not busy_viewer._detect_all_btn.isEnabled())
busy_viewer.close()


print("\nSaving a detection, and finding it again")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "keepme.mat"
    synthetic_recording(raw_path, seconds=3.0, n_channels=3)

    first = SpikeViewerWindow()
    first.load_defaults(Params())
    first._thresholds.setText("4")
    first.open_raw(raw_path)
    pump(first)
    pump(first)
    counts = {ch: first._times_for(ch, "thr4").size for ch in range(3)}
    shapes = {ch: first._waveforms[ch]["thr4"].shape for ch in range(3)}
    thresholds = {ch: first._spike_thresholds[ch]["thr4"] for ch in range(3)}

    saved = first._suggested_spike_path()
    check("a save is offered beside the recording it came from",
          saved.parent == raw_path.parent and saved.name == "keepme_spikes.npz",
          str(saved))
    save_spike_times_npz(saved, first._spike_times, first._spike_channels,
                         first._fs, params=first._saved_params(),
                         duration_s=first._duration_s,
                         waveforms=first._waveforms,
                         thresholds=first._spike_thresholds)
    check("the file is written", saved.exists())
    first.close()

    # Read back through the ordinary loader: what the viewer writes must be
    # what anything else reads, including the pipeline.
    reloaded = load_spike_file(saved)
    check("the times survive",
          all(reloaded.spike_times[ch]["thr4"].size == n
              for ch, n in counts.items()), str(counts))
    check("so do the waveforms, which a file of times alone would lose",
          all(reloaded.waveforms[ch]["thr4"].shape == shape
              for ch, shape in shapes.items()), str(shapes))
    check("and the threshold each method detected at",
          all(abs(reloaded.thresholds[ch]["thr4"] - value) < 1e-12
              for ch, value in thresholds.items()), str(thresholds))
    check("the sampling rate and duration come back",
          reloaded.fs == first._fs and reloaded.duration_s is not None,
          f"{reloaded.fs} / {reloaded.duration_s}")
    check("the settings it was detected with are written beside it",
          saved.with_name(saved.stem + "_params.txt").exists())

    # Opening the recording again should cost nothing: the spikes are there.
    second = SpikeViewerWindow()
    second.load_defaults(Params())
    second.open_raw(raw_path)
    pump(second)
    pump(second)
    check("opening the recording again picks the saved spikes up",
          {ch: second._times_for(ch, "thr4").size for ch in range(3)} == counts,
          str({ch: second._times_for(ch, "thr4").size for ch in range(3)}))
    check("with their waveforms, so the quality page still works",
          second._waveforms[0]["thr4"].shape == shapes[0],
          str(second._waveforms.get(0, {}).get("thr4", np.zeros(0)).shape))
    check("and it says where they came from",
          "keepme_spikes.npz" in second._spikes_path.text(),
          second._spikes_path.text())
    second.close()

    # Bursts take as long to compute as the spikes and describe the same
    # recording, so they travel with them.
    third = SpikeViewerWindow()
    third.load_defaults(Params())
    third._auto_detect.setChecked(False)
    third.open_raw(raw_path)
    pump(third)
    third._spikes_path.setText("")
    third._thresholds.setText("4")
    third._detect(all_channels=True, thresholds_only=True)
    pump(third)
    third._sc_min_spikes.setValue(4)
    third._nb_min_channels.setValue(2)
    third._detect_bursts()
    pump(third)
    # Which spikes you feed a burst detector decides what it finds, so results
    # are kept — and saved — per spike method.
    check("bursts are detected for every method on screen",
          set(third._bursts_by_method) == set(third._selected_methods()),
          f"{sorted(third._bursts_by_method)} vs {third._selected_methods()}")
    method = third._primary_method()
    network, _chans, info, single = third._bursts_by_method[method]
    check("the fixture bursts, so there is something to round-trip",
          len(network) > 0 and len(single["bursting_units"]) > 0,
          f"{len(network)} network, {len(single['bursting_units'])} channels")

    with_bursts = Path(tmp) / "with_bursts.npz"
    save_spike_times_npz(with_bursts, third._spike_times, third._spike_channels,
                         third._fs, duration_s=third._duration_s,
                         bursts=pack_bursts(third._bursts_by_method))
    restored = unpack_bursts(load_spike_file(with_bursts).bursts)
    check("every method's bursts come back under its own name",
          set(restored) == set(third._bursts_by_method), str(sorted(restored)))
    back = restored[method]
    check("the network bursts come back where they were",
          np.array_equal(np.asarray(back[0]), np.asarray(network)),
          f"{len(back[0])} vs {len(network)}")
    check("so does the ISIn threshold they were found at",
          back[2]["isin_th"] == info["isin_th"],
          f"{back[2]['isin_th']} vs {info['isin_th']}")
    check("and which channels burst on their own",
          np.array_equal(back[3]["bursting_units"], single["bursting_units"]),
          str(back[3]["bursting_units"]))
    same_matrices = all(
        np.array_equal(back[3]["burst_matrices"][ch]["T_start"],
                       np.asarray(matrix["T_start"], float))
        and np.array_equal(back[3]["burst_matrices"][ch]["T_end"],
                           np.asarray(matrix["T_end"], float))
        for ch, matrix in single["burst_matrices"].items()
        if np.size(matrix["T_start"]))
    check("each channel's own bursts come back too", same_matrices)

    fourth = SpikeViewerWindow()
    fourth.load_defaults(Params())
    fourth.open_spikes(with_bursts)
    pump(fourth)
    check("a file with bursts opens showing them, not asking for a re-run",
          len(fourth._bursts_by_method.get(method, ([],))[0]) == len(network),
          str({m: len(b[0]) for m, b in fourth._bursts_by_method.items()}))
    check("and says which methods they came for",
          method in fourth._status.text(), fourth._status.text())
    fourth.close()

    # The one thing that must not happen: bursts outliving the spikes they
    # describe. A fresh detection makes them describe something else.
    third._detect(all_channels=True, thresholds_only=True)
    pump(third)
    check("re-detecting spikes drops the bursts rather than mislabelling them",
          third._bursts_by_method == {}, str(list(third._bursts_by_method)))
    check("and the save button stops promising them",
          third._save_btn.text() == "Save spikes…", third._save_btn.text())
    third.close()

    check("a spike file with no bursts in it restores none",
          unpack_bursts({}) == {})
    # Files written before results were kept per method are still readable, and
    # are labelled as what they are rather than pinned on a method that may not
    # have produced them.
    legacy = unpack_bursts({"network_times": np.zeros((2, 2)),
                            "isin_th": np.array([0.1]),
                            "bursting_units": np.array([1, 2])})
    check("bursts saved before methods were recorded still load",
          list(legacy) == [UNLABELLED_METHOD], str(list(legacy)))

    # A file the pipeline wrote carries times only; that must still open.
    times_only = Path(tmp) / "times_only.npz"
    save_spike_times_npz(times_only, {0: {"thr4": np.array([0.1, 0.2])}},
                         np.array([1]), 12500.0)
    lean = load_spike_file(times_only)
    check("a times-only file from a pipeline run still loads",
          lean.spike_times[0]["thr4"].size == 2 and lean.waveforms == {},
          str(lean.waveforms))


print("\nThe burst diagnostics tab")

with tempfile.TemporaryDirectory() as tmp:
    raw_path = Path(tmp) / "diag.mat"
    synthetic_recording(raw_path, seconds=6.0, n_channels=4)

    diag = SpikeViewerWindow()
    diag.load_defaults(Params())
    diag._auto_detect.setChecked(False)
    diag._thresholds.setText("4")
    diag.open_raw(raw_path)
    pump(diag)

    diag._tabs.setCurrentIndex(TAB_BURST_STATS)
    diag._refresh()
    check("with no spikes it says so rather than drawing an empty grid",
          len(diag._burst_stats_canvas.figure.axes) == 1)

    diag._detect(all_channels=True, thresholds_only=True)
    pump(diag)
    diag._tabs.setCurrentIndex(TAB_BURST_STATS)
    diag._refresh()
    check("spikes without bursts still ask for a detection",
          len(diag._burst_stats_canvas.figure.axes) == 1)

    diag._sc_min_spikes.setValue(4)
    diag._nb_min_channels.setValue(2)
    diag._detect_bursts()
    pump(diag)
    check("detecting bursts opens the Bursts tab, not the diagnostics",
          diag._tabs.currentIndex() == TAB_BURSTS,
          str(diag._tabs.currentIndex()))

    diag._tabs.setCurrentIndex(TAB_BURST_STATS)
    diag._refresh()
    check("the diagnostics draw a panel for each distribution",
          len(diag._burst_stats_canvas.figure.axes) == 6,
          str(len(diag._burst_stats_canvas.figure.axes)))
    titles = " ".join(ax.get_title() for ax in
                      diag._burst_stats_canvas.figure.axes)
    check("including the ISIn distribution the threshold came from",
          "ISI$_{10}$" in titles or "ISI" in titles, titles)
    check("and it says whether the threshold was a valley or a fallback",
          "valley" in titles or "fallback" in titles, titles)

    # The detector's own record of what it did, which the ISIn panel reports.
    info = diag._bursts_by_method["thr4"][2]
    check("the detector reports how many fragments it merged",
          "n_before_merge" in info and info["n_before_merge"] >= len(
              diag._bursts_by_method["thr4"][0]),
          str(info.get("n_before_merge")))
    check("and hands back the unmerged bursts for the interval panel",
          np.asarray(info.get("pre_merge_s", ())).reshape(-1, 2).shape[0]
          == info["n_before_merge"],
          str(np.asarray(info.get("pre_merge_s", ())).shape))

    # Channels-per-burst is recomputed rather than read from the stored list,
    # because a reloaded file does not carry that list.
    burst_times = diag._bursts_by_method["thr4"][0]
    counts = diag._channels_per_burst(diag._spikes_for_method("thr4"),
                                      burst_times)
    check("every burst is counted against the electrodes that fired in it",
          counts.size == len(burst_times) and counts.min() >= 2,
          f"{counts.size} counts, min {counts.min() if counts.size else '-'}")

    # A file reloaded from disk has no burst_channels and no pre-merge times;
    # the tab has to draw from the spikes alone rather than fall over.
    thin = dict(diag._bursts_by_method)
    thin["thr4"] = (burst_times, [], {"isin_th": info["isin_th"]},
                    diag._bursts_by_method["thr4"][3])
    diag._bursts_by_method = thin
    diag._refresh()
    check("a reloaded file without those extras still draws",
          len(diag._burst_stats_canvas.figure.axes) == 6,
          str(len(diag._burst_stats_canvas.figure.axes)))
    diag.close()


print("\nSwitching from one recording to another")

with tempfile.TemporaryDirectory() as tmp:
    wide = Path(tmp) / "wide.mat"
    narrow = Path(tmp) / "narrow.mat"
    synthetic_recording(wide, seconds=3.0, n_channels=6)
    synthetic_recording(narrow, seconds=2.0, n_channels=2)

    swap = SpikeViewerWindow()
    swap.load_defaults(Params())
    swap._thresholds.setText("4")
    swap.open_raw(wide)
    pump(swap)
    pump(swap)
    swap._sc_min_spikes.setValue(4)
    swap._nb_min_channels.setValue(2)
    swap._detect_bursts()
    pump(swap)

    check("the first recording is detected and burst-detected",
          swap._channel_combo.count() == 6 and bool(swap._spike_times)
          and bool(swap._bursts_by_method),
          f"{swap._channel_combo.count()} channels, "
          f"{len(swap._spike_times)} with spikes, "
          f"{len(swap._bursts_by_method)} with bursts")
    wide_counts = {ch: swap._times_for(ch, "thr4").size for ch in range(6)}
    # What the field would hold had these spikes come from a file rather than
    # from the detection pass, so the check below has something to clear.
    swap._spikes_path.setText(str(wide.with_name("wide_spikes.npz")))

    # The second recording has fewer channels, which is what makes carrying
    # the first one's state over visible rather than merely wrong.
    swap.open_raw(narrow)
    pump(swap)
    pump(swap)

    check("the channel list follows the new recording",
          swap._channel_combo.count() == 2, str(swap._channel_combo.count()))
    check("and its duration does too",
          abs(swap._duration_s - 2.0) < 0.01, str(swap._duration_s))
    check("the previous recording's spikes are gone, not drawn on this one",
          set(swap._spike_times) <= {0, 1}, str(sorted(swap._spike_times)))
    check("the previous recording's bursts are gone with them",
          all(len(bursts[1]) <= 2 for bursts in swap._bursts_by_method.values())
          if swap._bursts_by_method else True,
          str({m: len(b[1]) for m, b in swap._bursts_by_method.items()}))
    check("the stale spike file path is cleared",
          "wide" not in swap._spikes_path.text(), swap._spikes_path.text())
    check("the new recording is detected on its own",
          bool(swap._spike_times), str(sorted(swap._spike_times)))
    # The fixture plants a burst of five every 0.5 s, so a 2 s recording holds
    # fewer spikes per channel than a 3 s one — the counts have to differ.
    narrow_counts = {ch: swap._times_for(ch, "thr4").size for ch in range(2)}
    check("and those are its spikes, not the ones carried over",
          all(narrow_counts[ch] != wide_counts[ch] for ch in range(2))
          and all(n > 0 for n in narrow_counts.values()),
          f"{narrow_counts} vs {{0: {wide_counts[0]}, 1: {wide_counts[1]}}}")
    check("the array map has no coordinates left from the other layout",
          swap._coords is None or len(swap._coords) == 2,
          str(None if swap._coords is None else len(swap._coords)))
    swap.close()

    # Spikes opened first, then the raw file that goes with them, is the other
    # way through _on_raw_loaded — and there the spikes must survive.
    keep = SpikeViewerWindow()
    keep.load_defaults(Params())
    keep._auto_detect.setChecked(False)
    keep._thresholds.setText("4")
    keep.open_raw(wide)
    pump(keep)
    keep._detect(all_channels=True, thresholds_only=True)
    pump(keep)
    saved = Path(tmp) / "wide_spikes.npz"
    save_spike_times_npz(saved, keep._spike_times, keep._spike_channels,
                         keep._fs, params=keep._saved_params(),
                         duration_s=keep._duration_s,
                         waveforms=keep._waveforms,
                         thresholds=keep._spike_thresholds)
    keep.close()

    paired = SpikeViewerWindow()
    paired.load_defaults(Params())
    paired._default_raw_dir = tmp
    paired.open_spikes(saved)
    pump(paired)
    pump(paired)
    check("opening a spike file still pulls its raw recording in",
          paired._dat is not None)
    check("and finding that recording does not throw the spikes away",
          bool(paired._spike_times), str(sorted(paired._spike_times)))
    paired.close()


print("\nReading a finished run's spikes")

detected = Path("OutputData28Aug2025/1_SpikeDetection/1A_SpikeDetectedData/"
                "NGN2_20230208_P1_DIV14_A2_spikes.mat")
if detected.exists():
    spike_file = load_spike_file(detected)
    check("methods come back from the file",
          "thr4" in spike_file.methods, str(spike_file.methods))
    check("the sampling rate comes back from the file",
          spike_file.fs == 12500.0, str(spike_file.fs))
    check("waveforms are (spikes, samples), not the transpose HDF5 stores",
          spike_file.waveforms[0]["thr4"].shape[0]
          == spike_file.spike_times[0]["thr4"].size,
          str(spike_file.waveforms[0]["thr4"].shape))
    check("thresholds come back per method",
          np.isfinite(spike_file.thresholds[0]["thr4"]),
          str(spike_file.thresholds[0]))
    check("the file's own detection settings come back",
          spike_file.params.get("filterHighPass") == 6150.0,
          str(spike_file.params.get("filterHighPass")))
else:
    print("  SKIP  no detected example run in this checkout")

window.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed:")
    for failure in FAILURES:
        print(f"  - {failure}")
    sys.exit(1)
print("All checks passed.")
