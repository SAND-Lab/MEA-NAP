"""Step 1 from spikes sorted elsewhere: SpyKING CIRCUS, Kilosort/phy, SpikeInterface.

:mod:`meanap.pipeline.spike_sorting` makes units the pipeline's nodes by
running a sorter. Labs that already sort — often on high-density arrays where
sorting is the only sensible way in — have the units already. This module
reads them and writes the *same* ``_spikes.npz`` the in-pipeline sorter does:
one train per unit under method :data:`~meanap.params.SORTED_METHOD`,
``channels`` = each unit's peak electrode, ``unit_*`` arrays for what tells
units apart. Steps 2–4 therefore never learn where the units came from.

Each reader returns an :class:`ImportedSorting`:

* :func:`read_spykingcircus` — ``<base>.result[-merged].hdf5`` and the
  matching ``templates`` file, whose largest-amplitude electrode places a unit.
* :func:`read_phy` — a phy folder, which Kilosort 1–4 write natively and
  SpyKING CIRCUS and SpikeInterface export to.
* :func:`read_spikeinterface` — anything SpikeInterface can load (a saved
  ``SortingAnalyzer``, or a sorting with a recording beside it). Optional
  dependency, imported lazily.

Sorter output knows spike *samples*, not seconds, and rarely knows where its
channels sit on the array. Those come from the raw recording when one is at
hand (:class:`ElectrodeTable`, e.g. from :func:`meanap.pipeline.maxwell.read_maxwell_meta`)
— which is also what gives the exact duration, rather than the time of the
last spike.

See ``python/SORTED_IMPORT_PLAN.md``.
"""

from __future__ import annotations

import ast
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from meanap.params import SORTED_METHOD

#: The formats :func:`read_sorted_output` dispatches on, as stored in Params.
SORTED_FORMATS = ("auto", "spykingcircus", "phy", "spikeinterface")

#: Curation labels dropped by default. ``noise`` is what phy and Kilosort call
#: a cluster that is not a neuron; everything else (``good``, ``mua``, an
#: uncurated ``unsorted``) is kept, since MUA is still activity on that site.
DEFAULT_DROP_LABELS = ("noise",)

#: Label for units from a sorter that does not curate (SpyKING CIRCUS).
UNCURATED_LABEL = "unsorted"

#: Plot-coordinate span of the largest array extent: the MCS and Axion
#: layouts in :mod:`meanap.pipeline.channel_layout` all span ``[0, 8]``, so
#: node sizes and edge widths tuned for them look the same on an HD-MEA.
LAYOUT_SPAN = 8.0


@dataclass(frozen=True)
class ElectrodeTable:
    """The recorded electrodes, in the row order the sorter numbered them.

    ``ids`` are hardware electrode numbers (MaxWell's 0–26399, or a channel
    number when that is all there is); ``xy_um`` their positions with y
    increasing *down* the array, as MaxWell and phy both store them.
    """

    ids: np.ndarray
    xy_um: np.ndarray

    def __post_init__(self):
        if len(self.ids) != len(self.xy_um):
            raise ValueError(f"{len(self.ids)} electrode IDs but {len(self.xy_um)} positions")

    @classmethod
    def from_maxwell(cls, meta) -> "ElectrodeTable":
        return cls(ids=np.asarray(meta.electrodes), xy_um=np.asarray(meta.xy_um, float))


@dataclass
class ImportedSorting:
    """Units from an external sorter, ready to become pipeline nodes."""

    sorter: str
    #: The sorter's own name for each unit (``temp_12``, cluster ``37``).
    sorter_unit_ids: np.ndarray
    #: Spike times in seconds, one sorted array per unit.
    spike_trains: list[np.ndarray]
    #: Row of :attr:`electrodes` each unit is largest on.
    peak_index: np.ndarray
    electrodes: ElectrodeTable
    fs: float
    duration_s: float
    labels: np.ndarray
    #: Each unit's template on its peak electrode, ``(n_units, n_samples)``, in
    #: the sorter's units (SpyKING CIRCUS normalises them; phy's are whitened).
    templates: np.ndarray | None = None
    #: Where it all came from, for the params file beside the spikes.
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def n_units(self) -> int:
        return len(self.spike_trains)

    def subset(self, keep: np.ndarray) -> "ImportedSorting":
        keep = np.asarray(keep, dtype=bool)
        return ImportedSorting(
            sorter=self.sorter, sorter_unit_ids=self.sorter_unit_ids[keep],
            spike_trains=[t for t, k in zip(self.spike_trains, keep) if k],
            peak_index=self.peak_index[keep], electrodes=self.electrodes,
            fs=self.fs, duration_s=self.duration_s, labels=self.labels[keep],
            templates=None if self.templates is None else self.templates[keep],
            sources=self.sources,
        )


