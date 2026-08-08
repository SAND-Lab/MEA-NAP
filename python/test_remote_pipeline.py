"""Test running a CAT-NAP batch from a remote source with bounded local disk.

Run from the repo root::

    uv run python python/test_remote_pipeline.py

The claim phase 7 makes is a bound, not a speed-up: *peak local storage is one
or two recordings, whatever the size of the batch*. So the load-bearing check
samples disk usage throughout a run over a dataset several times larger than
the cache budget, and asserts the budget was never exceeded — and that the run
still produced the same results a fully-local run does.

The remote is a fake store backed by a directory, so this needs no network but
exercises the real fetch/pin/evict path (``copies = True``).
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.remote.source import RecordingSource  # noqa: E402
from meanap.params import Params  # noqa: E402
from meanap.remote.cache import FileCache  # noqa: E402
from meanap.remote.local import LocalStore  # noqa: E402
from meanap.remote.prefetch import stream_ahead  # noqa: E402
from meanap.pipeline.spreadsheet import RecordingInfo  # noqa: E402

Check = tuple[str, bool, str]

N_CELLS, N_FRAMES = 8, 300
#: Big enough that a few recordings cannot all be resident at once.
PAD_BYTES = 4_000_000


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


class CopyingStore(LocalStore):
    """A directory pretending to be remote: reads cost a real copy."""

    copies = True

    def fetch(self, path: str, dest: Path, progress=None) -> Path:
        src = self._resolve(path)
        if not src.is_file():
            raise FileNotFoundError(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return dest


def _make_dataset(root: Path, names: list[str]) -> None:
    rng = np.random.default_rng(0)
    for i, name in enumerate(names):
        d = root / name / "suite2p" / "plane0"
        d.mkdir(parents=True)
        np.save(d / "F.npy", rng.random((N_CELLS, N_FRAMES)).astype(np.float32) + 1)
        np.save(d / "spks.npy", rng.random((N_CELLS, N_FRAMES)).astype(np.float32))
        np.save(d / "iscell.npy", np.ones((N_CELLS, 2)))
        np.save(d / "stat.npy",
                np.array([{"med": [int(rng.integers(0, 64)), int(rng.integers(0, 64))]}
                          for _ in range(N_CELLS)], dtype=object), allow_pickle=True)
        # ops carries the bulk, as it does in real suite2p output.
        np.save(d / "ops.npy", np.array(
            {"fs": 30.0, "meanImgE": rng.random((64, 64)),
             "pad": np.zeros(PAD_BYTES // 8)}, dtype=object), allow_pickle=True)
        # Files the pipeline never opens — must not be fetched.
        (d / "F.csv").write_bytes(b"x" * 2_000_000)
        (d / "Fneu.npy").write_bytes(b"x" * 1_000_000)


def _params(tmp: Path, out_name: str, **kw) -> Params:
    p = Params(
        suite2p_mode=True, twop_activity="F", func_con_lag_val=[33],
        min_activity_level=0.0, min_number_of_nodes_to_cal_net_met=2,
        twop_subnetwork_analysis=False, num_2p_traces=0,
        twop_network_background=True, auto_set_cartography_boundaries=False,
        random_seed=3, express_mode=True,
        output_data_folder=str(tmp), output_data_folder_name=out_name,
        derived_data_folder=str(tmp / "derived"),
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _prefetch_checks() -> list[Check]:
    """Ordering, lookahead bound, and failures that don't end the batch."""
    checks: list[Check] = []

    order, in_flight, peak = [], [0], [0]
    lock = threading.Lock()

    def fetch(i: int) -> int:
        with lock:
            in_flight[0] += 1
            peak[0] = max(peak[0], in_flight[0])
        time.sleep(0.01)
        with lock:
            in_flight[0] -= 1
        return i * 10

    for item, value in stream_ahead(range(6), fetch, depth=1):
        order.append((item, value))
        time.sleep(0.02)

    checks.append(("results arrive in the original order",
                   [i for i, _ in order] == list(range(6)), f"{[i for i, _ in order]}"))
    checks.append(("each result matches its item",
                   all(v == i * 10 for i, v in order), ""))
    checks.append(("at most one fetch runs at a time", peak[0] <= 1, f"{peak[0]}"))

    # depth=0 must still work — that is simply "no prefetching".
    serial = list(stream_ahead(range(3), lambda i: i, depth=0))
    checks.append(("depth 0 degrades to serial", [i for i, _ in serial] == [0, 1, 2], ""))

    def flaky(i: int) -> int:
        if i == 1:
            raise OSError("connection reset")
        return i

    got = list(stream_ahead(range(4), flaky, depth=1))
    checks.append(("a failed fetch is handed over, not raised",
                   isinstance(got[1][1], OSError), f"{got[1][1]!r}"))
    checks.append(("…and the rest of the batch still runs",
                   [i for i, _ in got] == [0, 1, 2, 3], ""))
    return checks


