"""Put immunostaining cell types on tracked cells.

A cell-type file lists, per marker, the suite2p ROIs that stained positive and
(in the newer format) the ones that stained negative. Getting those labels onto
a tracked cell comes down to one thing: **the ID spaces differ**.

* The files hold **raw 0-indexed suite2p ROI indices**, and only for ROIs with
  ``iscell == 1``, the same space as CAT-NAP's ``channels`` minus one.
* Tracking works on the **iscell-filtered** ROIs, so a payload's
  ``sessions[k].cluster[i]`` is indexed by position among the iscell ROIs.

So position ``i`` of a session is raw ROI ``flatnonzero(iscell)[i]``. Payloads
written since this module existed carry that mapping as ``sessions[k].roi``.
Older ones need the suite2p ``iscell.npy`` to rebuild it.

**Labels have three states, not two.** A Positive/Negative file leaves some
cells in neither list, for example PV cells in a region where the immunostain
lifted. That is *unknown*, not negative, and treating it as negative is the
mistake a positive-only membership matrix makes. Only when a file has **no**
negative column for a marker (the older ``PutativeCellType`` format) does "not
listed" mean negative.

**Files are checked against the recording before they are trusted.** One file
in the Yin dataset holds another day's ROI list: its IDs run to 382 in a
97-ROI recording. A file whose IDs mostly miss the recording's iscell ROIs is
rejected rather than applied, since spreading those labels would be silently
wrong.

**Cross-day agreement is a check on the tracking.** If the stain was done once,
a tracked cell should carry the same label every day. In Het (mosaic Mecp2)
cultures the Yin dataset agrees 86% against 52% expected by chance; that is
evidence the matcher never used, like the activity fingerprint.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Callable

import numpy as np

#: Encoding of a label, in payloads and in memory.
POS, NEG, UNKNOWN = 1, -1, 0

#: Above this fraction of IDs falling outside the recording's iscell ROIs, a
#: file is taken to belong to some other recording and is rejected. Genuine
#: files in the Yin dataset stay under 5%; the mislabelled one is at 56%.
MAX_OUTSIDE_FRACTION = 0.5

#: ``NeuN_Positive``, ``PV Negative``, ``GAD+``, ``SST-``: a marker with an
#: explicit sign. Anything else holding numbers is a positive-only marker.
_SIGNED = re.compile(
    r"^\s*(?P<marker>.+?)\s*(?:[_ ](?P<word>positive|negative|pos|neg)|(?P<sym>[+\-]))\s*$",
    re.IGNORECASE)


@dataclass
class MarkerLabels:
    """One recording's labels, read from its file: marker → sign per ROI."""

    positive: dict[str, set[int]] = field(default_factory=dict)
    negative: dict[str, set[int]] = field(default_factory=dict)
    #: Markers whose file lists positives only, so "not listed" means negative.
    positive_only: set[str] = field(default_factory=set)
    #: Cells that are in no list are unknown for every other marker.
    junk: int = 0

    @property
    def markers(self) -> list[str]:
        return sorted(set(self.positive) | set(self.negative))

    def ids(self) -> set[int]:
        out: set[int] = set()
        for group in (self.positive, self.negative):
            for s in group.values():
                out |= s
        return out