# ── Finding a recording's sorter output ───────────────────────────────────────

def _named_for(name: str, recording: str, separators: str = "._-",
               others: tuple[str, ...] = ()) -> bool:
    """``name`` is *recording*'s, not merely prefixed by it (``rec1`` ≠ ``rec10``).

    The name may carry a suffix after a separator — ``rec.raw.result.hdf5``,
    ``rec_kilosort4``, ``rec-phy`` — which is how sorter outputs are named.
    Since ``_`` also joins a plate to its well (``plate_A1``), a name that
    matches a *longer* recording among *others* is that one's, not this one's.
    """
    def match(rec: str) -> bool:
        return name == rec or (name.startswith(rec) and name[len(rec)] in separators)

    if not match(recording):
        return False
    return not any(len(o) > len(recording) and match(o) for o in others)


def find_sorted_output(folder: str | Path, recording: str, fmt: str = "auto",
                       others: tuple[str, ...] = ()) -> tuple[str, Path] | None:
    """Locate *recording*'s sorter output under *folder*: ``(format, path)``.

    SpyKING CIRCUS names its files after the raw file
    (``<rec>.raw.result-merged.hdf5`` for ``<rec>.raw.h5``); the merged result
    is preferred when both exist, since it is the one the user curated. A phy
    folder is any directory holding ``spike_times.npy`` whose own name, or a
    parent's, is the recording's — which covers Kilosort's output folder and
    SpyKING CIRCUS's ``<rec>/<rec>.GUI`` export alike. A SpikeInterface folder
    is a directory named for the recording that holds a saved analyzer or
    sorting (``spikeinterface_info.json``).

    *others* are the batch's other recording names, so that ``plate``'s
    search does not claim ``plate_A1``'s folder.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None

    if fmt in ("auto", "spykingcircus"):
        for suffix in (".result-merged.hdf5", ".result.hdf5"):
            # Named after the raw file, so only a "." follows the recording.
            hits = sorted(p for p in folder.rglob(f"*{suffix}")
                          if _named_for(p.name, recording, "."))
            if hits:
                return "spykingcircus", hits[0]

    if fmt in ("auto", "phy"):
        hits = sorted(
            (p.parent for p in folder.rglob("spike_times.npy")
             if any(_named_for(part, recording, others=others)
                    for part in p.parent.relative_to(folder).parts)),
            key=lambda p: len(p.parts))
        if hits:
            return "phy", hits[0]

    if fmt in ("auto", "spikeinterface"):
        for p in sorted(folder.rglob("spikeinterface_info.json"), key=lambda p: len(p.parts)):
            if any(_named_for(part, recording, others=others)
                   for part in p.parent.relative_to(folder).parts):
                return "spikeinterface", p.parent
    return None


def read_sorted_output(fmt: str, path: str | Path, *,
                       electrodes: ElectrodeTable | None = None,
                       fs: float | None = None,
                       duration_s: float | None = None) -> ImportedSorting:
    """Dispatch to the reader for *fmt* (as returned by :func:`find_sorted_output`)."""
    if fmt == "spykingcircus":
        return read_spykingcircus(path, electrodes=electrodes, fs=fs, duration_s=duration_s)
    if fmt == "phy":
        return read_phy(path, electrodes=electrodes, fs=fs, duration_s=duration_s)
    if fmt == "spikeinterface":
        return read_spikeinterface(path, electrodes=electrodes, duration_s=duration_s)
    raise ValueError(f"Unknown sorted-data format {fmt!r} (known: {', '.join(SORTED_FORMATS)})")


# ── SpyKING CIRCUS ────────────────────────────────────────────────────────────

def _spykingcircus_templates_path(result_path: Path) -> Path:
    """``x.result-merged.hdf5`` → ``x.templates-merged.hdf5`` (and unmerged alike)."""
    name = result_path.name.replace(".result", ".templates", 1)
    return result_path.with_name(name)


def _template_sort_key(name: str) -> int:
    return int(name.rsplit("_", 1)[1])


def read_spykingcircus(result_path: str | Path, *,
                       electrodes: ElectrodeTable | None,
                       fs: float | None,
                       duration_s: float | None = None) -> ImportedSorting:
    """Read a SpyKING CIRCUS ``result[-merged].hdf5`` and its templates.

    SpyKING CIRCUS stores samples (from the start of the file it sorted) and no
    sampling rate or electrode positions — those live in its ``.params`` and
    ``.prb`` files, which are routinely left behind. So *fs* and *electrodes*
    are required here; the runner takes them from the raw recording.

    A unit is placed on the electrode where its template is largest, which is
    what SpyKING CIRCUS itself calls the template's electrode.
    """
    import h5py
    from scipy.sparse import csc_matrix

    result_path = Path(result_path)
    if fs is None or electrodes is None:
        raise ValueError(
            f"{result_path.name}: SpyKING CIRCUS output has no sampling rate or "
            "electrode positions of its own — supply the raw recording")
    templates_path = _spykingcircus_templates_path(result_path)
    if not templates_path.exists():
        raise FileNotFoundError(f"{templates_path.name} not found beside {result_path.name}")

    with h5py.File(result_path, "r") as f:
        names = sorted(f["spiketimes"].keys(), key=_template_sort_key)
        samples = [f["spiketimes"][n][:].astype(np.int64) for n in names]

    with h5py.File(templates_path, "r") as f:
        n_e, n_t, n_cols = (int(x) for x in f["temp_shape"][:])
        dense = csc_matrix((f["temp_data"][:], (f["temp_x"][:], f["temp_y"][:])),
                           shape=(n_e * n_t, n_cols))
    # Columns [0, n_cols/2) are the templates, the rest their orthogonal
    # second components; result names temp_<k> index the first half.
    if len(names) > n_cols // 2:
        raise ValueError(f"{result_path.name}: {len(names)} units but only "
                         f"{n_cols // 2} templates in {templates_path.name}")
    if n_e != len(electrodes.ids):
        raise ValueError(
            f"{templates_path.name} has {n_e} electrodes but the recording has "
            f"{len(electrodes.ids)} — is this the sorting of a different file?")

    peak = np.empty(len(names), dtype=np.int64)
    templates = np.empty((len(names), n_t), dtype=np.float32)
    for i, n in enumerate(names):
        tmpl = dense[:, _template_sort_key(n)].toarray().reshape(n_e, n_t)
        peak[i] = int(np.argmax(np.abs(tmpl).max(axis=1)))
        templates[i] = tmpl[peak[i]]

    trains = [np.sort(s) / fs for s in samples]
    duration = _duration_or_last_spike(duration_s, trains, result_path.name)
    return ImportedSorting(
        sorter="spykingcircus", sorter_unit_ids=np.array(names),
        spike_trains=trains, peak_index=peak, electrodes=electrodes,
        fs=float(fs), duration_s=duration,
        labels=np.full(len(names), UNCURATED_LABEL),
        templates=templates,
        sources={"result": str(result_path), "templates": str(templates_path)},
    )


# ── phy / Kilosort ────────────────────────────────────────────────────────────

def _read_phy_params(folder: Path) -> dict[str, Any]:
    """phy's ``params.py`` as a dict, by parsing — never executing — it."""
    path = folder / "params.py"
    if not path.exists():
        return {}
    out: dict[str, Any] = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass   # e.g. dtype = np.int16 — not needed here
    return out


