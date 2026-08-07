"""A local directory, presented as a :class:`~meanap.remote.base.RemoteStore`.

Exists so the pipeline has one code path rather than two. The important detail
is that :meth:`LocalStore.fetch` returns the *original* path instead of copying:
a local run must not duplicate gigabytes to satisfy an abstraction, and the
cache knows not to account for bytes it doesn't own (``copies = False``).
"""

from __future__ import annotations

from pathlib import Path

from meanap.remote.base import ProgressFn, RemoteEntry, store_id_for

__all__ = ["LocalStore"]


class LocalStore:
    """Reads a directory tree that is already on this machine."""

    copies = False

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.store_id = store_id_for("local", str(self.root))

    def __repr__(self) -> str:
        return f"LocalStore({self.root})"

    def _resolve(self, path: str) -> Path:
        """Join a store-relative path, refusing anything that escapes the root.

        The paths come from spreadsheets and recording names, so a stray ``..``
        is a user error rather than an attack — but the failure should be a
        clear refusal either way.
        """
        target = (self.root / path.strip("/")).resolve() if path else self.root
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"{path!r} points outside {self.root}")
        return target

    def list(self, path: str = "") -> list[RemoteEntry]:
        target = self._resolve(path)
        if not target.is_dir():
            return []
        prefix = f"{path.strip('/')}/" if path.strip("/") else ""
        out = []
        for child in sorted(target.iterdir()):
            out.append(RemoteEntry(
                path=f"{prefix}{child.name}",
                is_dir=child.is_dir(),
                size=None if child.is_dir() else child.stat().st_size,
            ))
        return out

    def stat(self, path: str) -> RemoteEntry | None:
        try:
            target = self._resolve(path)
        except ValueError:
            return None
        if not target.exists():
            return None
        return RemoteEntry(
            path=path.strip("/"), is_dir=target.is_dir(),
            size=None if target.is_dir() else target.stat().st_size,
        )

    def fetch(self, path: str, dest: Path, progress: ProgressFn | None = None) -> Path:
        """Return the file where it already is; *dest* is ignored."""
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"{path} not found under {self.root}")
        if progress is not None:
            size = target.stat().st_size
            progress(size, size)
        return target
