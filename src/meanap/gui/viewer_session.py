"""Viewer servers owned by the GUI, one per bundle the user opens.

The viewer is a local web server (:mod:`meanap.viewer.server`) that renders a
bundle's figures on demand. Launching it from the GUI means the GUI owns its
lifetime: the server must outlive the click that started it, must not be
started twice for the same bundle, and must be shut down when the window
closes — a leaked ``ThreadingHTTPServer`` holds a port and a temporary
extraction directory for as long as the process lives.

Kept out of :mod:`meanap.gui.main_window` so it can be driven in tests without
a window, and so nothing here needs Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meanap.viewer.server import DEFAULT_PORT, serve

__all__ = ["ViewerSessions", "Session"]


@dataclass
class Session:
    """One running viewer: its URL and the objects that must be torn down."""

    source: Path
    url: str
    httpd: object
    service: object

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.service.close()


class ViewerSessions:
    """The set of viewers this window has open, keyed by resolved source path.

    Opening the same bundle twice returns the URL already serving it rather
    than paying to extract and parse it again — the user's intent in clicking
    twice is "show me that page", not "give me a second copy of it".
    """

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self._preferred_port = port
        self._sessions: dict[Path, Session] = {}

    def __len__(self) -> int:
        return len(self._sessions)

    def url_for(self, source: Path | str) -> str | None:
        """The URL already serving *source*, or ``None``."""
        session = self._sessions.get(Path(source).resolve())
        return session.url if session is not None else None

    def open(self, source: Path | str) -> str:
        """Serve *source* (bundle or output folder) and return its URL.

        Raises whatever the viewer raises on an unreadable source —
        :class:`ValueError` with a message written to be shown to the user.
        """
        key = Path(source).resolve()
        existing = self._sessions.get(key)
        if existing is not None:
            return existing.url

        # The default port is the one a collaborator would be told to visit, so
        # try it first; fall back to any free port when it is taken — by a
        # second bundle open in this window, or by something else entirely.
        try:
            httpd, service = serve(key, port=self._preferred_port, background=True)
        except OSError:
            httpd, service = serve(key, port=0, background=True)

        url = f"http://{httpd.server_address[0]}:{httpd.server_address[1]}/"
        self._sessions[key] = Session(source=key, url=url, httpd=httpd, service=service)
        return url

    def close_all(self) -> None:
        """Shut every viewer down. Safe to call twice."""
        for session in list(self._sessions.values()):
            try:
                session.close()
            except Exception:
                # Teardown runs while the window is closing; a server that is
                # already dead must not stop the rest from being reclaimed.
                pass
        self._sessions.clear()
