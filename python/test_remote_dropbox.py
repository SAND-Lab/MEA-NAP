"""Test the Dropbox share-link store.

Run from the repo root::

    uv run python python/test_remote_dropbox.py           # offline
    MEANAP_DROPBOX_URL='https://…' uv run python python/test_remote_dropbox.py

The default run uses a fake HTTP layer and needs no network. That is not a
convenience: the interesting cases here are the ones a live connection only
produces by luck — a session expiring, a server ignoring ``Range``, a truncated
response, an interstitial page served instead of file bytes. Each of those is
provoked deliberately below.

The adapter depends on undocumented endpoints, so there is also a live section.
It runs only when ``MEANAP_DROPBOX_URL`` is set, and its job is to fail loudly
the day Dropbox changes something — with a message pointing at the supported
alternatives rather than a stack trace.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from meanap.remote.dropbox_link import (  # noqa: E402
    DropboxInterfaceChanged, DropboxLinkStore, parse_share_url,
)
from meanap.remote.http import HttpResponse  # noqa: E402

Check = tuple[str, bool, str]

LINK = ("https://www.dropbox.com/scl/fo/LINKKEY/ROOTHASH"
        "?rlkey=RLKEY&dl=0")


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n = 0
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok else f"  [{detail}]"))
        n += bool(ok)
    print(f"  → {n}/{len(checks)} passed")
    return n, len(checks)


# ── a fake Dropbox ────────────────────────────────────────────────────────────

TREE = {
    "": [("rec1", True, None), ("batch.csv", False, 1200)],
    "/rec1": [("suite2p", True, None)],
    "/rec1/suite2p": [("plane0", True, None)],
    "/rec1/suite2p/plane0": [("F.npy", False, 40), ("ops.npy", False, 100)],
}


def _fake_hash(sub_path: str) -> str:
    """Stand-in for Dropbox's per-entry secure_hash: opaque and slash-free."""
    return "HASH" + sub_path.strip("/").replace("/", "_")


class FakeHttp:
    """Enough of :class:`HttpClient` to drive the adapter, with failure switches."""

    def __init__(self, **flags):
        self.flags = flags
        self.posts: list[dict] = []
        self.streams: list[tuple[str, int]] = []
        self._token = "TOKEN1"
        self.token_reads = 0

    # session
    def get(self, url, headers=None):
        self.token_reads += 1
        return HttpResponse(200, {}, b"<html></html>")

    def cookie(self, name):
        if self.flags.get("no_csrf"):
            return None
        return self._token

    # listing
    def post_form(self, url, fields, headers=None):
        self.posts.append(dict(fields))
        if self.flags.get("html_listing"):
            return HttpResponse(200, {}, b"<!DOCTYPE html><html>...")
        if self.flags.get("expired") and fields["t"] == "TOKEN1":
            from meanap.remote.http import HttpError
            self._token = "TOKEN2"
            raise HttpError("POST listing: HTTP 403", 403)

        sub = fields["sub_path"]
        # The real endpoint 404s when the hash doesn't match the sub_path; the
        # fake enforces the same rule so a regression in the walk is caught.
        # Real hashes are opaque and slash-free, so the fake's must be too —
        # otherwise the link regex would stop at the first slash.
        expected = "ROOTHASH" if sub == "" else _fake_hash(sub)
        if fields["secure_hash"] != expected:
            from meanap.remote.http import HttpError
            raise HttpError("POST listing: HTTP 404", 404)
        if sub not in TREE:
            from meanap.remote.http import HttpError
            raise HttpError("POST listing: HTTP 404", 404)

        entries = []
        for name, is_dir, size in TREE[sub]:
            child = f"{sub}/{name}"
            entries.append({
                "filename": name, "is_dir": is_dir, "bytes": size,
                "href": (f"https://www.dropbox.com/scl/fo/LINKKEY/"
                         f"{_fake_hash(child)}{child}?rlkey=RLKEY&dl=0"),
            })
        body = {"entries": entries, "total_num_entries": len(entries)}
        if self.flags.get("no_entries_key"):
            body = {"unexpected": True}
        if self.flags.get("paginated"):
            body["has_more_entries"] = True
        return HttpResponse(200, {}, json.dumps(body).encode())

    # download
    def stream(self, url, start=0, chunk_size=1 << 20):
        self.streams.append((url, start))
        if self.flags.get("html_body"):
            return 200, {"Content-Type": "text/html"}, iter([b"<!DOCTYPE html>"])
        payload = bytes(range(40))
        if self.flags.get("ignores_range"):
            return 200, {"Content-Type": "application/octet-stream"}, iter([payload])
        if self.flags.get("truncated"):
            return 200, {"Content-Type": "application/octet-stream"}, iter([payload[:10]])
        if start:
            return 206, {"Content-Type": "application/octet-stream"}, iter([payload[start:]])
        return 200, {"Content-Type": "application/octet-stream"}, iter([payload])


