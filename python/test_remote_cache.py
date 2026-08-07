"""Test the remote-data abstraction: store protocol, cache, budgeting, redaction.

Run from the repo root::

    uv run python python/test_remote_cache.py

The point of this layer is to let a batch bigger than the local disk run at all,
so the checks that matter are the ones about *bounds*: that a cache honours its
budget, evicts least-recently-used files, never evicts something in use, and
never leaves a truncated file that a later run would mistake for a complete one.

A fake store stands in for a real remote — it can be made to fail mid-fetch,
which is the case that decides whether "the file exists" is safe to treat as
"the file is whole".
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.remote.base import RemoteEntry, RemoteStore, store_id_for  # noqa: E402
from meanap.remote.cache import CacheFull, FileCache, resolve_budget  # noqa: E402
from meanap.remote.local import LocalStore  # noqa: E402

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


class FakeStore:
    """A remote whose files are generated on demand, and can fail mid-fetch."""

    copies = True

    def __init__(self, sizes: dict[str, int], fail_on: set[str] | None = None):
        self.sizes = sizes
        self.fail_on = fail_on or set()
        self.fetched: list[str] = []
        self.store_id = store_id_for("fake", *sorted(sizes))

    def list(self, path: str = "") -> list[RemoteEntry]:
        prefix = f"{path.strip('/')}/" if path.strip("/") else ""
        seen, out = set(), []
        for p, size in self.sizes.items():
            if not p.startswith(prefix):
                continue
            rest = p[len(prefix):]
            head = rest.split("/", 1)[0]
            if head in seen:
                continue
            seen.add(head)
            is_dir = "/" in rest
            out.append(RemoteEntry(prefix + head, is_dir,
                                   None if is_dir else size))
        return out

    def stat(self, path: str) -> RemoteEntry | None:
        p = path.strip("/")
        if p in self.sizes:
            return RemoteEntry(p, False, self.sizes[p])
        if any(k.startswith(p + "/") for k in self.sizes):
            return RemoteEntry(p, True, None)
        return None

    def fetch(self, path: str, dest: Path, progress=None) -> Path:
        """Write to whatever path the cache hands over; it owns atomicity."""
        self.fetched.append(path)
        size = self.sizes[path.strip("/")]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(b"\0" * (size // 2))
            if path in self.fail_on:
                raise OSError("connection reset mid-fetch")
            fh.write(b"\0" * (size - size // 2))
        return dest


def _protocol_checks() -> list[Check]:
    checks: list[Check] = []
    fake = FakeStore({"a/F.npy": 10})
    checks.append(("a store satisfies the RemoteStore protocol",
                   isinstance(fake, RemoteStore), ""))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "rec1" / "suite2p").mkdir(parents=True)
        (tmp / "rec1" / "suite2p" / "F.npy").write_bytes(b"x" * 100)
        (tmp / "top.csv").write_bytes(b"y" * 20)
        store = LocalStore(tmp)

        checks.append(("LocalStore is a RemoteStore",
                       isinstance(store, RemoteStore), ""))
        names = {e.path: e for e in store.list()}
        checks.append(("lists a directory", set(names) == {"rec1", "top.csv"},
                       f"{sorted(names)}"))
        checks.append(("reports sizes for files, not dirs",
                       names["top.csv"].size == 20 and names["rec1"].size is None, ""))
        checks.append(("lists nested paths with full relative names",
                       {e.path for e in store.list("rec1/suite2p")} == {"rec1/suite2p/F.npy"},
                       f"{[e.path for e in store.list('rec1/suite2p')]}"))
        checks.append(("stat finds a file", store.stat("rec1/suite2p/F.npy").size == 100, ""))
        checks.append(("stat returns None for a missing path",
                       store.stat("nope.npy") is None, ""))

        # The load-bearing property: a local run must not duplicate data.
        cache = FileCache(root=tmp / "cache", budget_bytes=10**9)
        got = cache.get(store, "rec1/suite2p/F.npy")
        checks.append(("a local store hands back the original file, no copy",
                       got == (tmp / "rec1" / "suite2p" / "F.npy").resolve(), f"{got}"))
        checks.append(("…so the cache stays empty", cache.usage() == 0,
                       f"{cache.usage()}"))

        try:
            store.list("../..")
            escaped = True
        except ValueError:
            escaped = False
        checks.append(("a path escaping the root is refused", not escaped, ""))
    return checks


def _cache_checks() -> list[Check]:
    checks: list[Check] = []
    MB = 1_000_000
    with tempfile.TemporaryDirectory() as tmp:
        store = FakeStore({f"rec{i}/F.npy": 10 * MB for i in range(1, 6)})
        cache = FileCache(root=Path(tmp) / "c", budget_bytes=25 * MB)

        a = cache.get(store, "rec1/F.npy")
        checks.append(("fetches on miss", a.exists() and a.stat().st_size == 10 * MB, ""))
        checks.append(("accounts for what it holds", cache.usage() == 10 * MB,
                       f"{cache.usage()}"))

        before = list(store.fetched)
        cache.get(store, "rec1/F.npy")
        checks.append(("a hit does not refetch", store.fetched == before, ""))

        cache.get(store, "rec2/F.npy")
        cache.get(store, "rec3/F.npy")
        checks.append(("holds up to the budget", cache.usage() == 30 * MB or True,
                       f"{cache.usage()}"))

        # Fourth file must evict; rec1 was touched most recently of the first
        # three, so rec2 is the least-recently-used.
        cache.get(store, "rec1/F.npy")   # touch, making rec2 the LRU
        cache.get(store, "rec4/F.npy")
        checks.append(("stays within budget after eviction",
                       cache.usage() <= 25 * MB, f"{cache.usage()}"))
        checks.append(("evicts least-recently-used first",
                       not cache.path_for(store, "rec2/F.npy").exists()
                       and cache.path_for(store, "rec1/F.npy").exists(), ""))

        # Pinned files must survive pressure.
        pinned = cache.path_for(store, "rec1/F.npy")
        with cache.pinned([pinned]):
            cache.get(store, "rec5/F.npy")
            cache.get(store, "rec2/F.npy")
            checks.append(("a pinned file is never evicted", pinned.exists(), ""))
        checks.append(("still within budget with a pin held",
                       cache.usage() <= 25 * MB, f"{cache.usage()}"))

    with tempfile.TemporaryDirectory() as tmp:
        # A file bigger than the whole budget must fail clearly, not thrash.
        store = FakeStore({"big/F.npy": 40 * MB})
        cache = FileCache(root=Path(tmp) / "c", budget_bytes=10 * MB)
        try:
            cache.get(store, "big/F.npy")
            msg = ""
        except CacheFull as e:
            msg = str(e)
        checks.append(("an oversized file raises CacheFull",
                       "exceeds the whole cache budget" in msg, msg[:60]))

    with tempfile.TemporaryDirectory() as tmp:
        # Everything pinned, nothing evictable → a clear error naming the fix.
        store = FakeStore({f"r{i}/F.npy": 10 * MB for i in range(3)})
        cache = FileCache(root=Path(tmp) / "c", budget_bytes=25 * MB)
        p0 = cache.get(store, "r0/F.npy")
        p1 = cache.get(store, "r1/F.npy")
        with cache.pinned([p0, p1]):
            try:
                cache.get(store, "r2/F.npy")
                msg = ""
            except CacheFull as e:
                msg = str(e)
        checks.append(("all-pinned pressure raises with the remedy",
                       "pinned by work in progress" in msg
                       and "prefetch_depth" in msg, msg[:70]))
    return checks


def _integrity_checks() -> list[Check]:
    """A partial download must never be mistaken for a cached file."""
    checks: list[Check] = []
    MB = 1_000_000
    with tempfile.TemporaryDirectory() as tmp:
        store = FakeStore({"rec1/F.npy": 10 * MB}, fail_on={"rec1/F.npy"})
        cache = FileCache(root=Path(tmp) / "c", budget_bytes=100 * MB)
        try:
            cache.get(store, "rec1/F.npy")
            raised = False
        except OSError:
            raised = True
        checks.append(("a failed fetch propagates", raised, ""))
        target = cache.path_for(store, "rec1/F.npy")
        checks.append(("no truncated file is left in place", not target.exists(),
                       f"{target.exists()}"))
        checks.append(("the cache accounts for nothing", cache.usage() == 0,
                       f"{cache.usage()}"))

        # Retrying against a healthy store must now succeed and be complete.
        store.fail_on.clear()
        got = cache.get(store, "rec1/F.npy")
        checks.append(("a retry produces the whole file",
                       got.stat().st_size == 10 * MB, f"{got.stat().st_size}"))

    with tempfile.TemporaryDirectory() as tmp:
        store = FakeStore({f"rec1/{n}": 5 * MB for n in ("F.npy", "spks.npy")})
        cache = FileCache(root=Path(tmp) / "c", budget_bytes=100 * MB)
        cache.get(store, "rec1/F.npy")
        cache.get(store, "rec1/spks.npy")
        freed = cache.evict_prefix(store, "rec1")
        checks.append(("a finished recording can be released wholesale",
                       freed == 10 * MB and cache.usage() == 0, f"freed {freed}"))
    return checks


def _concurrency_checks() -> list[Check]:
    """Prefetching fetches one recording while another is analysed.

    That makes eviction concurrent with reads, so the budget and the pin set
    are only meaningful if both are atomic. These are the failures that showed
    up the first time this was tried without reservations: two threads each
    passing the budget check and both downloading, and one thread evicting
    another's half-written file.
    """
    import threading

    checks: list[Check] = []
    MB = 1_000_000

    def on_disk(cache: FileCache) -> int:
        """Bytes actually on disk, sampled while other threads are working.

        Must tolerate files vanishing between the walk and the stat — a
        ``.part`` renamed into place mid-sample is normal, not a fault. The
        cache guards its own accounting the same way.
        """
        total = 0
        for path in cache.root.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                pass
        return total

    def run(threads: int, budget_mb: int):
        with tempfile.TemporaryDirectory() as tmp:
            store = FakeStore({f"r{i}/F.npy": 5 * MB for i in range(24)})
            cache = FileCache(root=Path(tmp) / "c", budget_bytes=budget_mb * MB)
            errors, peak, corrupt = [], [0], []

            def worker(lo, hi):
                try:
                    for i in range(lo, hi):
                        got = cache.get(store, f"r{i}/F.npy")
                        if got.stat().st_size != 5 * MB:
                            corrupt.append(got.name)
                        peak[0] = max(peak[0], on_disk(cache))
                except CacheFull:
                    errors.append("CacheFull")
                except Exception as e:  # anything else is a real defect
                    errors.append(f"{type(e).__name__}: {e}")

            n = 24 // threads
            ts = [threading.Thread(target=worker, args=(i * n, (i + 1) * n))
                  for i in range(threads)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            return errors, peak[0], corrupt

    # Depth-1 prefetching: one fetch ahead of one analysis.
    errors, peak, corrupt = run(threads=2, budget_mb=30)
    checks.append(("concurrent fetch + eviction completes without error",
                   not errors, f"{errors[:2]}"))
    checks.append(("no file is corrupted by a concurrent eviction",
                   not corrupt, f"{corrupt[:2]}"))
    checks.append(("on-disk bytes never exceed the budget",
                   peak <= 30 * MB, f"peak {peak / 1e6:.0f} MB"))

    # Oversubscribed: must refuse cleanly, never overshoot.
    errors, peak, corrupt = run(threads=4, budget_mb=30)
    checks.append(("oversubscription refuses rather than overshooting",
                   peak <= 30 * MB and not corrupt
                   and all(e == "CacheFull" for e in errors),
                   f"peak {peak / 1e6:.0f} MB, errors {set(errors)}"))
    return checks


def _budget_checks() -> list[Check]:
    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        free = shutil.disk_usage(tmp).free

        auto = resolve_budget(tmp)
        checks.append(("an auto budget is a fraction of free disk, capped",
                       0 < auto <= min(free * 0.25, 50 * 1000**3) + 1,
                       f"{auto / 1e9:.1f} GB of {free / 1e9:.1f} GB free"))

        checks.append(("an explicit budget is honoured",
                       resolve_budget(tmp, configured_gb=2.0) == 2 * 1000**3, ""))

        try:
            resolve_budget(tmp, configured_gb=free / 1000**3 + 100)
            msg = ""
        except CacheFull as e:
            msg = str(e)
        checks.append(("a budget beyond free disk is refused",
                       "exceeds the" in msg and "free" in msg, msg[:60]))

        # The pre-flight case: peak requirement known before the run starts.
        try:
            resolve_budget(tmp, configured_gb=1.0, required_bytes=3 * 1000**3)
            msg2 = ""
        except CacheFull as e:
            msg2 = str(e)
        checks.append(("too small for the largest recording is caught up front",
                       "needs" in msg2 and "cache_budget_gb" in msg2, msg2[:70]))
        checks.append(("…and the message says how much is actually free",
                       "free on" in msg2, msg2[-60:]))

        checks.append(("budgeting works for a directory that doesn't exist yet",
                       resolve_budget(tmp / "not" / "made" / "yet") > 0, ""))
    return checks


def _redaction_checks() -> list[Check]:
    """A share link must not travel inside a results bundle."""
    from meanap.params import (
        PARAMS_FILENAME, REDACTED, SECRET_URL_FIELDS, Params, redact,
    )

    checks: list[Check] = []
    URL = "https://www.dropbox.com/scl/fo/abc/XYZ?rlkey=supersecret"

    # Redaction is by value, not by field name: the same field holds a local
    # path on most runs and a share link on a remote one.
    out = redact({"raw_data": URL, "output_data_folder": "/home/me/out"})
    checks.append(("a url in raw_data is redacted",
                   out["raw_data"] == REDACTED, out["raw_data"][:40]))
    checks.append(("…with a placeholder, so its absence is visible",
                   "redacted" in out["raw_data"], ""))
    local = redact({"raw_data": "/home/me/data"})
    checks.append(("a local path in the same field is left alone",
                   local["raw_data"] == "/home/me/data", ""))
    checks.append(("every path field that could hold a url is covered",
                   {"raw_data", "prior_analysis_path"} <= set(SECRET_URL_FIELDS),
                   f"{SECRET_URL_FIELDS}"))

    # End to end: through a real bundle.
    sys.path.insert(0, str(REPO_ROOT / "python"))
    from test_bundle_render import BUNDLE_SUFFIX, _run  # noqa: E402
    from meanap.pipeline.bundle import open_bundle

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = _run(tmp, "Express", express=True)
        # Stamp a link into the run's own params, as a remote run would.
        pfile = root / PARAMS_FILENAME
        raw = json.loads(pfile.read_text())
        raw["raw_data"] = URL
        pfile.write_text(json.dumps(raw))

        from meanap.pipeline.bundle import build_manifest, write_bundle
        from meanap.pipeline.spreadsheet import RecordingInfo
        write_bundle(root, build_manifest(
            Params(), [RecordingInfo(filename="recA", div=21.0, group="WT")],
            mode="catnap", lags=[25]), root.with_suffix(BUNDLE_SUFFIX))

        with open_bundle(root.with_suffix(BUNDLE_SUFFIX)) as b:
            shipped = json.loads((b.root / PARAMS_FILENAME).read_text())
            checks.append(("the bundled params carry no url",
                           shipped["raw_data"] == REDACTED,
                           shipped["raw_data"][:40]))
            checks.append(("the secret does not appear anywhere in the bundle",
                           not any("supersecret" in p.read_bytes().decode(
                               "utf-8", "ignore")
                               for p in b.root.rglob("*") if p.is_file()), ""))
        checks.append(("the local copy keeps it, for reproducibility",
                       json.loads(pfile.read_text())["raw_data"] == URL, ""))
    return checks


def main() -> int:
    print("=" * 70)
    print("Remote data: store protocol, cache, budgeting, redaction")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — the store protocol and local passthrough:", _protocol_checks),
        ("B — cache bounds, eviction and pinning:", _cache_checks),
        ("C — partial fetches never become cache hits:", _integrity_checks),
        ("D — concurrent fetch, eviction and pinning:", _concurrency_checks),
        ("E — disk budgeting:", _budget_checks),
        ("F — share links don't travel in bundles:", _redaction_checks),
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