def _read_phy_labels(folder: Path, cluster_ids: np.ndarray) -> np.ndarray:
    """Each cluster's curation label, the manual one winning over Kilosort's.

    phy writes a user's labels to ``cluster_group.tsv``; Kilosort writes its
    own guess to ``cluster_KSLabel.tsv``; ``cluster_info.tsv`` repeats whichever
    applies in a ``group`` column. Unlabelled clusters are ``unsorted``, which
    is phy's own word for them.
    """
    labels: dict[int, str] = {}
    for name, col in (("cluster_KSLabel.tsv", "KSLabel"), ("cluster_info.tsv", "group"),
                      ("cluster_group.tsv", "group")):
        path = folder / name
        if not path.exists():
            continue
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                value = (row.get(col) or "").strip()
                if value and row.get("cluster_id") not in (None, ""):
                    labels[int(row["cluster_id"])] = value
    return np.array([labels.get(int(c), UNCURATED_LABEL) for c in cluster_ids])


def read_phy(folder: str | Path, *,
             electrodes: ElectrodeTable | None = None,
             fs: float | None = None,
             duration_s: float | None = None) -> ImportedSorting:
    """Read a phy folder (Kilosort's output, or any sorter's phy export).

    A unit is a *cluster* (``spike_clusters.npy``, falling back to
    ``spike_templates.npy`` for an uncurated Kilosort run). Its peak electrode
    comes from the template most of its spikes were fitted with.

    Electrode positions: phy's ``channel_positions.npy`` unless *electrodes*
    is given, in which case ``channel_map.npy`` picks rows out of it — so a
    MaxWell recording's real electrode IDs are used instead of phy's channel
    numbers. Duration: *duration_s*, else the ``.dat`` file's length, else the
    last spike.
    """
    folder = Path(folder)
    params = _read_phy_params(folder)
    fs = float(fs if fs is not None else params.get("sample_rate", 0)) or None
    if fs is None:
        raise ValueError(f"{folder}: no sample_rate in params.py and none supplied")

    samples = np.load(folder / "spike_times.npy").ravel().astype(np.int64)
    spike_templates = (np.load(folder / "spike_templates.npy").ravel().astype(np.int64)
                       if (folder / "spike_templates.npy").exists() else None)
    if (folder / "spike_clusters.npy").exists():
        clusters = np.load(folder / "spike_clusters.npy").ravel().astype(np.int64)
    elif spike_templates is not None:
        clusters = spike_templates
    else:
        raise FileNotFoundError(f"{folder}: neither spike_clusters.npy nor spike_templates.npy")

    channel_map = (np.load(folder / "channel_map.npy").ravel().astype(np.int64)
                   if (folder / "channel_map.npy").exists() else None)
    if electrodes is not None:
        rows = channel_map if channel_map is not None else np.arange(len(electrodes.ids))
        table = ElectrodeTable(ids=np.asarray(electrodes.ids)[rows],
                               xy_um=np.asarray(electrodes.xy_um)[rows])
    else:
        positions = np.load(folder / "channel_positions.npy").astype(float)
        ids = channel_map if channel_map is not None else np.arange(len(positions))
        table = ElectrodeTable(ids=ids, xy_um=positions[:, :2])

    cluster_ids = np.unique(clusters)
    peak = np.zeros(len(cluster_ids), dtype=np.int64)
    templates = None
    if (folder / "templates.npy").exists() and spike_templates is not None:
        tmpl_all = np.load(folder / "templates.npy")      # (n_templates, n_t, n_ch)
        templates = np.empty((len(cluster_ids), tmpl_all.shape[1]), dtype=np.float32)
        for i, c in enumerate(cluster_ids):
            main = np.bincount(spike_templates[clusters == c]).argmax()
            t = tmpl_all[main]
            peak[i] = int(np.argmax(np.abs(t).max(axis=0)))
            templates[i] = t[:, peak[i]]
    elif (folder / "cluster_info.tsv").exists():
        with open(folder / "cluster_info.tsv", newline="") as fh:
            ch = {int(r["cluster_id"]): int(r["ch"]) for r in csv.DictReader(fh, delimiter="\t")
                  if r.get("ch") not in (None, "")}
        peak = np.array([ch[int(c)] for c in cluster_ids], dtype=np.int64)
    else:
        raise FileNotFoundError(f"{folder}: no templates.npy or cluster_info.tsv to place units with")

    order = np.argsort(samples, kind="stable")
    samples, clusters = samples[order], clusters[order]
    trains = [samples[clusters == c] / fs for c in cluster_ids]

    if duration_s is None:
        duration_s = _phy_dat_duration(folder, params)
    duration = _duration_or_last_spike(duration_s, trains, folder.name)
    return ImportedSorting(
        sorter=str(params.get("sorter", "phy")) if "sorter" in params else "phy",
        sorter_unit_ids=cluster_ids.astype(str), spike_trains=trains,
        peak_index=peak, electrodes=table, fs=fs, duration_s=duration,
        labels=_read_phy_labels(folder, cluster_ids), templates=templates,
        sources={"phy": str(folder)},
    )


