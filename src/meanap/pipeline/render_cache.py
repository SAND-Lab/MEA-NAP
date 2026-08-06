"""Cache for figures rendered from a bundle.

The batch comparison families are produced by plotters that emit a whole folder
in one call — ``plot_step4_group_comparisons`` writes all 109 of its figures
per invocation and cannot be asked for just one. So a gallery cannot render
lazily as the reader scrolls; it renders the family, or it renders nothing.

That is affordable if it happens once. At the thumbnail resolution
(:data:`~meanap.pipeline.figure_output.DEFAULT_THUMBNAIL_DPI`) a 109-figure
family takes about six seconds; every view after the first should be a file
read. This module is that "after the first".

Entries are keyed by everything that can change a pixel — the bundle's
identity, the family, the image format, the resolution, and any styling
overrides — so a restyled view is a different entry rather than a stale hit.
The key deliberately does *not* include a timestamp: the same bundle rendered
the same way must hit, or the cache is pointless.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["RenderCache", "cache_key"]


def cache_key(
    bundle_id: str,
    family: str,
    *,
    fmt: str = "png",
    dpi: int | None = None,
    overrides: dict | None = None,
) -> str:
    """A stable digest of everything that affects the rendered output."""
    payload = json.dumps(
        {
            "bundle": bundle_id,
            "family": family,
            "fmt": fmt,
            "dpi": dpi,
            # Sorted so two equivalent override dicts share one entry.
            "overrides": sorted((overrides or {}).items(), key=lambda kv: kv[0]),
        },
        sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def bundle_identity(path: Path | str) -> str:
    """Identify a bundle by content, not by name.

    Two people can hold the same analysis under different filenames, and one
    person can overwrite a bundle in place while keeping its name. Hashing the
    bytes gets both cases right; for bundles of a megabyte or so it costs
    milliseconds.
    """
    p = Path(path)
    if not p.is_file():
        # An unpacked output folder: fall back to its resolved path plus the
        # metrics file's mtime, which is the thing a re-run would change.
        metrics = p / "4_NetworkActivity" / "netmet_results.json"
        stamp = metrics.stat().st_mtime_ns if metrics.exists() else 0
        return hashlib.sha256(f"{p.resolve()}:{stamp}".encode()).hexdigest()[:20]

    digest = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:20]


@dataclass
class RenderCache:
    """A directory of rendered figure sets, addressed by :func:`cache_key`.

    Not thread-safe against concurrent *writes* of the same key: two requests
    racing on a cold entry would both render. That is wasteful but harmless —
    the render is deterministic, so whichever finishes last writes the same
    bytes. Serialising it would mean holding a lock across a six-second render,
    which is worse.
    """

    root: Path
    _owned_tempdir: str | None = None

    @classmethod
    def in_temp(cls) -> "RenderCache":
        """A cache in a temporary directory, cleaned up by :meth:`close`."""
        tmp = tempfile.mkdtemp(prefix="meanap-render-cache-")
        return cls(root=Path(tmp), _owned_tempdir=tmp)

    def path_for(self, key: str) -> Path:
        return self.root / key

    def get(self, key: str) -> list[Path] | None:
        """Cached files for *key*, or ``None`` on a miss.

        A directory without its ``.complete`` marker counts as a miss: it means
        a previous render died partway, and half a gallery is worse than none.
        """
        entry = self.path_for(key)
        if not (entry / ".complete").exists():
            return None
        return sorted(p for p in entry.rglob("*")
                      if p.is_file() and p.name != ".complete")

    def put(self, key: str, render) -> list[Path]:
        """Render into the entry for *key* and mark it complete.

        ``render`` is called with the destination directory and should return
        the files it wrote. A failed render leaves no marker, so the next
        request retries rather than serving a partial set.
        """
        entry = self.path_for(key)
        if entry.exists():
            shutil.rmtree(entry, ignore_errors=True)
        entry.mkdir(parents=True, exist_ok=True)
        written = list(render(entry))
        (entry / ".complete").write_text(str(len(written)))
        return written

    def get_or_render(self, key: str, render) -> tuple[list[Path], bool]:
        """Return ``(files, was_cached)``."""
        hit = self.get(key)
        if hit is not None:
            return hit, True
        return self.put(key, render), False

    def clear(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        if self._owned_tempdir is not None:
            shutil.rmtree(self._owned_tempdir, ignore_errors=True)
            self._owned_tempdir = None

    def __enter__(self) -> "RenderCache":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