def _store(**flags) -> tuple[DropboxLinkStore, FakeHttp]:
    http = FakeHttp(**flags)
    return DropboxLinkStore(LINK, client=http), http


# ── sections ──────────────────────────────────────────────────────────────────


def _url_checks() -> list[Check]:
    checks: list[Check] = []
    key, h, rl = parse_share_url(LINK)
    checks.append(("a folder link parses", (key, h, rl) == ("LINKKEY", "ROOTHASH", "RLKEY"),
                   f"{(key, h, rl)}"))
    checks.append(("extra query parameters are tolerated",
                   parse_share_url(LINK + "&st=abc&e=1")[2] == "RLKEY", ""))

    for bad, expect in [
        ("https://example.com/x", "Not a Dropbox share link"),
        ("https://www.dropbox.com/scl/fi/K/H?rlkey=R", "link to a single file"),
        ("https://www.dropbox.com/scl/fo/K/H", "no 'rlkey'"),
    ]:
        try:
            parse_share_url(bad)
            msg = ""
        except ValueError as e:
            msg = str(e)
        checks.append((f"rejected with a reason: {expect}", expect in msg, msg[:60]))
    return checks


def _walk_checks() -> list[Check]:
    checks: list[Check] = []
    store, http = _store()

    root = {e.name: e for e in store.list()}
    checks.append(("lists the root", set(root) == {"rec1", "batch.csv"}, f"{sorted(root)}"))
    checks.append(("file sizes come from the listing", root["batch.csv"].size == 1200, ""))
    checks.append(("directories report no size", root["rec1"].size is None, ""))

    deep = {e.name: e for e in store.list("rec1/suite2p/plane0")}
    checks.append(("descends three levels", set(deep) == {"F.npy", "ops.npy"},
                   f"{sorted(deep)}"))
    checks.append(("nested entries carry full relative paths",
                   deep["F.npy"].path == "rec1/suite2p/plane0/F.npy",
                   deep["F.npy"].path))

    # The walk must reuse cached ancestors rather than re-listing them.
    posts_before = len(http.posts)
    store.list("rec1/suite2p/plane0")
    checks.append(("a repeated listing costs no requests",
                   len(http.posts) == posts_before, f"{len(http.posts) - posts_before}"))

    checks.append(("stat finds a nested file",
                   store.stat("rec1/suite2p/plane0/F.npy").size == 40, ""))
    checks.append(("stat returns None for a missing name",
                   store.stat("rec1/suite2p/plane0/nope.npy") is None, ""))
    checks.append(("listing a non-existent folder is empty, not an error",
                   store.list("rec1/nope") == [], ""))

    # The download URL must use raw=1 — dl=1 returns an interstitial page.
    url = store._download_url("rec1/suite2p/plane0/F.npy")
    checks.append(("download url uses raw=1", "raw=1" in url, url[-40:]))
    checks.append(("…and drops dl=", "dl=" not in url, url[-40:]))
    checks.append(("…and keeps the access key", "rlkey=RLKEY" in url, ""))
    return checks


def _session_checks() -> list[Check]:
    checks: list[Check] = []

    store, http = _store(expired=True)
    entries = store.list()
    checks.append(("an expired session is refreshed and retried",
                   len(entries) == 2, f"{len(entries)}"))
    checks.append(("…using a new token",
                   http.posts[-1]["t"] == "TOKEN2", f"{http.posts[-1]['t']}"))

    store, _ = _store(no_csrf=True)
    try:
        store.list()
        msg = ""
    except DropboxInterfaceChanged as e:
        msg = str(e)
    checks.append(("a missing CSRF cookie is reported as an interface change",
                   "CSRF cookie" in msg, msg[:50]))
    checks.append(("…with the supported alternatives named",
                   "rclone" in msg and "synced Dropbox folder" in msg, ""))
    return checks


def _interface_change_checks() -> list[Check]:
    """Every way this can rot must fail loudly, never as "the folder is empty"."""
    checks: list[Check] = []

    for flags, label, expect in [
        (dict(html_listing=True), "HTML instead of JSON", "HTML instead of JSON"),
        (dict(no_entries_key=True), "no 'entries' key", "no 'entries' key"),
        (dict(paginated=True), "a paginated listing", "paginated listings"),
    ]:
        store, _ = _store(**flags)
        try:
            store.list()
            msg = ""
        except DropboxInterfaceChanged as e:
            msg = str(e)
        checks.append((f"{label} raises DropboxInterfaceChanged", expect in msg, msg[:60]))

    store, _ = _store(html_body=True)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            store.fetch("rec1/suite2p/plane0/F.npy", Path(tmp) / "F.npy")
            msg = ""
        except DropboxInterfaceChanged as e:
            msg = str(e)
    checks.append(("a web page served instead of file bytes is caught",
                   "web page instead of file data" in msg, msg[:60]))
    return checks


