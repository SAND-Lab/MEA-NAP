"""Read a public Dropbox folder share link, one file at a time.

A folder share link looks like a dead end: the only *documented* unauthenticated
operation is downloading the whole folder as a generated zip, which for a real
dataset means tens of gigabytes and no way to take a part of it. Dropbox's own
web interface obviously does better than that, and it does so with endpoints
that need no token:

===============================  ===========================================
list a folder                    ``POST /list_shared_link_folder_entries``
                                 with the CSRF token from the share page;
                                 long folders page via ``voucher``
descend into a subfolder         the child's **own** ``secure_hash`` (from its
                                 ``href``) *plus* the full ``sub_path``
download one file                the entry's ``href`` with ``raw=1``
===============================  ===========================================

All three were verified against a live 14 GB link, including ``Range`` support
on the download (``206`` with ``Content-Range``), which is what makes an
interrupted fetch resumable rather than restarted.

.. warning::

   **This is not a public API.** It is what dropbox.com's front end happens to
   use, it is unversioned, and it can change without notice. It is confined to
   this module so that when it breaks, one adapter fails with an actionable
   message rather than the pipeline misbehaving somewhere unrelated — see
   :class:`DropboxInterfaceChanged`. A synced folder or an ``rclone`` mount
   reaches the same data through supported means and needs none of this.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path

from meanap.remote.base import ProgressFn, RemoteEntry, store_id_for
from meanap.remote.http import HttpClient, HttpError

__all__ = ["DropboxLinkStore", "DropboxInterfaceChanged", "parse_share_url"]

_LISTING_URL = "https://www.dropbox.com/list_shared_link_folder_entries"
_LINK_RE = re.compile(r"/scl/(?P<kind>fo|fi)/(?P<key>[^/]+)/(?P<hash>[^/?]+)")


class DropboxInterfaceChanged(RuntimeError):
    """Dropbox's web endpoints no longer behave as this adapter expects.

    Raised instead of a parse error or an empty listing, because "the folder
    looks empty" is the most damaging way this could fail: a run would proceed
    and quietly analyse nothing.
    """

    def __init__(self, detail: str):
        super().__init__(
            f"{detail}\n\nThe Dropbox share-link reader depends on undocumented "
            "web endpoints, which appear to have changed. Use a synced Dropbox "
            "folder or an 'rclone mount' and point Params.raw_data at it — both "
            "reach the same data through supported interfaces.")


def parse_share_url(url: str) -> tuple[str, str, str]:
    """Split a share link into ``(link_key, secure_hash, rlkey)``.

    Raises :class:`ValueError` with a specific reason — a file link, or a link
    missing its ``rlkey`` — rather than failing later with an opaque HTTP error.
    """
    match = _LINK_RE.search(url)
    if not match:
        raise ValueError(
            f"Not a Dropbox share link: {url!r}. Expected something like "
            "https://www.dropbox.com/scl/fo/<id>/<hash>?rlkey=<key>")
    if match.group("kind") == "fi":
        raise ValueError(
            "That is a link to a single file (/scl/fi/...). MEA-NAP needs a "
            "link to the folder containing your recordings — share the folder "
            "instead.")
    rlkey = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("rlkey", [""])[0]
    if not rlkey:
        raise ValueError(
            "The share link has no 'rlkey' parameter. Copy the whole link from "
            "Dropbox's Share dialog, including everything after the '?'.")
    return match.group("key"), match.group("hash"), rlkey


class DropboxLinkStore:
    """A :class:`~meanap.remote.base.RemoteStore` over a public folder link."""

    copies = True

    def __init__(self, url: str, client: HttpClient | None = None,
                 listing_backoff: float = 5.0):
        self.link_key, self.root_hash, self.rlkey = parse_share_url(url)
        self.url = url
        self.store_id = store_id_for("dropbox", self.link_key)
        self._http = client or HttpClient()
        self._csrf: str | None = None
        #: Seconds before the second listing attempt, doubling thereafter.
        #: A parameter so tests can drive the retry path without sleeping.
        self._listing_backoff = listing_backoff
        # dir path -> {"hash": str, "entries": [RemoteEntry], "hrefs": {name: url}}
        self._dirs: dict[str, dict] = {}

    def __repr__(self) -> str:
        return f"DropboxLinkStore({self.link_key})"

    # ── session ──────────────────────────────────────────────────────────────

    def _token(self, refresh: bool = False) -> str:
        """CSRF token for the listing endpoint, from the share page's cookies."""
        if self._csrf and not refresh:
            return self._csrf
        self._http.get(self.url)
        token = self._http.cookie("__Host-js_csrf")
        if not token:
            raise DropboxInterfaceChanged(
                "The share page did not set the expected CSRF cookie.")
        self._csrf = token
        return token

    #: Statuses this endpoint returns when it is declining a request that is in
    #: itself well-formed — an expired session, or too much traffic in too
    #: short a window. The request shape here is fixed and known-good, so a
    #: 400 is *not* the usual "you sent nonsense": it is Dropbox saying not
    #: now. Observed on a 381-recording pre-flight, which lists three folders
    #: per recording; the same walk succeeded from a fresh session minutes
    #: later. Treating it as fatal kills a multi-hour run at request ~1000.
    _SESSION_STATUSES = frozenset({400, 403, 404})

    #: Attempts per listing call, each preceded by a fresh token and a longer
    #: wait. Deliberately patient rather than fast: a throttle that clears in
    #: 30 s is worth waiting out when the alternative is restarting a run.
    _LISTING_ATTEMPTS = 4

    def _listing_call(
        self, secure_hash: str, sub_path: str, voucher: str | None = None,
    ) -> dict:
        fields = {
            "t": self._token(), "link_key": self.link_key,
            "secure_hash": secure_hash, "rlkey": self.rlkey,
            "sub_path": sub_path, "link_type": "s",
        }
        if voucher:
            fields["voucher"] = voucher

        last: HttpError | None = None
        for attempt in range(self._LISTING_ATTEMPTS):
            if attempt:
                # Back off *then* re-authenticate: a token minted during the
                # throttle window is no more welcome than the one it replaces.
                time.sleep(self._listing_backoff * (2 ** (attempt - 1)))
                fields["t"] = self._token(refresh=True)
            try:
                resp = self._http.post_form(
                    _LISTING_URL, fields, {"X-Requested-With": "XMLHttpRequest"})
            except HttpError as e:
                if e.status not in self._SESSION_STATUSES:
                    raise
                last = e
                continue
            try:
                return json.loads(resp.text())
            except json.JSONDecodeError:
                raise DropboxInterfaceChanged(
                    "The folder-listing endpoint returned HTML instead of JSON."
                ) from None

        raise DropboxInterfaceChanged(
            f"Listing '{sub_path or '/'}' failed {self._LISTING_ATTEMPTS} times; "
            f"the last was {last}. If this is throttling it will clear on its "
            "own — wait and re-run, and the cache means nothing already "
            "fetched is fetched again.")

    # ── directory walk ───────────────────────────────────────────────────────

    def _dir(self, path: str) -> dict:
        """Listing metadata for a directory, walking (and caching) from the root.

        Each level needs the *child's* ``secure_hash`` together with the full
        path so far — the parent's hash gives a 404. Cached because a tree walk
        would otherwise re-request every ancestor for every leaf.
        """
        path = path.strip("/")
        if path in self._dirs:
            return self._dirs[path]

        if not path:
            info = self._load_dir(self.root_hash, "")
            self._dirs[""] = info
            return info

        parent_path, _, name = path.rpartition("/")
        parent = self._dir(parent_path)
        href = parent["hrefs"].get(name)
        if href is None:
            raise FileNotFoundError(path)
        match = _LINK_RE.search(href)
        if not match:
            raise DropboxInterfaceChanged(f"Unrecognised entry link for {path!r}.")
        info = self._load_dir(match.group("hash"), "/" + path)
        self._dirs[path] = info
        return info

    def _load_dir(self, secure_hash: str, sub_path: str) -> dict:
        """Every entry in one directory, following pagination to the end.

        The first response carries 30 entries; bigger folders then hand back a
        ``next_request_voucher`` to pass as ``voucher`` on the next call, which
        returns 75 at a time. A dataset folder holding hundreds of recordings
        needs this, and the failure it prevents is the worst kind: a short
        listing looks like a complete one, so a batch would quietly analyse its
        first 30 recordings and report success.
        """
        prefix = sub_path.strip("/")
        entries, hrefs = [], {}
        voucher: str | None = None
        while True:
            data = self._listing_call(secure_hash, sub_path, voucher)
            if "entries" not in data:
                raise DropboxInterfaceChanged(
                    f"Folder listing had no 'entries' key (got: {sorted(data)[:6]}).")

            for raw in data["entries"]:
                name = raw.get("filename")
                if not name:
                    continue
                entries.append(RemoteEntry(
                    path=f"{prefix}/{name}" if prefix else name,
                    is_dir=bool(raw.get("is_dir")),
                    size=None if raw.get("is_dir") else raw.get("bytes"),
                ))
                hrefs[name] = raw.get("href", "")

            if not data.get("has_more_entries"):
                break
            voucher = data.get("next_request_voucher")
            if not voucher:
                # More entries exist but nothing to ask for them with. Refusing
                # beats returning a listing that is silently incomplete.
                raise DropboxInterfaceChanged(
                    f"Folder '{sub_path or '/'}' reports more entries than were "
                    f"returned ({len(entries)} of {data.get('total_num_entries')}) "
                    "but gave no pagination voucher.")
        return {"hash": secure_hash, "entries": entries, "hrefs": hrefs}

    # ── RemoteStore ──────────────────────────────────────────────────────────

    def list(self, path: str = "") -> list[RemoteEntry]:
        try:
            return list(self._dir(path)["entries"])
        except FileNotFoundError:
            return []

    def stat(self, path: str) -> RemoteEntry | None:
        path = path.strip("/")
        if not path:
            return RemoteEntry("", True, None)
        parent, _, name = path.rpartition("/")
        try:
            entries = self._dir(parent)["entries"]
        except FileNotFoundError:
            return None
        return next((e for e in entries if e.name == name), None)

    def _download_url(self, path: str) -> str:
        """The direct-bytes URL for a file: its href with ``raw=1``.

        ``dl=1`` returns an HTML interstitial rather than the file, which is the
        kind of thing that would otherwise be discovered by writing a 24 MB HTML
        page into a ``.npy``.
        """
        parent, _, name = path.strip("/").rpartition("/")
        href = self._dir(parent)["hrefs"].get(name)
        if not href:
            raise FileNotFoundError(path)
        split = urllib.parse.urlsplit(href)
        query = urllib.parse.parse_qs(split.query)
        query.pop("dl", None)
        query["raw"] = ["1"]
        return urllib.parse.urlunsplit(
            split._replace(query=urllib.parse.urlencode(query, doseq=True)))

    def fetch(self, path: str, dest: Path, progress: ProgressFn | None = None) -> Path:
        """Download one file to *dest*, resuming if a partial is already there.

        The caller (:class:`~meanap.remote.cache.FileCache`) owns atomicity and
        hands over a temporary path; resuming across *its* retries is why the
        partial is appended to rather than replaced.
        """
        url = self._download_url(path)
        entry = self.stat(path)
        total = entry.size if entry else None

        have = dest.stat().st_size if dest.exists() else 0
        if total is not None and have >= total:
            return dest

        status, headers, chunks = self._http.stream(url, start=have)
        # A server that ignores Range answers 200 with the whole file; appending
        # then would corrupt it, so start over.
        mode = "ab"
        if have and status != 206:
            have, mode = 0, "wb"

        ctype = headers.get("Content-Type", "")
        if ctype.startswith("text/html"):
            raise DropboxInterfaceChanged(
                f"Downloading {path!r} returned a web page instead of file data.")

        written = have
        with open(dest, mode) as fh:
            for block in chunks:
                fh.write(block)
                written += len(block)
                if progress is not None:
                    progress(written, total)

        if total is not None and written != total:
            raise HttpError(
                f"{path}: got {written} bytes, expected {total}. The download "
                "was truncated; it will be retried from here.")
        return dest