def _selective_fetch_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _make_dataset(tmp / "remote", ["rec0"])
        store = CopyingStore(tmp / "remote")
        cache = FileCache(root=tmp / "cache", budget_bytes=200_000_000)
        source = RecordingSource(store=store, cache=cache, log=lambda m: None)

        plane0 = source.plane0("rec0")
        fetched = {p.name for p in plane0.iterdir()}
        checks.append(("the required files are fetched",
                       {"F.npy", "iscell.npy", "stat.npy", "ops.npy"} <= fetched,
                       f"{sorted(fetched)}"))
        checks.append(("files the pipeline never opens are not fetched",
                       "F.csv" not in fetched and "Fneu.npy" not in fetched,
                       f"{sorted(fetched)}"))

        from meanap.catnap.loader import load_suite2p
        data = load_suite2p(plane0, tmp / "derived", "rec0")
        checks.append(("the fetched folder loads as a real recording",
                       data.F.shape == (N_CELLS, N_FRAMES) and data.fs == 30.0,
                       f"{data.F.shape}"))

        before = cache.usage()
        source.release("rec0")
        checks.append(("releasing frees the cache",
                       cache.usage() == 0 and before > 0,
                       f"{before} -> {cache.usage()}"))

        missing = None
        try:
            source.plane0("nope")
        except FileNotFoundError as e:
            missing = str(e)
        checks.append(("a recording with no suite2p output is reported",
                       missing is not None, f"{missing}"))
    return checks


def _bounded_run_checks() -> list[Check]:
    """The claim: a batch far larger than the cache still runs, within budget."""
    from meanap.catnap import pipeline as cp
    from meanap.pipeline.output_folders import create_output_folders

    checks: list[Check] = []
    names = [f"rec{i}" for i in range(6)]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _make_dataset(tmp / "remote", names)
        dataset_bytes = sum(p.stat().st_size
                            for p in (tmp / "remote").rglob("*") if p.is_file())

        store = CopyingStore(tmp / "remote")
        # Room for ~2 recordings, against a dataset of six.
        budget = 12_000_000
        cache = FileCache(root=tmp / "cache", budget_bytes=budget)

        samples = [0]
        stop = threading.Event()

        def sample() -> None:
            while not stop.is_set():
                total = 0
                for p in (tmp / "cache").rglob("*"):
                    try:
                        if p.is_file():
                            total += p.stat().st_size
                    except OSError:
                        pass
                samples[0] = max(samples[0], total)
                time.sleep(0.005)

        watcher = threading.Thread(target=sample, daemon=True)
        watcher.start()
        try:
            out = create_output_folders(tmp, "Remote", ["WT"])
            source = RecordingSource(store=store, cache=cache, log=lambda m: None)
            cp.run_catnap_pipeline(
                _params(tmp, "Remote"),
                [RecordingInfo(filename=n, div=21.0, group="WT") for n in names],
                out, lambda m: None, source=source)
        finally:
            stop.set()
            watcher.join(timeout=2)

        checks.append((f"the dataset is far larger than the budget "
                       f"({dataset_bytes / 1e6:.0f} MB vs {budget / 1e6:.0f} MB)",
                       dataset_bytes > budget * 3, f"{dataset_bytes / 1e6:.0f} MB"))
        checks.append((f"peak cache never exceeded the budget "
                       f"({samples[0] / 1e6:.1f} MB)",
                       samples[0] <= budget, f"{samples[0]} > {budget}"))

        import pandas as pd
        csv = out / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv"
        checks.append(("the run produced results", csv.exists(), ""))
        if csv.exists():
            df = pd.read_csv(csv)
            checks.append((f"every recording was analysed ({len(df)}/6)",
                           set(df["FileName"]) == set(names), f"{sorted(set(df['FileName']))}"))

        checks.append(("the cache is empty when the run ends",
                       cache.usage() == 0, f"{cache.usage()}"))
        checks.append(("nothing was written into the source data",
                       not list((tmp / "remote").rglob("Fdenoised.npy")), ""))

        # The same batch, run locally, must give identical numbers.
        out2 = create_output_folders(tmp, "Local", ["WT"])
        local_source = RecordingSource(
            store=LocalStore(tmp / "remote"), cache=None, log=lambda m: None)
        cp.run_catnap_pipeline(
            _params(tmp, "Local"),
            [RecordingInfo(filename=n, div=21.0, group="WT") for n in names],
            out2, lambda m: None, source=local_source)
        a = pd.read_csv(csv)
        b = pd.read_csv(out2 / "4_NetworkActivity" / "NetworkActivity_RecordingLevel.csv")
        checks.append(("remote and local runs agree exactly",
                       a.equals(b), "CSVs differ"))
    return checks