def _download_checks() -> list[Check]:
    checks: list[Check] = []
    rel = "rec1/suite2p/plane0/F.npy"

    with tempfile.TemporaryDirectory() as tmp:
        store, http = _store()
        dest = Path(tmp) / "F.npy"
        store.fetch(rel, dest)
        checks.append(("a fresh download is complete",
                       dest.read_bytes() == bytes(range(40)), ""))

        # Resume: half the bytes already present.
        dest.write_bytes(bytes(range(40))[:15])
        http.streams.clear()
        store.fetch(rel, dest)
        checks.append(("a partial file is resumed, not restarted",
                       http.streams[-1][1] == 15, f"{http.streams[-1][1]}"))
        checks.append(("…and the result is byte-identical",
                       dest.read_bytes() == bytes(range(40)), ""))

        # Already complete: no request at all.
        http.streams.clear()
        store.fetch(rel, dest)
        checks.append(("a complete file triggers no download",
                       not http.streams, f"{len(http.streams)}"))

    with tempfile.TemporaryDirectory() as tmp:
        # A server that ignores Range must not have its bytes appended.
        store, _ = _store(ignores_range=True)
        dest = Path(tmp) / "F.npy"
        dest.write_bytes(bytes(range(40))[:15])
        store.fetch(rel, dest)
        checks.append(("a server ignoring Range restarts cleanly",
                       dest.read_bytes() == bytes(range(40)),
                       f"{len(dest.read_bytes())} bytes"))

    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _store(truncated=True)
        try:
            store.fetch(rel, Path(tmp) / "F.npy")
            msg = ""
        except Exception as e:
            msg = str(e)
        checks.append(("a truncated response is detected against the listed size",
                       "expected 40" in msg, msg[:60]))
    return checks


def _live_checks(url: str) -> list[Check]:
    """Against the real Dropbox. Fails the day the undocumented endpoints change."""
    import numpy as np

    from meanap.remote.cache import FileCache

    checks: list[Check] = []
    store = DropboxLinkStore(url)
    root = store.list()
    checks.append(("the live root lists", len(root) > 0, f"{len(root)}"))
    checks.append(("entries carry sizes without downloading",
                   any(e.size for e in root if not e.is_dir)
                   or all(e.is_dir for e in root), ""))

    folders = [e for e in root if e.is_dir]
    if not folders:
        checks.append(("a recording folder exists", False, "none found"))
        return checks

    plane0 = None
    for folder in folders:
        candidate = f"{folder.path}/suite2p/plane0"
        if store.list(candidate):
            plane0 = candidate
            break
    checks.append(("a suite2p/plane0 is reachable", plane0 is not None, ""))
    if plane0 is None:
        return checks

    files = {e.name: e for e in store.list(plane0)}
    checks.append(("plane0 lists .npy files",
                   any(n.endswith(".npy") for n in files), f"{sorted(files)[:4]}"))

    name = "F.npy" if "F.npy" in files else next(iter(files))
    with tempfile.TemporaryDirectory() as tmp:
        cache = FileCache(root=Path(tmp) / "c", budget_bytes=2_000_000_000)
        got = cache.get(store, f"{plane0}/{name}")
        checks.append(("a file downloads to the listed size",
                       got.stat().st_size == files[name].size,
                       f"{got.stat().st_size} vs {files[name].size}"))
        if name.endswith(".npy"):
            try:
                arr = np.load(got, mmap_mode="r", allow_pickle=True)
                ok = getattr(arr, "shape", None) is not None or True
            except Exception as e:
                ok, arr = False, e
            checks.append(("…and is a readable .npy, not an HTML page", ok, f"{arr}"))
    return checks


def main() -> int:
    print("=" * 70)
    print("Dropbox share-link store")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("A — share-link URLs:", _url_checks),
        ("B — listing and the folder walk:", _walk_checks),
        ("C — session and CSRF handling:", _session_checks),
        ("D — every way the interface can rot:", _interface_change_checks),
        ("E — downloads, resume and truncation:", _download_checks),
    ]:
        p, n = _report(title, build())
        total_pass += p
        total += n

    live = os.environ.get("MEANAP_DROPBOX_URL")
    if live:
        p, n = _report("F — against the live Dropbox link:", _live_checks(live))
        total_pass += p
        total += n
    else:
        print("\nF — live Dropbox check SKIPPED "
              "(set MEANAP_DROPBOX_URL to run it)")

    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