def _phy_dat_duration(folder: Path, params: dict[str, Any]) -> float | None:
    """Duration from the binary phy points at, when it is there to measure."""
    dat = params.get("dat_path")
    n_ch = params.get("n_channels_dat")
    if not dat or not n_ch:
        return None
    dat = dat[0] if isinstance(dat, (list, tuple)) else dat
    path = Path(dat) if Path(dat).is_absolute() else folder / dat
    if not path.exists():
        return None
    itemsize = np.dtype(params.get("dtype", "int16")).itemsize
    n_samples = (path.stat().st_size - int(params.get("offset", 0))) // (itemsize * int(n_ch))
    return n_samples / float(params["sample_rate"])


# ── SpikeInterface ────────────────────────────────────────────────────────────

def read_spikeinterface(path: str | Path, *,
                        electrodes: ElectrodeTable | None = None,
                        duration_s: float | None = None) -> ImportedSorting:
    """Read a saved SpikeInterface ``SortingAnalyzer`` (or a sorting folder).

    An analyzer carries everything: spike trains, the recording's sampling
    rate, duration and probe, and (once computed) templates — which place each
    unit on its largest channel. A bare sorting has none of the geometry, so
    *electrodes* must be given for it, and units fall back to SpikeInterface's
    ``max_channel`` property when the sorter set one.
    """
    try:
        import spikeinterface.core as sic
    except ImportError as e:
        raise ImportError("Reading a SpikeInterface folder needs SpikeInterface "
                          "(pip install meanap[sorting])") from e

    path = Path(path)
    obj = sic.load(path)
    analyzer = obj if hasattr(obj, "sorting") and hasattr(obj, "get_channel_locations") else None
    sorting = analyzer.sorting if analyzer is not None else obj
    fs = float(sorting.get_sampling_frequency())
    unit_ids = np.asarray(sorting.get_unit_ids())
    trains = [np.sort(np.asarray(sorting.get_unit_spike_train(u, segment_index=0))) / fs
              for u in unit_ids]

    templates = None
    if analyzer is not None:
        table = electrodes or ElectrodeTable(
            ids=np.asarray(analyzer.channel_ids).astype(str),
            xy_um=np.asarray(analyzer.get_channel_locations(), float)[:, :2])
        if duration_s is None:
            duration_s = analyzer.get_total_duration()
        ext = analyzer.get_extension("templates")
        if ext is None:
            raise ValueError(f"{path}: the analyzer has no 'templates' extension to "
                             "place units with — compute it first")
        tmpl = ext.get_templates(operator="average")       # (n_units, n_t, n_ch)
        peak = np.argmax(np.abs(tmpl).max(axis=1), axis=1).astype(np.int64)
        templates = np.stack([tmpl[i, :, p] for i, p in enumerate(peak)]).astype(np.float32)
    else:
        if electrodes is None:
            raise ValueError(f"{path}: a bare sorting has no electrode positions — "
                             "supply the recording or save a SortingAnalyzer")
        table = electrodes
        prop = sorting.get_property("max_channel")
        if prop is None:
            raise ValueError(f"{path}: no 'max_channel' property to place units with")
        peak = np.asarray(prop, dtype=np.int64)

    labels = sorting.get_property("quality")
    if labels is None:
        labels = sorting.get_property("KSLabel")
    labels = (np.asarray(labels).astype(str) if labels is not None
              else np.full(len(unit_ids), UNCURATED_LABEL))
    duration = _duration_or_last_spike(duration_s, trains, path.name)
    return ImportedSorting(
        sorter=str(sorting.get_annotation("sorter_name") or "spikeinterface"),
        sorter_unit_ids=unit_ids.astype(str), spike_trains=trains, peak_index=peak,
        electrodes=table, fs=fs, duration_s=float(duration), labels=labels,
        templates=templates, sources={"spikeinterface": str(path)},
    )