def _ephys_source_checks() -> list[Check]:
    """The electrophysiology path: one file per recording, sometimes shared.

    An Axion ``.raw`` holds a whole plate and MEA-NAP treats each well as its
    own recording, so several recordings map to one file. Releasing it when the
    first well finishes would re-download it for the next — which is what the
    reference counting exists to prevent.
    """
    checks: list[Check] = []
    MB = 1_000_000
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        remote = tmp / "remote"
        remote.mkdir()
        (remote / "recA.mat").write_bytes(b"m" * 8 * MB)
        (remote / "recB.h5").write_bytes(b"h" * 6 * MB)

        store = CopyingStore(remote)
        cache = FileCache(root=tmp / "cache", budget_bytes=100 * MB)
        source = RecordingSource(store=store, cache=cache, log=lambda m: None)

        got = source.raw_file("recA")
        checks.append((".mat is found and fetched",
                       got.path.exists() and got.path.stat().st_size == 8 * MB,
                       f"{got.path}"))
        checks.append(("no well is set for a single-recording file",
                       got.well is None, f"{got.well}"))
        checks.append((".h5 is found too",
                       source.raw_file("recB").path.stat().st_size == 6 * MB, ""))

        source.release("recA")
        checks.append(("releasing frees just that recording",
                       not cache.path_for(store, "recA.mat").exists()
                       and cache.path_for(store, "recB.h5").exists(), ""))

        missing = None
        try:
            source.raw_file("ghost")
        except FileNotFoundError as e:
            missing = str(e)
        checks.append(("a missing recording names the extensions tried",
                       missing and ".mat" in missing, f"{missing}"))

    with tempfile.TemporaryDirectory() as tmp:
        # One plate, three wells: fetched once, kept until the last well is done.
        tmp = Path(tmp)
        remote = tmp / "remote"
        remote.mkdir()
        (remote / "plate1.raw").write_bytes(b"r" * 20 * MB)
        store = CopyingStore(remote)
        cache = FileCache(root=tmp / "cache", budget_bytes=100 * MB)
        source = RecordingSource(store=store, cache=cache, log=lambda m: None)

        wells = ["plate1_A1", "plate1_A2", "plate1_A3"]
        sources = [source.raw_file(w) for w in wells]
        checks.append(("every well resolves to the one plate file",
                       len({s.path for s in sources}) == 1, ""))
        checks.append(("each well knows which one it is",
                       [s.well for s in sources] == ["A1", "A2", "A3"],
                       f"{[s.well for s in sources]}"))
        checks.append(("the plate is fetched once, not per well",
                       cache.usage() == 20 * MB, f"{cache.usage()}"))

        source.release("plate1_A1")
        checks.append(("the plate survives the first well finishing",
                       cache.path_for(store, "plate1.raw").exists(), ""))
        source.release("plate1_A2")
        checks.append(("…and the second", cache.path_for(store, "plate1.raw").exists(), ""))
        source.release("plate1_A3")
        checks.append(("…and is dropped when the last one is done",
                       not cache.path_for(store, "plate1.raw").exists()
                       and cache.usage() == 0, f"{cache.usage()}"))
    return checks


