"""A very small HTTP client: cookies, retries, ranged streaming.

Standard library only, deliberately. The remote-data feature is optional, and
adding ``requests`` to the core dependencies of an analysis package so that one
backend can talk to one website is a poor trade — the same reasoning that keeps
the viewer on ``http.server``.

Everything network-facing lives behind :class:`HttpClient` so the Dropbox
backend can be tested without a network: the tests substitute a fake client and
drive the retry, resume and throttling paths that a live connection would only
exercise by luck.
"""

from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from typing import Iterator

__all__ = ["HttpClient", "HttpResponse", "HttpError", "USER_AGENT"]

#: Dropbox serves its single-page app, not JSON, to clients it doesn't
#: recognise as browsers. This is required for the listing endpoint to answer.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

#: Retried with backoff: throttling, and the transient 5xx family.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class HttpError(RuntimeError):
    """A request failed after exhausting retries."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class HttpResponse:
    status: int
    headers: dict
    body: bytes = b""

    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


@dataclass
class HttpClient:
    """Cookie-aware client with exponential backoff.

    One cookie jar per instance: Dropbox's listing endpoint needs both a session
    cookie and the CSRF token it sets, so the client that fetches the share page
    must be the one that lists it.
    """

    timeout: float = 90.0
    retries: int = 4
    backoff: float = 1.5
    _jar: CookieJar = field(default_factory=CookieJar)

    def __post_init__(self) -> None:
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar))

    # ── cookies ──────────────────────────────────────────────────────────────

    def cookie(self, name: str) -> str | None:
        for c in self._jar:
            if c.name == name:
                return c.value
        return None

    # ── requests ─────────────────────────────────────────────────────────────

    def _request(self, url: str, *, data: bytes | None = None,
                 headers: dict | None = None, stream: bool = False):
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept-Encoding", "gzip")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        return self._opener.open(req, timeout=self.timeout)

    def _with_retries(self, describe: str, attempt):
        """Run *attempt*, retrying throttling and transient failures.

        A 4xx that isn't throttling is not retried: it will not become true by
        waiting, and burning four timeouts on it hides the real error.
        """
        last = None
        for i in range(self.retries):
            try:
                return attempt()
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in _RETRY_STATUSES:
                    raise HttpError(f"{describe}: HTTP {e.code}", e.code) from e
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                last = e
            if i < self.retries - 1:
                time.sleep(self.backoff ** i)
        status = getattr(last, "code", None)
        raise HttpError(f"{describe}: giving up after {self.retries} attempts "
                        f"({type(last).__name__}: {last})", status)

    def get(self, url: str, headers: dict | None = None) -> HttpResponse:
        def attempt() -> HttpResponse:
            with self._request(url, headers=headers) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return HttpResponse(r.status, dict(r.headers), body)
        return self._with_retries(f"GET {_short(url)}", attempt)

    def post_form(self, url: str, fields: dict,
                  headers: dict | None = None) -> HttpResponse:
        data = urllib.parse.urlencode(fields).encode()
        merged = {"Content-Type": "application/x-www-form-urlencoded"}
        merged.update(headers or {})

        def attempt() -> HttpResponse:
            with self._request(url, data=data, headers=merged) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return HttpResponse(r.status, dict(r.headers), body)
        return self._with_retries(f"POST {_short(url)}", attempt)

    def stream(self, url: str, start: int = 0,
               chunk_size: int = 1 << 20) -> tuple[int, dict, Iterator[bytes]]:
        """Open a ranged download, returning ``(status, headers, chunks)``.

        ``start`` resumes a partial download. A server that ignores the range
        answers 200 rather than 206; the caller must notice and restart, which
        is why the status is returned rather than swallowed.
        """
        headers = {"Range": f"bytes={start}-"} if start else {}
        # Range and transparent gzip do not mix — the byte offsets would refer
        # to different streams.
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", USER_AGENT)
        for k, v in headers.items():
            req.add_header(k, v)

        def attempt():
            return self._opener.open(req, timeout=self.timeout)

        resp = self._with_retries(f"GET {_short(url)}", attempt)

        def chunks() -> Iterator[bytes]:
            try:
                while True:
                    block = resp.read(chunk_size)
                    if not block:
                        return
                    yield block
            finally:
                resp.close()

        return resp.status, dict(resp.headers), chunks()


def _short(url: str) -> str:
    """URLs here carry access secrets; keep them out of exception text."""
    parsed = urllib.parse.urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
