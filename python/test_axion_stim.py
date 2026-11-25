"""Axion stimulation read from the ``.raw`` (the ``axionStimEvents`` method).

Two halves:

* **Synthetic files**, always run. :func:`write_tag_raw` writes an Axion
  ``.raw`` holding only stimulation tags, laid out byte for byte as the
  toolbox reads them (``TagEntry.m``, ``EventTag.m``, ``StimulationEvent.m``,
  ``StimulationWaveform.m``, ``StimulationChannels.m``, ``StimulationLeds.m``).
  These pin the decoding, head revisions, linking, unlinked events, LED
  events, the per-well assembly, pattern numbering by first stimulation, and
  the stim step end to end, including its fallback for events that name no
  electrode.
* **The real recording** ``~/Downloads/AK_HCNT24.4_DIV60_HL_5uA.raw``, skipped
  when it is not on this machine: the stimulated electrodes per well, event
  counts, and that times are sorted and inside the recording. MATLAB's run on
  it (OutputData24Jun2026) stimulated well A1 on electrode 33 only.

    uv run pytest python/test_axion_stim.py
"""

from __future__ import annotations

import struct
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REAL_RAW = Path.home() / "Downloads/AK_HCNT24.4_DIV60_HL_5uA.raw"

ZERO = uuid.UUID(int=0)


# ── Writing tag-only .raw files ───────────────────────────────────────────────

def _tag(tag_type: int, guid: uuid.UUID, body: bytes, revision: int = 0) -> bytes:
    return (struct.pack("<H", tag_type) + struct.pack("<7H", 2026, 6, 24, 12, 0, 0, 0)
            + guid.bytes_le + struct.pack("<I", revision) + body)


def event_tag(guid, time_s, waveform, channels, block, fs=12500.0, revision=0) -> bytes:
    body = (struct.pack("<dqq", fs, int(round(time_s * fs)), 0) + struct.pack("<HH", 0, 0)
            + waveform.bytes_le + channels.bytes_le + struct.pack("<HH", block, 0))
    return _tag(5, guid, body, revision)


def _string(s: str) -> bytes:
    b = s.encode()
    return struct.pack("<i", len(b)) + b


def waveform_tag(guid, blocks: dict[int, tuple[int, ...]], program: str = "micro ops") -> bytes:
    body = struct.pack("<HH", 0, len(blocks))
    for block_id, groups in blocks.items():
        g = list(groups) + [0] * (2 - len(groups))
        body += struct.pack("<HHddHH", block_id, 0, 0.0004, 0.002, *g) + _string(f"block {block_id}")
    if program.startswith("<?xml"):           # as AxIS writes it: UTF-16 with a BOM
        raw = program.encode("utf-16")
        return _tag(7, guid, body + struct.pack("<i", len(raw)) + raw)
    return _tag(7, guid, body + _string(program))