def _parse_id(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() and number >= 0 else None


def _read_columns(path: Path) -> dict[str, list]:
    """Column name → cells, for a CSV or an Excel sheet.

    CSVs are read with the stdlib: the files carry a byte-order mark and ragged
    rows, which is exactly where a CSV parser's type guessing goes wrong.
    """
    if path.suffix.lower() in (".xlsx", ".xls"):
        import pandas as pd

        df = pd.read_excel(path)
        return {str(c): df[c].tolist() for c in df.columns}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return {}
    header = rows[0]
    return {name: [row[j] if j < len(row) else "" for row in rows[1:]]
            for j, name in enumerate(header) if name.strip()}


def read_marker_labels(path: str | Path) -> MarkerLabels:
    """Read a cell-type file into per-marker positive and negative ID sets.

    ``Comments on …`` columns are skipped by name. Their contents are sometimes
    bare numbers (``"11"``), which a read that keeps every numeric column
    mistakes for a marker.
    """
    labels = MarkerLabels()
    for name, values in _read_columns(Path(path)).items():
        if name.strip().lower().startswith(("comment", "unnamed")):
            continue
        ids, junk = set(), 0
        for v in values:
            parsed = _parse_id(v)
            if parsed is not None:
                ids.add(parsed)
            elif str(v).strip() and str(v).strip().lower() != "nan":
                junk += 1
        labels.junk += junk
        if not ids:
            continue
        m = _SIGNED.match(name)
        if m is None:
            marker, positive = name.strip(), True
        else:
            marker = m.group("marker").strip()
            sign = (m.group("word") or m.group("sym")).lower()
            positive = sign in ("positive", "pos", "+")
        target = labels.positive if positive else labels.negative
        target.setdefault(marker, set()).update(ids)
    labels.positive_only = {m for m in labels.positive if m not in labels.negative}
    return labels


@dataclass
class SessionLabels:
    """One recording's labels, placed on its iscell ROIs."""

    recording: str
    source: str
    #: marker → state per iscell position (``POS``/``NEG``/``UNKNOWN``)
    states: dict[str, np.ndarray]
    outside: int = 0
    conflicts: int = 0


def place_labels(labels: MarkerLabels, roi_index: np.ndarray, *,
                 recording: str = "", source: str = "") -> SessionLabels:
    """Map a file's raw ROI IDs onto a session's iscell positions.

    Raises ``ValueError`` when the file cannot belong to this recording (see
    :data:`MAX_OUTSIDE_FRACTION`), so the caller can report it by name.
    """
    roi_index = np.asarray(roi_index, dtype=int)
    position = {int(r): i for i, r in enumerate(roi_index)}
    ids = labels.ids()
    outside = sum(1 for i in ids if i not in position)
    if ids and outside / len(ids) > MAX_OUTSIDE_FRACTION:
        raise ValueError(
            f"{outside} of {len(ids)} ROI IDs are not iscell ROIs of this "
            f"recording (max ID {max(ids)}, {len(roi_index)} iscell ROIs); "
            "the file looks like it belongs to another recording")
    if labels.junk > len(ids):
        raise ValueError(f"{labels.junk} entries are not ROI IDs")

    states: dict[str, np.ndarray] = {}
    conflicts = 0
    for marker in labels.markers:
        pos = labels.positive.get(marker, set())
        neg = labels.negative.get(marker, set())
        default = NEG if marker in labels.positive_only else UNKNOWN
        s = np.full(len(roi_index), default, dtype=np.int8)
        for i in neg:
            if i in position:
                s[position[i]] = NEG
        for i in pos:
            if i in position:
                s[position[i]] = POS
        # listed as both: the annotator was unsure, so neither sign is trusted
        both = [position[i] for i in pos & neg if i in position]
        s[both] = UNKNOWN
        conflicts += len(both)
        states[marker] = s
    return SessionLabels(recording=recording, source=source, states=states,
                         outside=outside, conflicts=conflicts)


# ── finding files ─────────────────────────────────────────────────────────────

def find_label_file(recording: str, folders) -> Path | None:
    """A recording's cell-type file in any of *folders*.

    Two layouts are accepted: flat ``<folder>/<recording>.csv`` (how the Yin
    dataset ships them) and CAT-NAP's ``<rawData>/<recording>/*.csv``. CSV is
    preferred to Excel when both exist. In the Yin dataset 29 of the ``.xlsx``
    twins cannot be opened at all and several hold another day's list.
    """
    from meanap.catnap.subnetwork import find_cell_type_file

    for folder in folders:
        if not folder:
            continue
        folder = Path(folder)
        if folder.is_file():
            return folder
        for ext in (".csv", ".xlsx", ".xls"):
            flat = folder / f"{recording}{ext}"
            if flat.is_file():
                return flat
        nested = find_cell_type_file(folder, recording)
        if nested is not None:
            return nested
    return None


def label_index(folders) -> dict[tuple[str, int], str]:
    """``(chain, div)`` → recording, from the file names in flat folders.

    Old payloads do not record which recording each day came from; the label
    files' own names say, once parsed the way the chains were built.
    """
    from meanap.catnap.tracking.chains import parse_recording

    out: dict[tuple[str, int], str] = {}
    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            name = path.stem if path.is_file() else path.name
            if path.is_file() and path.suffix.lower() not in (".csv", ".xlsx", ".xls"):
                continue
            try:
                rec = parse_recording(name)
            except Exception:
                continue
            out.setdefault((rec.chain, rec.div), name)
    return out


def iscell_index(recording: str, roots) -> np.ndarray | None:
    """Raw indices of the iscell ROIs, from the first root holding ``iscell.npy``."""
    for root in roots:
        if not root:
            continue
        for rel in ("", "plane0", "suite2p/plane0"):
            path = Path(root) / recording / rel / "iscell.npy"
            if path.is_file():
                return np.flatnonzero(np.load(path)[:, 0] > 0)
    return None


def iscell_stat(recording: str, roots):
    """The iscell-filtered ``stat.npy``, in tracking's position order, or ``None``."""
    for root in roots:
        if not root:
            continue
        for rel in ("", "plane0", "suite2p/plane0"):
            folder = Path(root) / recording / rel
            if (folder / "stat.npy").is_file() and (folder / "iscell.npy").is_file():
                stat = np.load(folder / "stat.npy", allow_pickle=True)
                iscell = np.load(folder / "iscell.npy")[:, 0] > 0
                return stat[iscell] if len(stat) == len(iscell) else None
    return None


# ── annotating ────────────────────────────────────────────────────────────────

def cell_call(states: list[int]) -> str | None:
    """One label for a tracked cell across its days.

    ``"+"``/``"-"`` when every labelled day agrees, ``"~"`` when they disagree,
    which is either a wrong match or a wrong label. ``None`` when no day is
    labelled.
    """
    known = {s for s in states if s != UNKNOWN}
    if not known:
        return None
    if len(known) > 1:
        return "~"
    return "+" if known.pop() == POS else "-"


#: A day that tracking reached only by fallback -- added by position after
#: ROICaT, or joined from a split cluster -- counts this much in the vote. When
#: a label flips on such a day, the match is the likelier error, not the stain.
FALLBACK_DAY_WEIGHT = 0.5

#: Markers the culture's genotype decides outright. Every cell in a WT culture
#: carries a working Mecp2 and none in a KO does, so there a disagreeing label
#: is a staining or annotation error, whatever the vote says. Het cultures are
#: mosaic and are left to the labels.
GENOTYPE_FIXED = {"Mecp2": {"WT": "+", "KO": "-"}}


def recommend(states: list[int], *, weights: list[float] | None = None,
              genotype: str = "", marker: str = "") -> dict:
    """The best guess at one cell's true label for one marker, with why.

    ``call`` is ``"+"``, ``"-"`` or ``None`` (undecided, or never labelled).
    A tie is left undecided on purpose: two days disagreeing one-to-one carry
    no information about which is right, and a coin flip dressed as a
    recommendation would hide the cells that most need a person to look.
    """
    weights = weights or [1.0] * len(states)
    known = [(s, w) for s, w in zip(states, weights) if s != UNKNOWN]
    n_pos = sum(1 for s, _ in known if s == POS)
    n_neg = len(known) - n_pos
    out = {"pos": n_pos, "neg": n_neg}
    fixed = GENOTYPE_FIXED.get(marker, {}).get(genotype)
    if fixed:
        return {**out, "call": fixed, "conf": 1.0, "reason": "genotype"}
    if not known:
        return {**out, "call": None, "conf": None, "reason": "unlabelled"}
    wp = sum(w for s, w in known if s == POS)
    wn = sum(w for s, w in known if s == NEG)
    if wp == wn:
        return {**out, "call": None, "conf": 0.5, "reason": "tie"}
    return {**out, "call": "+" if wp > wn else "-",
            "conf": round(max(wp, wn) / (wp + wn), 3),
            "reason": "unanimous" if min(n_pos, n_neg) == 0 else "majority"}


def annotate_payload(payload: dict, session_labels: list[SessionLabels | None],
                     *, genotype: str = "") -> dict:
    """Attach labels to a viewer payload, in place, and return a chain summary.

    Adds ``markers`` at the top; ``labels`` (marker → state per ROI) and
    ``labelSource`` to each labelled session; and ``types`` (marker → state per
    day, aligned with ``divs``) plus ``typeCall`` (marker → ``+``/``-``/``~``)
    to each cell.
    """
    sessions = payload["sessions"]
    markers = sorted({m for sl in session_labels if sl for m in sl.states})
    payload["markers"] = markers
    for s, sl in zip(sessions, session_labels):
        s.pop("labels", None)
        s.pop("labelSource", None)
        if sl is None:
            continue
        s["labels"] = {m: [int(v) for v in st] for m, st in sl.states.items()}
        s["labelSource"] = sl.source

    where = [{int(c): i for i, c in enumerate(s["cluster"]) if c >= 0} for s in sessions]
    for cell in payload["cells"]:
        types: dict[str, list[int]] = {m: [] for m in markers}
        for si, _y, _x in cell["positions"]:
            sl = session_labels[si]
            i = where[si].get(int(cell["cluster"]))
            for m in markers:
                st = sl.states.get(m) if sl is not None else None
                types[m].append(int(st[i]) if st is not None and i is not None else UNKNOWN)
        cell["types"] = types
        cell["typeCall"] = {m: cell_call(v) for m, v in types.items()}
        fallback = set(cell.get("rescuedDivs", [])) | set(cell.get("mergedDivs", []))
        weights = [FALLBACK_DAY_WEIGHT if d in fallback else 1.0 for d in cell["divs"]]
        cell["typeRec"] = {m: recommend(v, weights=weights, genotype=genotype, marker=m)
                           for m, v in types.items()}
    return chain_agreement(payload, session_labels)


def chain_agreement(payload: dict, session_labels) -> dict:
    """Per marker: how often a tracked cell keeps its label from day to day.

    Chance is what two days with the same label frequencies would agree on if
    the matches were random, ``p₁p₂ + (1−p₁)(1−p₂)`` per day pair. A marker
    that is uniform in a culture (Mecp2 in WT or KO) agrees perfectly at chance
    and says nothing; the mosaic Het cultures are where this has power.
    """
    out: dict[str, dict] = {}
    sessions = payload["sessions"]
    where = [{int(c): i for i, c in enumerate(s["cluster"]) if c >= 0} for s in sessions]
    for m in payload.get("markers", []):
        pairs = agree = 0
        chance = 0.0
        for a, b in combinations(range(len(sessions)), 2):
            la, lb = session_labels[a], session_labels[b]
            if la is None or lb is None or m not in la.states or m not in lb.states:
                continue
            A, B = [], []
            for c, i in where[a].items():
                j = where[b].get(c)
                if j is None:
                    continue
                sa, sb = la.states[m][i], lb.states[m][j]
                if sa != UNKNOWN and sb != UNKNOWN:
                    A.append(sa == POS)
                    B.append(sb == POS)
            if not A:
                continue
            A, B = np.array(A), np.array(B)
            pairs += len(A)
            agree += int((A == B).sum())
            pa, pb = A.mean(), B.mean()
            chance += (pa * pb + (1 - pa) * (1 - pb)) * len(A)
        if pairs:
            out[m] = {"pairs": pairs, "agree": agree, "chance": round(chance, 3)}
    return out


@dataclass
class AnnotateReport:
    """What happened to each chain, for the log and for ``summary.json``."""

    chains: int = 0
    labelled_chains: int = 0
    labelled_days: int = 0
    missing_days: list[str] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    #: label files matched by chain and DIV because their name disagreed
    renamed: list[str] = field(default_factory=list)
    #: (marker, genotype) → pooled agreement counts
    agreement: dict = field(default_factory=dict)

    def summary(self) -> dict:
        agreement = {}
        for (m, g), v in sorted(self.agreement.items()):
            agreement.setdefault(m, {})[g] = {
                "pairs": v["pairs"],
                "agreement": round(v["agree"] / v["pairs"], 4),
                "chance": round(v["chance"] / v["pairs"], 4),
            }
        return {"labelled_chains": self.labelled_chains,
                "labelled_days": self.labelled_days,
                "rejected_files": self.rejected,
                "matched_by_chain_and_div": self.renamed,
                "label_agreement": agreement}


def annotate_tracking_dir(
    tracking_dir: str | Path,
    label_folders,
    *,
    suite2p_roots=(),
    rerender: bool = True,
    log: Callable[[str], None] = lambda _msg: None,
) -> AnnotateReport:
    """Label every tracked cell in a ``CellTracking`` folder.

    Rewrites ``payload/*.json`` (and ``viewer/*.html`` when *rerender*), adds a
    ``cell_types`` block to ``chains/*.json`` and ``summary.json``, and writes
    ``cell_types.csv``, one row per tracked cell, day and marker.

    Safe to run again: every annotation is replaced, not appended to.
    """
    from meanap.catnap.tracking.viewer import render_page

    root = Path(tracking_dir)
    label_folders = [Path(f) for f in label_folders if f]
    by_day = label_index(label_folders)
    # the recordings themselves, for runs whose payloads do not name them: a
    # label file's own name can disagree on the imaging date (one Yin file says
    # 20240621 for a recording dated 20240624), so the file is only trusted
    # for which chain and DIV it covers
    recordings_by_day = label_index(suite2p_roots)
    report = AnnotateReport()
    rows: list[dict] = []
    cell_rows: list[dict] = []

    for payload_path in sorted((root / "payload").glob("*.json")):
        payload = json.loads(payload_path.read_text())
        key = payload.get("chainKey", payload_path.stem)
        report.chains += 1
        genotype = _genotype(root, key)

        session_labels: list[SessionLabels | None] = []
        for s in payload["sessions"]:
            div = int(s["div"])
            recording = (s.get("recording") or recordings_by_day.get((key, div))
                         or by_day.get((key, div)))
            sl = None
            path = find_label_file(recording, label_folders) if recording else None
            if path is None and (key, div) in by_day:
                path = find_label_file(by_day[(key, div)], label_folders)
                if path is not None:
                    report.renamed.append(f"{path.name} used for {recording}")
            if path is None:
                report.missing_days.append(f"{key} DIV{div}")
            else:
                roi = (np.asarray(s["roi"], dtype=int) if s.get("roi") is not None
                       else iscell_index(recording, suite2p_roots))
                if roi is None:
                    report.rejected.append({"chain": key, "div": div, "file": path.name,
                                            "reason": "no iscell.npy to map ROI IDs"})
                elif len(roi) != len(s["cluster"]):
                    report.rejected.append({
                        "chain": key, "div": div, "file": path.name,
                        "reason": f"{len(roi)} iscell ROIs but the session has "
                                  f"{len(s['cluster'])}"})
                else:
                    try:
                        sl = place_labels(read_marker_labels(path), roi,
                                          recording=recording, source=path.name)
                    except Exception as e:  # a bad file must not stop the rest
                        report.rejected.append({"chain": key, "div": div,
                                                "file": path.name, "reason": str(e)})
                    else:
                        s["recording"] = recording
                        s["roi"] = [int(r) for r in roi]
            session_labels.append(sl)
            # payloads from before cell types lack the ROI index image that lets
            # the page colour masks by label; build it from stat.npy if we can
            if not s.get("masksIdPng") and recording and payload.get("frame"):
                stat = iscell_stat(recording, suite2p_roots)
                if stat is not None and len(stat) == len(s["cluster"]):
                    from meanap.catnap.tracking.viewer import roi_id_png

                    s["masksIdPng"] = roi_id_png(stat, int(payload["frame"]))

        agreement = annotate_payload(payload, session_labels, genotype=genotype)
        payload["genotype"] = genotype
        labelled = [int(s["div"]) for s, sl in zip(payload["sessions"], session_labels) if sl]
        report.labelled_days += len(labelled)
        report.labelled_chains += bool(labelled)
        for m, v in agreement.items():
            pooled = report.agreement.setdefault((m, genotype or "?"),
                                                 {"pairs": 0, "agree": 0, "chance": 0.0})
            for k in pooled:
                pooled[k] += v[k]

        payload_path.write_text(json.dumps(payload))
        if rerender and (root / "viewer").is_dir():
            (root / "viewer" / f"{key}.html").write_text(render_page(payload))
        _update_chain_meta(root, key, {
            "nodes": _node_labels(root, key, payload),
            "markers": payload["markers"],
            "labelled_divs": labelled,
            "unlabelled_divs": [int(s["div"]) for s, sl
                                in zip(payload["sessions"], session_labels) if sl is None],
            "agreement": agreement,
        })
        rows.extend(_rows(key, genotype, payload, session_labels))
        cell_rows.extend(_cell_rows(key, genotype, payload))

    _write_rows(root / "cell_types.csv", rows)
    _write_cell_rows(root / CELLS_CSV, cell_rows)
    # a relabel changes the recommendations, so the final table follows
    write_final_csv(root / CELLS_CSV, load_overrides(root / OVERRIDES_FILE),
                    root / FINAL_CSV)
    summary_path = root / "summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text())
        summary["cell_types"] = report.summary()
        summary_path.write_text(json.dumps(summary, indent=1))
    log(f"Cell types: {report.labelled_days} days in {report.labelled_chains} of "
        f"{report.chains} chains labelled; {len(report.rejected)} files rejected.")
    for r in report.rejected:
        log(f"  rejected {r['file']} ({r['chain']} DIV{r['div']}): {r['reason']}")
    for note in report.renamed:
        log(f"  name differs, matched on chain and DIV: {note}")
    return report


def _genotype(root: Path, key: str) -> str:
    meta = root / "chains" / f"{key}.json"
    if meta.is_file():
        return json.loads(meta.read_text()).get("genotype", "")
    from meanap.catnap.tracking.chains import GENOTYPES

    return next((g for g in GENOTYPES if f"_{g}_" in f"_{key}_"), "")


def _node_labels(root: Path, key: str, payload: dict) -> dict | None:
    """Labels for the network view's nodes, keyed the way the network is.

    Nodes are the cells tracked into two or more days, sorted by cluster id
    (``pipeline._network_summary``). Networks written before they carried
    ``clusters`` are matched by rebuilding that list, and skipped if the count
    disagrees rather than risk labelling the wrong nodes.
    """
    meta_path = root / "chains" / f"{key}.json"
    if not meta_path.is_file():
        return None
    network = json.loads(meta_path.read_text()).get("network") or {}
    if not network.get("days"):
        return None
    clusters = network.get("clusters")
    if clusters is None:
        days_of: dict[int, int] = {}
        for s in payload["sessions"]:
            for c in {int(c) for c in s["cluster"] if c >= 0}:
                days_of[c] = days_of.get(c, 0) + 1
        clusters = sorted(c for c, n in days_of.items() if n >= 2)
        if len(clusters) != network.get("nCells"):
            return None
    by_cluster = {int(c["cluster"]): c for c in payload["cells"]}
    n_days = len(payload["sessions"])
    states = {m: [] for m in payload["markers"]}
    calls = {m: [] for m in payload["markers"]}
    recs = {m: [] for m in payload["markers"]}
    for c in clusters:
        cell = by_cluster.get(int(c))
        for m in payload["markers"]:
            per_day = [UNKNOWN] * n_days
            if cell is not None:
                for (si, _y, _x), v in zip(cell["positions"], cell["types"][m]):
                    per_day[si] = v
            states[m].append(per_day)
            calls[m].append(cell["typeCall"][m] if cell is not None else None)
            recs[m].append(cell["typeRec"][m]["call"] if cell is not None else None)
    return {"clusters": [int(c) for c in clusters], "states": states,
            "calls": calls, "rec": recs}


def _update_chain_meta(root: Path, key: str, block: dict) -> None:
    meta_path = root / "chains" / f"{key}.json"
    if not meta_path.is_file():
        return
    meta = json.loads(meta_path.read_text())
    meta["cell_types"] = block
    meta_path.write_text(json.dumps(meta, indent=1))


def _cell_rows(key, genotype, payload) -> list[dict]:
    """One row per tracked cell and marker: the days, the raw call, the guess."""
    rows = []
    for cell in payload["cells"]:
        for m in payload["markers"]:
            rec = cell["typeRec"][m]
            rows.append({
                "chain": key, "genotype": genotype, "cluster": cell["cluster"],
                "marker": m,
                "days": " ".join(f"DIV{d}:{ {POS: '+', NEG: '-'}.get(v, '?') }"
                                 for d, v in zip(cell["divs"], cell["types"][m])),
                "raw_call": cell["typeCall"][m] or "",
                "recommendation": rec["call"] or "",
                "confidence": "" if rec["conf"] is None else rec["conf"],
                "reason": rec["reason"],
            })
    return rows


def _write_cell_rows(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CELL_FIELDS)
        w.writeheader()
        w.writerows(rows)


# ── manual overrides ──────────────────────────────────────────────────────────

#: Where overrides live in a CellTracking folder. Kept out of the payloads so a
#: relabel (``annotate_tracking_dir``) never discards a person's decisions.
OVERRIDES_FILE = "cell_type_overrides.json"
CELLS_CSV = "cell_types_cells.csv"
FINAL_CSV = "cell_types_final.csv"
CELL_FIELDS = ["chain", "genotype", "cluster", "marker", "days", "raw_call",
               "recommendation", "confidence", "reason"]
#: What an override may say. ``"?"`` is a decision too: "cannot tell".
OVERRIDE_VALUES = ("+", "-", "?")


def load_overrides(path: str | Path) -> dict:
    """``{chain: {cluster (str): {marker: value}}}``; empty if there is no file."""
    path = Path(path)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    return {chain: {str(c): {m: e["value"] for m, e in markers.items()}
                    for c, markers in clusters.items()}
            for chain, clusters in data.get("chains", {}).items()}


def set_override(path: str | Path, chain: str, cluster: int, marker: str,
                 value: str | None, *, note: str = "") -> dict:
    """Record (or with ``value=None``, clear) one decision; returns the chain's.

    Written atomically, since the viewer can be closed mid-save and a torn
    JSON file would lose every decision in it.
    """
    from datetime import datetime, timezone

    if value is not None and value not in OVERRIDE_VALUES:
        raise ValueError(f"override must be one of {OVERRIDE_VALUES} or null, not {value!r}")
    path = Path(path)
    data = json.loads(path.read_text()) if path.is_file() else {}
    data.setdefault("version", 1)
    chains = data.setdefault("chains", {})
    cell = chains.setdefault(chain, {}).setdefault(str(int(cluster)), {})
    if value is None:
        cell.pop(marker, None)
    else:
        cell[marker] = {"value": value,
                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        **({"note": note} if note else {})}
    if not cell:
        chains[chain].pop(str(int(cluster)))
    if not chains[chain]:
        chains.pop(chain)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)
    return load_overrides(path).get(chain, {})