def _duration_or_last_spike(duration_s: float | None, trains: list[np.ndarray],
                            what: str) -> float:
    if duration_s is not None:
        return float(duration_s)
    last = max((t[-1] for t in trains if len(t)), default=0.0)
    # The last spike underestimates the recording; rates come out slightly
    # high. Only reached when no raw file or .dat was found to measure.
    import warnings
    warnings.warn(f"{what}: recording duration unknown — using the last spike "
                  f"({last:.3f} s); firing rates will be slightly overestimated")
    return float(last)


# ── Into the pipeline's spike file ────────────────────────────────────────────

def layout_coords_from_um(xy_um: np.ndarray) -> tuple[np.ndarray, float]:
    """Positions in µm (y down) → MEA-NAP plot coordinates (y up), and the scale.

    The largest extent of the array maps to :data:`LAYOUT_SPAN`, keeping the
    aspect ratio, so an HD-MEA's nodes are drawn at the size the built-in
    layouts use. Returns ``(coords, units_per_um)``.
    """
    xy = np.asarray(xy_um, dtype=float).reshape(-1, 2)
    if xy.size == 0:
        return xy.copy(), 1.0
    lo, hi = np.nanmin(xy, axis=0), np.nanmax(xy, axis=0)
    span = float(np.max(hi - lo))
    scale = LAYOUT_SPAN / span if span > 0 else 1.0
    coords = np.column_stack([(xy[:, 0] - lo[0]) * scale, (hi[1] - xy[:, 1]) * scale])
    return coords, scale