def channel_tag(guid, groups: dict[int, list[tuple[str, int]]]) -> bytes:
    """``groups``: ID → [(well, electrode ID column*10 + row), …]."""
    body = struct.pack("<HH", 0, 0)
    for group_id, mappings in groups.items():
        body += struct.pack("<III", group_id, 25165825, len(mappings))
        for well, electrode in mappings:
            row, col = "ABCDEFGH".index(well[0]) + 1, int(well[1:])
            body += struct.pack("<6BH", col, row, electrode // 10, electrode % 10, 0, 0, 0xFFFF)
    return _tag(6, guid, body)


def led_tag(guid, groups: dict[int, list[str]]) -> bytes:
    body = struct.pack("<HH", 0, len(groups))
    for group_id, wells in groups.items():
        body += struct.pack("<III", group_id, 25165825, len(wells))
        for well in wells:
            body += struct.pack("<BBH", int(well[1:]), "ABCDEFGH".index(well[0]) + 1, 1)
    return _tag(9, guid, body)


def deleted_tag(guid, revision) -> bytes:
    return _tag(0, guid, b"", revision)


def write_tag_raw(path: Path, entries: list[bytes]) -> Path:
    """An Axion ``.raw`` header whose entries are *entries* (tag entries), with
    a second header page when there are more than fit on the first."""
    first, rest = entries[:120], entries[120:]
    header_len = 8 + 2 * 3 + 8 + 4 + 8 + 8 * 123
    entries_start = header_len + (-header_len % 8)

    def slots(chunk, n):
        out = [(0x06 << 56) | len(e) for e in chunk]
        return struct.pack(f"<{n}Q", *(out + [0] * (n - len(out))))

    body = b"".join(first)
    if rest:
        # A page that runs out of slots without a terminator continues on a
        # page right after its entries; the spare slots are zero-length Skips.
        used = [(0x06 << 56) | len(e) for e in first]
        page1 = struct.pack("<123Q", *(used + [0xFF << 56] * (123 - len(used))))
        tail = b"AxionBio" + slots(rest, 126) + struct.pack("<II", 0, 0) + b"".join(rest)
    else:
        page1 = slots(first, 123)
        tail = b""
    head = (b"AxionBio" + struct.pack("<HHH", 0, 1, 0) + struct.pack("<qI", 0, 600)
            + struct.pack("<q", entries_start) + page1)
    head += b"\0" * (entries_start - len(head))
    path.write_bytes(head + body + tail)
    return path


# The scene used throughout: a waveform whose block 2 drives two channel
# groups (A1/12 and A1/44 + B2/21), block 1 one group (A1/33).
W, C, L = (uuid.UUID(int=i) for i in (101, 102, 103))
GROUPS = {10: [("A1", 33)], 11: [("A1", 12)], 12: [("A1", 44), ("B2", 21)]}


def _electrode_scene(tmp: Path) -> Path:
    ev = []
    for i, t in enumerate((1.0, 3.0, 5.0)):
        ev.append(event_tag(uuid.UUID(int=1000 + i), t, W, C, block=2))
    for i, t in enumerate((2.0, 4.0, 6.0)):
        ev.append(event_tag(uuid.UUID(int=2000 + i), t, W, C, block=1))
    # A revised event: revision 1 (t = 7 s) replaces revision 0 (t = 9 s).
    rev = uuid.UUID(int=3000)
    ev += [event_tag(rev, 9.0, W, C, block=1, revision=0),
           event_tag(rev, 7.0, W, C, block=1, revision=1)]
    # Deleted at its head revision: not an event.
    gone = uuid.UUID(int=3001)
    ev += [event_tag(gone, 8.0, W, C, block=1, revision=0), deleted_tag(gone, 1)]
    # Unlinked: zero GUIDs, and a waveform the file doesn't hold.
    ev += [event_tag(uuid.UUID(int=4000), 8.0, ZERO, ZERO, block=1),
           event_tag(uuid.UUID(int=4001), 8.5, uuid.UUID(int=999), C, block=1)]
    return write_tag_raw(tmp / "Plate_DIV14.raw",
                         [waveform_tag(W, {1: (10,), 2: (11, 12)}),
                          channel_tag(C, GROUPS), *ev])


# ── The reader ────────────────────────────────────────────────────────────────

def test_reader_decodes_and_links(tmp_path):
    from meanap.pipeline.axion_raw import read_axion_stim_events

    ev = read_axion_stim_events(_electrode_scene(tmp_path))
    assert ev.n_unlinked == 2 and ev.unlinked_times == (8.0, 8.5)
    assert [e.time_s for e in ev.events] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    by_time = {e.time_s: e for e in ev.events}
    assert by_time[1.0].block_id == 2
    assert by_time[1.0].electrodes == (("A1", 12), ("A1", 44), ("B2", 21))
    assert by_time[2.0].electrodes == (("A1", 33),)
    assert by_time[7.0].electrodes == (("A1", 33),)        # the head revision
    assert ev.stimulated_wells() == ["A1", "B2"] and ev.names_electrodes()


def test_reader_follows_header_pages(tmp_path):
    """More tags than one header page holds: the walk reads the next page."""
    from meanap.pipeline.axion_raw import read_axion_stim_events

    events = [event_tag(uuid.UUID(int=5000 + i), 0.5 + i, W, C, block=1) for i in range(130)]
    raw = write_tag_raw(tmp_path / "big.raw",
                        [waveform_tag(W, {1: (10,)}), channel_tag(C, GROUPS), *events])
    ev = read_axion_stim_events(raw)
    assert len(ev.events) == 130 and ev.n_unlinked == 0


#: How AxIS wrote AK_HCNT24.4_DIV60_HL_5uA.raw: the block lists no channel group
#: (both slots 0), and the program arms channel array 1 instead.
PROGRAM = """<?xml version="1.0" encoding="utf-16"?>
<electrical-operations xmlns="StimulationSchema.xsd">
  <achkset channelid="0xFF,0xFF" command="0x08E0" />
  <achkset channelarrayid="1" command="0x08E4" />
  <loop repetitions="3"><tag id="0"><stimulation /></tag></loop>
</electrical-operations>"""


def test_block_without_groups_uses_the_programs_channel_array(tmp_path):
    from meanap.pipeline.axion_raw import read_axion_stim_events

    raw = write_tag_raw(tmp_path / "Prog.raw", [
        waveform_tag(W, {0: ()}, PROGRAM),
        channel_tag(C, {1: [("A1", 33), ("B2", 21)]}),
        *[event_tag(uuid.UUID(int=10 + i), 2.0 + 5 * i, W, C, block=0) for i in range(3)]])
    ev = read_axion_stim_events(raw)
    assert ev.n_unlinked == 0 and len(ev.events) == 3
    assert all(e.electrodes == (("A1", 33), ("B2", 21)) for e in ev.events)

    # Without the program to say, the block drives nothing that can be named.
    plain = write_tag_raw(tmp_path / "Plain.raw", [
        waveform_tag(W, {0: ()}), channel_tag(C, {1: [("A1", 33)]}),
        event_tag(uuid.UUID(int=10), 2.0, W, C, block=0)])
    assert not read_axion_stim_events(plain).names_electrodes()


def test_led_events_name_wells_not_electrodes(tmp_path):
    from meanap.pipeline.axion_raw import read_axion_stim_events

    raw = write_tag_raw(tmp_path / "Led.raw", [
        waveform_tag(W, {3: (20,)}), led_tag(L, {20: ["A1", "B2"]}),
        event_tag(uuid.UUID(int=1), 1.5, W, L, block=3),
        event_tag(uuid.UUID(int=2), 2.5, W, L, block=3)])
    ev = read_axion_stim_events(raw)
    assert not ev.names_electrodes() and ev.n_unlinked == 0
    assert [e.led_wells for e in ev.events] == [("A1", "B2")] * 2


# ── Per-well assembly ─────────────────────────────────────────────────────────

def test_well_stimulation(tmp_path):
    from meanap.pipeline.axion_raw import read_axion_stim_events
    from meanap.stim.axion import ELECTRODES, NONE, well_stimulation

    ev = read_axion_stim_events(_electrode_scene(tmp_path))
    a1 = well_stimulation(ev, "Plate_DIV14_A1", "A1")
    assert a1.kind == ELECTRODES
    assert {k: v.tolist() for k, v in a1.times_by_electrode.items()} == {
        12: [1.0, 3.0, 5.0], 33: [2.0, 4.0, 6.0, 7.0], 44: [1.0, 3.0, 5.0]}
    assert well_stimulation(ev, "Plate_DIV14_B2", "B2").times_by_electrode.keys() == {21}
    c3 = well_stimulation(ev, "Plate_DIV14_C3", "C3")
    assert c3.kind == NONE and "A1, B2" in c3.summary


def test_patterns_numbered_by_first_stimulation(tmp_path):
    """Electrodes driven by one block share a pattern; pattern 1 is stimulated first."""
    from meanap.pipeline.axion_raw import read_axion_stim_events
    from meanap.stim.axion import stim_info_for_well, well_stimulation
    from meanap.stim.detection import get_stim_patterns

    ev = read_axion_stim_events(_electrode_scene(tmp_path))
    ws = well_stimulation(ev, "Plate_DIV14_A1", "A1")
    channels = np.array([11, 12, 33, 44, 99])
    logged = []
    info = stim_info_for_well(ws, channels[:4], np.zeros((4, 2)),
                              {"stimDuration": 0.0004}, logged.append)
    params = {"stimDetectionMethod": "axionStimEvents", "stimTimeDiffThreshold": 0.005}
    info, patterns = get_stim_patterns(info, params)
    assert [s.pattern for s in info] == [0, 1, 2, 1]
    assert patterns[0].tolist() == [1.0, 3.0, 5.0]
    assert all(s.blank_durations.sum() == 0 for s in info)       # zero-length blanks
    # By count (the voltage methods), the 3-event block would be pattern 1 anyway;
    # flip the counts to show the ordering really is by first time.
    ws.times_by_electrode[33] = np.array([2.0])
    info, _ = get_stim_patterns(
        stim_info_for_well(ws, channels[:4], np.zeros((4, 2)), {"stimDuration": 0.0004}),
        params)
    assert [s.pattern for s in info] == [0, 1, 2, 1]
    assert not logged

    # An electrode the recording lacks is reported and left out.
    stim_info_for_well(ws, np.array([12, 44]), np.zeros((2, 2)), {"stimDuration": 0.0004},
                       logged.append)
    assert "33" in logged[0] and "not channels of the recording" in logged[0]


def test_no_electrode_files(tmp_path):
    from meanap.pipeline.axion_raw import read_axion_stim_events
    from meanap.stim.axion import NO_ELECTRODE, NONE, well_stimulation

    led = write_tag_raw(tmp_path / "Led.raw", [
        waveform_tag(W, {3: (20,)}), led_tag(L, {20: ["A1"]}),
        event_tag(uuid.UUID(int=1), 1.5, W, L, block=3),
        event_tag(uuid.UUID(int=2), 2.5, W, L, block=3)])
    ev = read_axion_stim_events(led)
    a1 = well_stimulation(ev, "Led_A1", "A1")
    assert a1.kind == NO_ELECTRODE and a1.event_times.tolist() == [1.5, 2.5]
    assert well_stimulation(ev, "Led_B1", "B1").kind == NONE       # not lit

    tagless = write_tag_raw(tmp_path / "Tagless.raw", [
        event_tag(uuid.UUID(int=1), 1.0, ZERO, ZERO, block=1),
        event_tag(uuid.UUID(int=2), 2.0, ZERO, ZERO, block=1)])
    ws = well_stimulation(read_axion_stim_events(tagless), "Tagless_C2", "C2")
    assert ws.kind == NO_ELECTRODE and ws.event_times.tolist() == [1.0, 2.0]


def test_source_finds_the_raw_and_reads_it_once(tmp_path, monkeypatch):
    import meanap.pipeline.axion_raw as ar
    from meanap.stim.axion import AxionStimSource

    _electrode_scene(tmp_path)
    reads = []
    real = ar.read_axion_stim_events
    monkeypatch.setattr(ar, "read_axion_stim_events", lambda p: reads.append(p) or real(p))
    logged = []
    src = AxionStimSource([tmp_path / "missing", tmp_path], logged.append)
    assert src.for_recording("plate_div14_A1").times_by_electrode.keys() == {12, 33, 44}
    assert src.for_recording("Plate_DIV14_B2").times_by_electrode.keys() == {21}
    assert len(reads) == 1
    assert sum("unlinked" in s for s in logged) == 1
    assert src.for_recording("Other_A1") is None and "Other.raw not found" in logged[-1]
    assert src.for_recording("NoWell") is None and "_<well>" in logged[-1]


def test_voltage_detection_refuses_axion():
    from meanap.stim.detection import detect_stim_times

    with pytest.raises(ValueError, match="StimulationEvents"):
        detect_stim_times(np.zeros((10, 2)), {
            "stimDetectionMethod": "axionStimEvents", "stimRefractoryPeriod": 1.0,
            "stimDuration": 0.0001, "fs": 1000.0}, np.array([11, 12]), np.zeros((2, 2)))


def test_saved_params_with_the_csv_key_load(tmp_path):
    import json

    from meanap.params import Params, load_params, save_params

    path = save_params(Params(stim_detection_method="axionStimEvents"), tmp_path / "p.json")
    raw = json.loads(path.read_text())
    raw["axion_stim_csv"] = "/old/stim.csv"
    path.write_text(json.dumps(raw))
    params, unknown = load_params(path)
    assert params.stim_detection_method == "axionStimEvents" and unknown == []
    assert "axionStimCSV" not in params.to_stim_params_dict()


# ── The stim step end to end ──────────────────────────────────────────────────

CHANNELS = np.array([11, 21, 31, 41, 12, 22, 32, 42, 13, 23, 33, 43, 14, 24, 34, 44])
FS, T = 12500.0, 40.0
STIMS = np.arange(2.0, 38.0, 1.0)                    # 36 pulses


def _run_inputs(tmp: Path, raw_entries: list[bytes], stem: str) -> tuple[Path, Path]:
    import scipy.io as sio

    from meanap.pipeline.io import save_spike_times_npz
    from meanap.pipeline.resume import SPIKE_SUBDIR

    raw_dir = tmp / "raw"
    raw_dir.mkdir()
    write_tag_raw(raw_dir / f"{stem}.raw", raw_entries)
    rng = np.random.default_rng(0)
    dat = rng.normal(0, 5e-6, (int(T * FS), len(CHANNELS))).astype(np.float32)
    sio.savemat(raw_dir / f"{stem}_A1.mat",
                {"dat": dat, "channels": CHANNELS.astype(float), "fs": FS})
    trains = [np.sort(rng.uniform(0, T, rng.poisson(2 * T))) for _ in CHANNELS]
    for j in (0, 1, 4, 5):                           # electrodes 11, 21, 12, 22 respond
        for s in STIMS:
            trains[j] = np.sort(np.r_[trains[j], s + rng.uniform(0.004, 0.02, 3)])
    out = tmp / "Output"
    save_spike_times_npz(out / SPIKE_SUBDIR / f"{stem}_A1_spikes.npz",
                         {c: {"thr4p5": t} for c, t in enumerate(trains)}, CHANNELS, FS,
                         duration_s=T)
    return raw_dir, out


def _run(raw_dir: Path, out: Path, stem: str):
    from meanap.params import Params
    from meanap.pipeline.spreadsheet import RecordingInfo
    from meanap.pipeline.stim_step import run_stim_analysis

    params = Params(stimulation_mode=True, stim_detection_method="axionStimEvents",
                    raw_data=str(raw_dir), spikes_method="thr4p5", channel_layout="Axion16",
                    stim_network=False, stim_n_shuffles=20, random_seed=1,
                    post_stim_window_dur=2.0)
    lines = []
    run_stim_analysis(params, [RecordingInfo(f"{stem}_A1", 14, "WT")], out, log=lines.append)
    return lines


def test_stim_step_reads_the_raw(tmp_path):
    import pandas as pd

    from meanap.stim.redraw import FIGURES_SUFFIX, load_figure_payload

    entries = [waveform_tag(W, {1: (10,)}), channel_tag(C, {10: [("A1", 33)]})]
    entries += [event_tag(uuid.UUID(int=6000 + i), t, W, C, block=1)
                for i, t in enumerate(STIMS)]
    raw_dir, out = _run_inputs(tmp_path, entries, "Plate")
    lines = _run(raw_dir, out, "Plate")
    assert any("stimulated electrode(s) 33 (36)" in s for s in lines), lines

    df = pd.read_csv(out / "StimActivity_NodeLevel.csv")
    assert set(df["pattern_id"]) == {1} and 33 not in set(df["channel_id"])
    assert df.set_index("channel_id").loc[11, "auc_corrected"] > 0
    payload = load_figure_payload(out / "ExperimentMatFiles" / f"Plate_A1{FIGURES_SUFFIX}")
    stim = [s for s in payload["stim_info"] if s.pattern > 0]
    assert [s.channel_name for s in stim] == [33]
    np.testing.assert_allclose(stim[0].elec_stim_times, STIMS)


def test_stim_step_falls_back_without_electrodes(tmp_path):
    import pandas as pd

    entries = [waveform_tag(W, {3: (20,)}), led_tag(L, {20: ["A1"]})]
    entries += [event_tag(uuid.UUID(int=7000 + i), t, W, L, block=3)
                for i, t in enumerate(STIMS)]
    raw_dir, out = _run_inputs(tmp_path, entries, "Led")
    lines = _run(raw_dir, out, "Led")
    assert any("as event-driven stimulation instead" in s for s in lines), lines

    df = pd.read_csv(out / "StimActivity_NodeLevel.csv")
    assert set(df["condition"]) == {"stim"} and len(df) == len(CHANNELS)
    events = pd.read_csv(out / "2_NeuronalActivity" / "2A_IndividualNeuronalAnalysis"
                         / "WT" / "Led_A1" / "stim_events.csv")
    assert len(events) == len(STIMS)


# ── The GUI's stim detection preview ──────────────────────────────────────────

def test_preview_shows_the_wells_events(tmp_path):
    from meanap.gui.panels.stim_preview import axion_preview

    _electrode_scene(tmp_path)
    params = {"stimDetectionMethod": "axionStimEvents", "stimTimeDiffThreshold": 0.005,
              "stimDuration": 0.0004}
    channels = np.array([11, 12, 33, 44])
    info, patterns, events, note = axion_preview("Plate_DIV14_A1", [tmp_path], channels,
                                                 np.zeros((4, 2)), params)
    assert [s.pattern for s in info] == [0, 1, 2, 1] and events is None
    assert "stimulated electrode(s) 12 (3), 33 (4), 44 (3)" in note

    write_tag_raw(tmp_path / "Led.raw", [
        waveform_tag(W, {3: (20,)}), led_tag(L, {20: ["A1"]}),
        event_tag(uuid.UUID(int=1), 1.5, W, L, block=3)])
    info, patterns, events, note = axion_preview("Led_A1", [tmp_path], channels,
                                                 np.zeros((4, 2)), params)
    assert events.tolist() == [1.5] and all(s.pattern == 0 for s in info)
    assert "event-driven" in note
    with pytest.raises(ValueError, match="not found"):
        axion_preview("Gone_A1", [tmp_path], channels, np.zeros((4, 2)), params)


def test_preview_panel_names_the_axion_well(tmp_path):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from meanap.gui.panels.stim_preview import StimPreviewPanel

    app = QApplication.instance() or QApplication([])   # noqa: F841
    panel = StimPreviewPanel()
    assert panel._method.findText("axionStimEvents") >= 0
    panel._path.setText(str(tmp_path / "Plate_DIV14.raw"))
    panel._well_combo.addItems(["A1", "B2"])
    panel._well_combo.setCurrentText("B2")
    panel._well_combo.setEnabled(True)
    assert panel.recording_name() == "Plate_DIV14_B2"
    panel._well_combo.setEnabled(False)
    panel._path.setText(str(tmp_path / "Plate_DIV14_A1.mat"))
    assert panel.recording_name() == "Plate_DIV14_A1"


# ── The real recording ────────────────────────────────────────────────────────

needs_real = pytest.mark.skipif(not REAL_RAW.is_file(), reason=f"{REAL_RAW} not on this machine")


@needs_real
def test_real_file_stimulated_electrodes():
    from meanap.pipeline.axion_raw import read_axion_metadata, read_axion_stim_events
    from meanap.stim.axion import ELECTRODES, well_stimulation

    meta = read_axion_metadata(REAL_RAW)
    ev = read_axion_stim_events(REAL_RAW)
    times = ev.times
    print(f"\n{REAL_RAW.name}: {len(ev.events)} linked event(s), {ev.n_unlinked} unlinked; "
          f"{meta.duration_s:g} s; wells {', '.join(meta.wells())}")
    assert len(ev.events) > 0
    assert np.all(np.diff(times) >= 0)
    assert times.min() >= 0 and times.max() <= meta.duration_s

    per_well = {}
    for well in meta.wells():
        ws = well_stimulation(ev, f"{REAL_RAW.stem}_{well}", well)
        if ws.kind == ELECTRODES:
            per_well[well] = {k: len(v) for k, v in ws.times_by_electrode.items()}
            for v in ws.times_by_electrode.values():
                assert np.all(np.diff(v) > 0) and v.max() <= meta.duration_s
        print(f"  {ws.summary}")
    # 60 pulses 5 s apart, each on one electrode of every well but E5; the
    # program arms channel array 1, which names them. MATLAB's run
    # (OutputData24Jun2026, from a CSV) stimulated A1 on electrode 33.
    assert len(ev.events) == 60 and ev.n_unlinked == 0
    assert np.allclose(np.diff(times), 5.0, atol=1e-3)
    assert per_well["A1"] == {33: 60}
    assert per_well["B2"] == {33: 60} and per_well["C1"] == {23: 60}
    assert set(meta.wells()) - set(per_well) == {"E5"}
    assert all(len(v) == 1 and list(v.values()) == [60] for v in per_well.values())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