def final_call(recommendation: str | None, override: str | None) -> str | None:
    """What a cell is taken to be: the person's decision, else the guess."""
    if override is not None:
        return None if override == "?" else override
    return recommendation or None


def write_final_csv(cells_csv: str | Path, overrides: dict, out: str | Path) -> None:
    """The per-cell table with each decision and the resulting call.

    ``final`` is what analysis should use: blank means undecided or unlabelled.
    ``source`` says whether it came from the recommendation or a person.
    """
    cells_csv = Path(cells_csv)
    if not cells_csv.is_file():
        return
    with open(cells_csv, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        ov = overrides.get(r["chain"], {}).get(str(r["cluster"]), {}).get(r["marker"])
        r["override"] = ov or ""
        r["final"] = final_call(r["recommendation"] or None, ov) or ""
        r["source"] = "manual" if ov else ("recommendation" if r["recommendation"] else "")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CELL_FIELDS + ["override", "final", "source"])
        w.writeheader()
        w.writerows(rows)


def _rows(key, genotype, payload, session_labels) -> list[dict]:
    rows = []
    for cell in payload["cells"]:
        for k, (si, _y, _x) in enumerate(cell["positions"]):
            sl = session_labels[si]
            if sl is None:
                continue
            s = payload["sessions"][si]
            pos = [i for i, c in enumerate(s["cluster"]) if c == cell["cluster"]]
            roi = s["roi"][pos[0]] if pos and s.get("roi") else ""
            for m in payload["markers"]:
                state = cell["types"][m][k]
                rows.append({
                    "chain": key, "genotype": genotype, "cluster": cell["cluster"],
                    "div": cell["divs"][k], "recording": sl.recording, "roi": roi,
                    "marker": m,
                    "state": {POS: "+", NEG: "-"}.get(state, ""),
                    "cell_call": cell["typeCall"][m] or "",
                })
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    fields = ["chain", "genotype", "cluster", "div", "recording", "roi",
              "marker", "state", "cell_call"]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    """Label an existing run's tracked cells without re-tracking.

        python -m meanap.catnap.tracking.celltypes <run>/CellTracking \\
            --labels <cell-type folder> --suite2p <suite2p root>

    ``--suite2p`` is only needed for runs from before payloads recorded each
    day's raw ROI indices; it is searched for ``<recording>/iscell.npy``,
    ``<recording>/plane0/`` and ``<recording>/suite2p/plane0/``.
    """
    import argparse

    ap = argparse.ArgumentParser(prog="meanap.catnap.tracking.celltypes",
                                 description=main.__doc__.split("\n")[0])
    ap.add_argument("tracking_dir", type=Path,
                    help="a CellTracking folder, or the run folder holding one")
    ap.add_argument("--labels", type=Path, action="append", required=True,
                    help="folder of <recording>.csv cell-type files (repeatable)")
    ap.add_argument("--suite2p", type=Path, action="append", default=[],
                    help="root holding each recording's iscell.npy (repeatable)")
    ap.add_argument("--no-render", action="store_true",
                    help="update the payloads but not viewer/*.html")
    args = ap.parse_args(argv)

    root = args.tracking_dir
    if not (root / "payload").is_dir() and (root / "CellTracking" / "payload").is_dir():
        root = root / "CellTracking"
    if not (root / "payload").is_dir():
        ap.error(f"{args.tracking_dir} has no payload/ folder")
    report = annotate_tracking_dir(root, args.labels, suite2p_roots=args.suite2p,
                                   rerender=not args.no_render, log=print)
    for marker, by_geno in report.summary()["label_agreement"].items():
        for geno, v in by_geno.items():
            print(f"  {marker:6s} {geno:4s} tracked pairs agree {v['agreement']:.3f} "
                  f"(chance {v['chance']:.3f}, n={v['pairs']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