def _min_spacing(xy: np.ndarray) -> float:
    """Smallest non-zero distance between two electrodes — the array's pitch."""
    from scipy.spatial import cKDTree

    xy = np.unique(np.asarray(xy, float), axis=0)
    if len(xy) < 2:
        return 1.0
    d, _ = cKDTree(xy).query(xy, k=2)
    return float(np.min(d[:, 1]))


@dataclass
class SpikeFileContent:
    """The arguments :func:`~meanap.pipeline.io.save_spike_times_npz` takes."""

    spike_times: dict[int, dict[str, np.ndarray]]
    channels: np.ndarray
    units: dict[str, np.ndarray]
    electrodes: dict[str, np.ndarray]


def to_spike_file(imp: ImportedSorting, drop_labels=DEFAULT_DROP_LABELS) -> SpikeFileContent:
    """Lay an import out as a sorted ``_spikes.npz``, nodes = kept units.

    Spikes outside ``[0, duration)`` are dropped (a sorter that read padding
    can place a few there). Unit IDs follow the in-pipeline sorter's
    ``<electrode>-<rank>`` so a node reads the same whichever way it was made;
    the sorter's own name is kept as ``sorter_unit_id``.
    """
    from meanap.pipeline.spike_sorting import unit_ring_coords

    keep = ~np.isin(imp.labels, list(drop_labels))
    imp = imp.subset(keep)

    elec_coords, scale = layout_coords_from_um(imp.electrodes.xy_um)
    step = _min_spacing(imp.electrodes.xy_um) * scale

    # Order nodes by electrode then sorter ID, as the in-pipeline sorter does.
    order = np.lexsort((np.arange(imp.n_units), imp.peak_index))
    peak = imp.peak_index[order]
    elec_ids = np.asarray(imp.electrodes.ids)
    unit_ids, rank_on = [], {}
    for p in peak:
        rank_on[p] = rank_on.get(p, 0) + 1
        unit_ids.append(f"{elec_ids[p]}-{rank_on[p]}")

    trains = []
    for i in order:
        t = np.asarray(imp.spike_trains[i], dtype=float)
        trains.append(t[(t >= 0) & (t < imp.duration_s)])

    units: dict[str, np.ndarray] = {
        "id": np.array(unit_ids),
        "sorter_unit_id": imp.sorter_unit_ids[order],
        "channel_index": peak,
        "coords": unit_ring_coords(elec_coords[peak], peak, step),
        "label": imp.labels[order],
        "n_spikes": np.array([len(t) for t in trains], dtype=int),
        "firing_rate": np.array([len(t) / imp.duration_s for t in trains], dtype=float),
        "sorter_name": np.array(imp.sorter),
        "source": np.array("import"),
        "sources_json": np.array(json.dumps(imp.sources)),
        "n_units_returned": np.array(len(keep)),
    }
    if imp.templates is not None:
        units["template"] = imp.templates[order].astype(np.float32)
        units["template_times_ms"] = (
            (np.arange(imp.templates.shape[1]) - imp.templates.shape[1] // 2)
            / imp.fs * 1e3).astype(np.float32)
    try:
        channels = elec_ids[peak].astype(np.int64)
    except ValueError:
        # Named channels (a SpikeInterface probe with string IDs): number them.
        channels = peak.astype(np.int64)
    return SpikeFileContent(
        spike_times={i: {SORTED_METHOD: t} for i, t in enumerate(trains)},
        channels=channels, units=units,
        electrodes={"ids": channels_or_index(elec_ids), "coords": elec_coords,
                    "coords_um": np.asarray(imp.electrodes.xy_um, float)},
    )


def channels_or_index(ids: np.ndarray) -> np.ndarray:
    """Electrode IDs as integers, or their row numbers if they are not numbers."""
    try:
        return np.asarray(ids).astype(np.int64)
    except ValueError:
        return np.arange(len(ids), dtype=np.int64)
