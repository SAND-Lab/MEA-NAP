"""Hand a file to the MEA-NAP window that is already open.

Double-clicking a second ``.meanap`` bundle starts MEA-NAP again. Without this
it would open a second window with a second viewer server; instead the new
process passes the file to the running window over a local socket and exits,
so everything being viewed is in one place.

macOS works differently: Finder starts the app with no file on the command
line and sends it a "file open" event instead, to the running copy if there
is one. :class:`FileOpenFilter` turns those events into the same call.
"""

from __future__ import annotations

import getpass
import json
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

__all__ = ["FileOpenFilter", "InstanceServer", "server_name", "send_to_running"]

TIMEOUT_MS = 1500


def server_name() -> str:
    """One name per user, so two people on one computer get their own windows."""
    try:
        user = getpass.getuser()
    except Exception:  # no login name (some containers)
        user = "user"
    return f"meanap-gui-{user}"


def send_to_running(paths: list[str], name: str | None = None) -> bool:
    """Give *paths* to a running MEA-NAP window; whether one took them."""
    socket = QLocalSocket()
    socket.connectToServer(name or server_name())
    if not socket.waitForConnected(TIMEOUT_MS):
        return False
    payload = json.dumps([str(Path(p).expanduser().resolve()) for p in paths])
    socket.write(payload.encode() + b"\n")
    # flush() usually writes it all at once, leaving nothing to wait for.
    socket.flush()
    while socket.bytesToWrite() > 0:
        if not socket.waitForBytesWritten(TIMEOUT_MS):
            return False
    socket.disconnectFromServer()
    return True


def _answering(name: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(name)
    connected = socket.waitForConnected(TIMEOUT_MS)
    socket.abort()
    return connected


class InstanceServer(QObject):
    """Listens for files sent by :func:`send_to_running`."""

    paths_received = pyqtSignal(list)

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_connection)
        name = name or server_name()
        # Asked first, because on Linux and macOS listening with socket options
        # replaces the socket file, which would cut off a copy still running
        # (one started a second time with no file). That copy keeps the name,
        # and this one goes without.
        if _answering(name):
            return
        if not self._server.listen(name):
            # A socket left behind by a copy that crashed.
            QLocalServer.removeServer(name)
            self._server.listen(name)

    @property
    def listening(self) -> bool:
        return self._server.isListening()

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            buffer = bytearray()

            def read(s=socket, buf=buffer) -> None:
                buf += bytes(s.readAll())
                if buf.endswith(b"\n"):
                    self._deliver(bytes(buf))
                    buf.clear()

            socket.readyRead.connect(read)
            socket.disconnected.connect(socket.deleteLater)

    def _deliver(self, raw: bytes) -> None:
        try:
            paths = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(paths, list) and paths:
            self.paths_received.emit([str(p) for p in paths])


class FileOpenFilter(QObject):
    """Turns macOS "open this file" events into :attr:`path_opened`.

    Installed on the application before the window exists, because Finder
    sends the event while the app is still starting; paths that arrive before
    anyone is listening are kept in :attr:`pending`.
    """

    path_opened = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pending: list[str] = []
        self._ready = False

    def set_ready(self) -> list[str]:
        """Start emitting, and return what arrived before now."""
        self._ready = True
        pending, self.pending = self.pending, []
        return pending

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt naming
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path:
                if self._ready:
                    self.path_opened.emit(path)
                else:
                    self.pending.append(path)
                return True
        return super().eventFilter(obj, event)
