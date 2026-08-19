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

#: A folder with more recordings than one listing response returns. Real share
#: links of this size exist (387 recordings in the dataset that first hit it),
#: and a truncated listing there is indistinguishable from a small dataset.
BIG = [(f"rec{i:03d}", True, None) for i in range(130)]

TREE = {
    "": [("rec1", True, None), ("batch.csv", False, 1200)],
    "/rec1": [("suite2p", True, None), ("big", True, None)],
    "/rec1/suite2p": [("plane0", True, None)],
    "/rec1/suite2p/plane0": [("F.npy", False, 40), ("ops.npy", False, 100)],
    "/rec1/big": BIG,
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
        self.fail_next = int(flags.get("fail_next", 0))

    # session
    def get(self, url, headers=None):
        # Each fetch of the share page mints a new CSRF cookie, as the real one
        # does — so "did it re-authenticate?" is observable in the posted token.
        self.token_reads += 1
        self._token = f"TOKEN{self.token_reads}"
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
            raise HttpError("POST listing: HTTP 403", 403)

        # Throttling: decline the first N calls with the status Dropbox
        # actually returns, then behave normally.
        if self.fail_next:
            self.fail_next -= 1
            from meanap.remote.http import HttpError
            raise HttpError("POST listing: HTTP 400", 400)
        if self.flags.get("bad_request"):
            from meanap.remote.http import HttpError
            raise HttpError("POST listing: HTTP 418", 418)

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
        total = len(entries)

        # Dropbox pages long folders: the response carries a slice plus a
        # voucher to hand back for the next one. The fake uses the offset as
        # its voucher so a lost or ignored voucher shows up as a repeat.
        page = self.flags.get("page_size")
        if page:
            start = int(fields.get("voucher", 0) or 0)
            entries = entries[start:start + page]
            body = {"entries": entries, "total_num_entries": total}
            if start + page < total:
                body["has_more_entries"] = True
                body["next_request_voucher"] = str(start + page)
        else:
            body = {"entries": entries, "total_num_entries": total}

        if self.flags.get("no_entries_key"):
            body = {"unexpected": True}
        if self.flags.get("no_voucher"):
            body["has_more_entries"] = True
            body.pop("next_request_voucher", None)
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
    # Zero backoff: the retry *policy* is what's under test, not the waiting.
    return DropboxLinkStore(LINK, client=http, listing_backoff=0.0), http


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


def _pagination_checks() -> list[Check]:
    """A folder bigger than one response must still list completely.

    This is the failure mode with no symptom: a short listing reads as a small
    dataset, so a 387-recording batch would run its first 30 and report done.
    """
    checks: list[Check] = []
    store, http = _store(page_size=30)

    big = store.list("rec1/big")
    checks.append(("a folder spanning several pages is listed in full",
                   len(big) == len(BIG), f"{len(big)} of {len(BIG)}"))
    checks.append(("…in order, with no page dropped or repeated",
                   [e.name for e in big] == [n for n, _, _ in BIG], ""))

    listing_posts = [p for p in http.posts if p["sub_path"] == "/rec1/big"]
    checks.append(("…which took more than one request",
                   len(listing_posts) == 5, f"{len(listing_posts)}"))
    checks.append(("the first request carries no voucher",
                   "voucher" not in listing_posts[0], ""))
    checks.append(("…and each later one carries the previous response's",
                   [p["voucher"] for p in listing_posts[1:]]
                   == ["30", "60", "90", "120"],
                   f"{[p.get('voucher') for p in listing_posts[1:]]}"))

    checks.append(("a paged folder still resolves a file inside it",
                   store.stat("rec1/big/rec129") is not None, ""))

    # Folders that fit in one page must not pay for the loop: four levels,
    # four requests.
    fresh, fresh_http = _store(page_size=30)
    fresh.list("rec1/suite2p/plane0")
    checks.append(("folders that fit in one page cost one request each",
                   len(fresh_http.posts) == 4, f"{len(fresh_http.posts)}"))
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


def _throttle_checks() -> list[Check]:
    """A transient refusal must cost a pause, not the run.

    From a real failure: a 381-recording pre-flight lists three folders per
    recording, and somewhere past request ~1000 Dropbox began answering 400.
    The same walk from a fresh session completed all 382 folders minutes
    later, so the request was never malformed — the server was declining. A
    fatal 400 there loses hours of streaming to a throttle that clears by
    itself.
    """
    checks: list[Check] = []

    store, http = _store(fail_next=2)
    entries = store.list()
    checks.append(("a listing throttled twice still succeeds",
                   len(entries) == 2, f"{len(entries)}"))
    checks.append(("…having retried rather than given up",
                   len(http.posts) == 3, f"{len(http.posts)} posts"))
    tokens = [p["t"] for p in http.posts]
    checks.append(("…re-authenticating before each retry, never reusing a token",
                   len(set(tokens)) == len(tokens) == 3, f"{tokens}"))

    # Persistent refusal must still end, and say what to do about it.
    store, http = _store(fail_next=99)
    try:
        store.list()
        msg = ""
    except DropboxInterfaceChanged as e:
        msg = str(e)
    checks.append(("a listing that never recovers raises rather than hanging",
                   bool(msg), "no exception"))
    checks.append(("…bounded by the attempt limit",
                   len(http.posts) == store._LISTING_ATTEMPTS,
                   f"{len(http.posts)} posts"))
    checks.append(("…and says the cache makes a re-run cheap",
                   "already fetched is fetched again" in msg, msg[:80]))

    # A genuine client error must not be retried into a long stall.
    store, http = _store(bad_request=True)
    try:
        store.list()
        status = None
    except Exception as e:
        status = getattr(e, "status", None)
    checks.append(("a non-session 4xx is still raised immediately",
                   status == 418 and len(http.posts) == 1,
                   f"status={status} posts={len(http.posts)}"))
    return checks


def _interface_change_checks() -> list[Check]:
    """Every way this can rot must fail loudly, never as "the folder is empty"."""
    checks: list[Check] = []

    for flags, label, expect in [
        (dict(html_listing=True), "HTML instead of JSON", "HTML instead of JSON"),
        (dict(no_entries_key=True), "no 'entries' key", "no 'entries' key"),
        (dict(no_voucher=True), "more entries but no voucher",
         "gave no pagination voucher"),
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
        ("B2 — folders too big for one response:", _pagination_checks),
        ("C — session and CSRF handling:", _session_checks),
        ("C2 — throttling during a long walk:", _throttle_checks),
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