def _ephys_run_checks() -> list[Check]:
    """A remote electrophysiology run, end to end, within a small budget."""
    import pandas as pd

    from meanap.pipeline.runner import run_pipeline

    checks: list[Check] = []
    REPO = Path("/home/timsit/MEA-NAP")
    dataset = REPO / "local" / "testBurstDetection"
    if not (dataset / "HCNT26_DIV58_E2.mat").exists():
        checks.append(("SKIPPED — example ephys dataset not present", True, ""))
        return checks

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        params = Params(
            raw_data=str(dataset),
            spreadsheet_file_name=str(dataset / "testBurstDetection.csv"),
            spreadsheet_range="2:1000", output_data_folder=str(tmp),
            output_data_folder_name="Local", start_analysis_step=1,
            stop_analysis_step=4, func_con_lag_val=[25], random_seed=1,
            express_mode=True,
        )
        local_out = run_pipeline(params, log=lambda m: None)

        # Now the same data through a store that copies, with a tight budget.
        import meanap.pipeline.runner as runner

        def copying_open_store(p):
            return CopyingStore(p.raw_data)

        runner_open = runner._build_raw_source
        def build(p, log):
            store = CopyingStore(p.raw_data)
            return RecordingSource(
                store=store,
                cache=FileCache(root=Path(p.output_data_folder) / "c",
                                budget_bytes=400_000_000),
                log=log)
        runner._build_raw_source = build
        try:
            params.output_data_folder_name = "Remote"
            remote_out = run_pipeline(params, log=lambda m: None)
        finally:
            runner._build_raw_source = runner_open

        # Both runs are express, so their results live in the bundle rather
        # than in a folder beside it.
        from meanap.pipeline.bundle import open_bundle

        def recording_level(out) -> pd.DataFrame:
            with open_bundle(out) as bundle:
                return pd.read_csv(bundle.root / "4_NetworkActivity"
                                   / "NetworkActivity_RecordingLevel.csv")

        a = recording_level(local_out)
        b = recording_level(remote_out)
        checks.append(("a remote ephys run produces results", len(b) > 0, f"{len(b)}"))
        checks.append(("…identical to the local run", a.equals(b), "CSVs differ"))
        cache = Path(params.output_data_folder) / "c"
        left = sum(p.stat().st_size for p in cache.rglob("*") if p.is_file()) if cache.exists() else 0
        checks.append(("the raw recording is released after step 1",
                       left == 0, f"{left / 1e6:.0f} MB left"))
    return checks


def _name_map_checks() -> list[Check]:
    """Folders renamed away from the spreadsheet resolve without editing either."""
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _make_dataset(tmp / "remote", ["rec0 Some Person"])
        store = CopyingStore(tmp / "remote")
        cache = FileCache(root=tmp / "cache", budget_bytes=200_000_000)

        plain = RecordingSource(store=store, cache=cache, log=lambda m: None)
        failed = False
        try:
            plain.plane0("rec0")
        except FileNotFoundError:
            failed = True
        checks.append(("without a map, a renamed folder is not found", failed, ""))

        mapped = RecordingSource(store=store, cache=cache, log=lambda m: None,
                                 name_map={"rec0": "rec0 Some Person"})
        got = mapped.plane0("rec0")
        checks.append(("with a map, it resolves to the real folder",
                       got.exists() and "Some Person" in str(got), f"{got}"))
        freed = mapped.cache.evict_prefix(store, mapped.folder("rec0"))
        checks.append(("release uses the mapped name too", freed > 0, f"{freed}"))
    return checks


def main() -> int:
    print("=" * 70)
    print("Remote batch: prefetch, eviction, bounded storage")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — prefetch ordering and failures:", _prefetch_checks),
        ("B — fetching only what the pipeline opens:", _selective_fetch_checks),
        ("C — a batch larger than the cache:", _bounded_run_checks),
        ("D — electrophysiology: files, plates and refcounts:", _ephys_source_checks),
        ("E — a remote electrophysiology run:", _ephys_run_checks),
        ("F — renamed folders resolve via the name map:", _name_map_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
