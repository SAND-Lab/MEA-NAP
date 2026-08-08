"""A local web viewer for a ``.meanap`` bundle.

Express mode ships data instead of pictures; this serves the pictures back on
demand. The front end is HTML so the figures live where people already read
things, and so vector output is a click away rather than a file dialog; the
back end is the same Python that drew them in the pipeline, so what you see is
what the pipeline would have produced — the pixel-parity tests cover exactly
that path.

Deliberately stdlib-only (``http.server``): a viewer that needs a web framework
installed is a viewer a collaborator won't run. Bound to loopback by default,
because the bundle is unpublished research data and nothing here authenticates
anyone.

Endpoints
---------
``GET /``                     the page
``GET /api/manifest``         recordings, lags, figures, families, comparisons, controls
``GET /api/figure``           one network figure, restyled per the query string
``GET /api/activity``         one step-2 activity figure (raster, heatmap, …)
``GET /api/comparison``       one 2B/4B comparison figure, by facet
``GET /api/lagseries``        one across-lag figure (metric vs lag, roles per lag)
``GET /api/family``           a family's thumbnails (renders once, then cached)
``GET /api/asset``            a file from the render cache

``/api/comparison`` is what makes the batch comparisons navigable. A three-lag
run's 4B set is 274 small multiples, and ``/api/family`` can only hand over all
of them at once; each is one metric at one lag, so it has an address —
``family``, ``level``, ``split``, ``lag``, ``metric`` — and the page asks for
the one it is showing.

The styling controls apply to the spatial network plots only, so ``/api/family``
ignores them and the page hides the panel for gallery views rather than
offering knobs that do nothing.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from meanap.pipeline.bundle import is_bundle, open_bundle
from meanap.pipeline.figure_output import DEFAULT_THUMBNAIL_DPI
from meanap.pipeline.render import (
    available_activity_figures, available_comparison_families, available_figures,
    available_spike_check_figures, render_spike_check_figure, figure_variants,
    available_edge_check_lags, render_edge_check_figure,
    available_subnetwork_figures, render_subnetwork_figure,
    available_group_families, available_lag_series, cached_comparison_figure,
    cached_figure, cached_lag_series_figure, comparison_axes, gallery, load_context,
    render_activity_figure,
)
from meanap.pipeline.render_cache import RenderCache
from meanap.viewer.controls import (
    comparison_control_schema, control_schema, parse_comparison_overrides,
    parse_overrides,
)
from meanap.viewer.page import PAGE_HTML

__all__ = ["ViewerService", "serve"]

#: Formats a client may request. Anything else is rejected rather than passed
#: to matplotlib, whose error for an unknown suffix is not user-facing.
ALLOWED_FORMATS = ("png", "svg", "pdf")


class ViewerService:
    """Bundle + render cache + the queries the HTTP layer needs.

    Separated from the request handler so it can be driven directly in tests
    without a socket, and so a GUI could embed the same logic behind a
    ``QWebEngineView`` without going through HTTP at all.
    """

    def __init__(self, source: Path | str):
        source = Path(source)
        self._bundle = open_bundle(source) if is_bundle(source) else None
        root = self._bundle.root if self._bundle is not None else source
        self.ctx = load_context(self._bundle if self._bundle is not None else root)
        self.cache = RenderCache.in_temp()
        self.source = source

    def close(self) -> None:
        self.cache.close()
        if self._bundle is not None:
            self._bundle.close()

    # ── queries ──────────────────────────────────────────────────────────────

    def manifest(self) -> dict:
        recordings = []
        for name, rec in self.ctx.recordings.items():
            lags = self.ctx.lags(name)
            recordings.append({
                "name": name, "group": rec.group, "div": rec.div, "lags": lags,
                "figures": {
                    str(lag): [
                        {"name": f.name, "label": f.label,
                         # Which scalings this plot has here: only the spatial
                         # network plots have any, and only when the batch
                         # bounds their size metric needs were pooled.
                         "variants": figure_variants(
                             self.ctx, name, lag, f.name.format(lag=lag))}
                        for f in available_figures(self.ctx, name, lag)]
                    for lag in lags
                },
                # Step-2 figures are per recording, not per lag — a separate
                # list rather than a lag key, so the page can show them once.
                "activity": [{"name": f.name, "label": f.label}
                             for f in available_activity_figures(self.ctx, name)],
                # Step-1 checks are per recording too. Listed separately from
                # the step-2 activity set because they answer a different
                # question — did detection work — and a reader looking for that
                # should not have to find it among the rasters.
                "spike_checks": [{"name": f.name, "label": f.label}
                                 for f in available_spike_check_figures(
                                     self.ctx, name)],
                # One per lag, and usually empty: these only exist when the run
                # had thresholding checks switched on.
                "edge_checks": available_edge_check_lags(self.ctx, name),
                # Per lag, like the network figures — a cell type's role can
                # differ between lags, so these are addressed the same way.
                "subnetworks": {
                    str(lag): [{"name": f.name, "label": f.label}
                               for f in available_subnetwork_figures(
                                   self.ctx, name, lag)]
                    for lag in lags
                },
            })
        return {
            "source": self.source.name,
            # A folder cannot be exported: it already is one.
            "can_export": self._bundle is not None,
            "mode": self.ctx.mode,
            "recordings": recordings,
            "families": [{"key": f.key, "label": f.label}
                         for f in available_group_families(self.ctx)],
            "comparisons": self.comparisons(),
            "lag_series": self.lag_series(),
            "controls": control_schema(),
            "comparison_controls": comparison_control_schema(),
            "formats": list(ALLOWED_FORMATS),
        }

    def comparisons(self) -> list[dict]:
        """The facets behind the comparison tab: one entry per family.

        These families are the half-violin sets (4B network metrics, 2B
        neuronal activity), which are one metric per figure and therefore
        selectable. The gallery families in ``families`` above stay as they
        are — nothing there has an address to select by.
        """
        out = []
        for fam in available_comparison_families(self.ctx):
            axes = comparison_axes(self.ctx, fam.key)
            out.append({
                "key": axes.family,
                "label": axes.label,
                "lags": list(axes.lags),
                "levels": [
                    {"key": level.key, "label": level.label,
                     "metrics": [{"name": m.key, "label": m.label}
                                 for m in level.metrics]}
                    for level in axes.levels
                ],
                "splits": [{"key": s.key, "label": s.label} for s in axes.splits],
            })
        return out

    def lag_series(self) -> list[dict]:
        """The across-lag sets: graph metrics vs lag, and cartography per lag.

        Empty on a single-lag run — a curve through one point says nothing, so
        the tab is not offered rather than shown empty.
        """
        return [
            {"key": series.key, "label": series.label, "keyed_by": series.keyed_by,
             "options": [{"key": c.key, "label": c.label} for c in choices]}
            for series, choices in available_lag_series(self.ctx)
        ]

    def lag_series_figure(self, series: str, key: str, *,
                          fmt: str, thumbnail: bool, overrides: dict) -> Path:
        """One across-lag figure, by set and key. Cached like the rest."""
        path, _ = cached_lag_series_figure(
            self.ctx, self.cache, series, key, fmt=fmt,
            dpi=DEFAULT_THUMBNAIL_DPI if thumbnail else None,
            overrides=overrides or None,
        )
        return path

    def comparison(self, family: str, level: str, split: str, metric: str, *,
                   lag: int | None, fmt: str, thumbnail: bool,
                   overrides: dict) -> Path:
        """One comparison figure, by address. Cached like the 4A figures.

        The overrides here are the *comparison* controls (age and group
        colours), not the Network Viewer ones — a violin plot reads no node
        size or edge threshold, so those are neither accepted nor offered.
        """
        path, _ = cached_comparison_figure(
            self.ctx, self.cache, family, level, split, metric, lag=lag, fmt=fmt,
            dpi=DEFAULT_THUMBNAIL_DPI if thumbnail else None,
            overrides=overrides or None,
        )
        return path

    def figure(self, recording: str, lag: int, name: str, *,
               fmt: str, overrides: dict, thumbnail: bool,
               variant: str = "plain") -> Path:
        path, _ = cached_figure(
            self.ctx, self.cache, recording, lag, name, fmt=fmt,
            dpi=DEFAULT_THUMBNAIL_DPI if thumbnail else None,
            overrides=overrides or None, variant=variant,
        )
        return path

    def activity_figure(self, recording: str, name: str, *,
                        fmt: str, overrides: dict) -> Path:
        """One step-2 activity figure. Cached like the network ones."""
        from meanap.pipeline.render_cache import bundle_identity, cache_key

        key = cache_key(bundle_identity(self.ctx.root), f"act:{recording}:{name}",
                        fmt=fmt, dpi=None, overrides=overrides)
        files, _ = self.cache.get_or_render(
            key,
            lambda dest: [render_activity_figure(
                self.ctx, recording, name, dest, fmt=fmt,
                overrides=overrides or None)],
        )
        return files[0]

    def spike_check_figure(self, recording: str, name: str, *,
                           fmt: str) -> Path:
        """One step-1 check figure. No overrides — see render_spike_check_figure."""
        from meanap.pipeline.render_cache import bundle_identity, cache_key

        key = cache_key(bundle_identity(self.ctx.root), f"chk:{recording}:{name}",
                        fmt=fmt, dpi=None, overrides={})
        files, _ = self.cache.get_or_render(
            key,
            lambda dest: [render_spike_check_figure(
                self.ctx, recording, name, dest, fmt=fmt)],
        )
        return files[0]

    def edge_check_figure(self, recording: str, lag: int, *, fmt: str) -> Path:
        """One step-3 thresholding check. No overrides, like the step-1 ones."""
        from meanap.pipeline.render_cache import bundle_identity, cache_key

        key = cache_key(bundle_identity(self.ctx.root),
                        f"edge:{recording}:{lag}", fmt=fmt, dpi=None, overrides={})
        files, _ = self.cache.get_or_render(
            key,
            lambda dest: [render_edge_check_figure(
                self.ctx, recording, lag, dest, fmt=fmt)],
        )
        return files[0]

    def subnetwork_figure(self, recording: str, lag: int, name: str, *,
                          fmt: str) -> Path:
        """One per-recording cell-type subnetwork figure."""
        from meanap.pipeline.render_cache import bundle_identity, cache_key

        key = cache_key(bundle_identity(self.ctx.root),
                        f"subnet:{recording}:{lag}:{name}",
                        fmt=fmt, dpi=None, overrides={})
        files, _ = self.cache.get_or_render(
            key,
            lambda dest: [render_subnetwork_figure(
                self.ctx, recording, lag, name, dest, fmt=fmt)],
        )
        return files[0]

    def export(self) -> dict:
        """Draw this bundle out into an ordinary output folder.

        For sending results to someone with no MEA-NAP: they get the figures as
        files and a self-contained ``report.html`` to browse them with. Only
        meaningful when the viewer was opened on a bundle — pointed at a folder
        there is nothing to unpack.
        """
        from meanap.pipeline.export import export_output_folder

        if self._bundle is None:
            raise ValueError(
                "This viewer is showing an output folder, not a bundle, so "
                "there is nothing to export — the folder is already the folder.")
        from meanap.pipeline.export import default_export_dest

        # Beside the bundle file the user opened, not beside its extracted copy.
        result = export_output_folder(
            self._bundle, default_export_dest(self.source), log=lambda m: None)
        return {
            "dest": str(result.dest),
            "figures": result.figures,
            "report": str(result.report) if result.report else None,
            "skipped": [{"what": w, "why": why} for w, why in result.skipped],
        }

    def family(self, key: str, *, fmt: str = "png") -> dict:
        """Render (or serve cached) a family, as asset references.

        Paths are returned relative to the cache root and resolved back through
        :meth:`asset`, so the client never sees or supplies a filesystem path.
        """
        files, was_cached = gallery(self.ctx, key, self.cache, fmt=fmt)
        items = []
        for path in files:
            rel = path.relative_to(self.cache.root)
            # The folder tree is how the pipeline groups these (by lag, by
            # comparison axis); keep it as the caption so a gallery of 109
            # small multiples is navigable rather than a wall of names.
            items.append({
                "asset": rel.as_posix(),
                "name": path.stem,
                "group": rel.parent.as_posix(),
            })
        return {"cached": was_cached, "count": len(items), "items": items}

    def asset(self, relative: str) -> Path:
        """Resolve a cache-relative path, refusing anything that escapes it."""
        root = self.cache.root.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise FileNotFoundError(relative)
        return target


class _Handler(BaseHTTPRequestHandler):
    service: ViewerService = None  # set by serve()
    server_version = "MEA-NAP-viewer"

    def log_message(self, *args) -> None:  # noqa: D102 - quieten stderr spam
        pass

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE_HTML.encode())
            elif parsed.path == "/api/manifest":
                self._json(self.service.manifest())
            elif parsed.path == "/api/figure":
                self._figure(query)
            elif parsed.path == "/api/activity":
                self._activity(query)
            elif parsed.path == "/api/spikecheck":
                self._spike_check(query)
            elif parsed.path == "/api/edgecheck":
                self._edge_check(query)
            elif parsed.path == "/api/subnetwork":
                self._subnetwork(query)
            elif parsed.path == "/api/export":
                self._json(self.service.export())
            elif parsed.path == "/api/comparison":
                self._comparison(query)
            elif parsed.path == "/api/lagseries":
                self._lag_series(query)
            elif parsed.path == "/api/family":
                self._json(self.service.family(
                    _one(query, "key"), fmt=_fmt(query)))
            elif parsed.path == "/api/asset":
                self._file(self.service.asset(_one(query, "path")))
            else:
                self._json({"error": "not found"}, status=404)
        except FileNotFoundError as e:
            self._json({"error": f"not found: {e}"}, status=404)
        except ValueError as e:
            # Bad input from the page: report it verbatim, it is actionable.
            self._json({"error": str(e)}, status=400)
        except Exception as e:
            self._json({"error": f"{type(e).__name__}: {e}",
                        "traceback": traceback.format_exc()}, status=500)

    # ── handlers ─────────────────────────────────────────────────────────────

    def _figure(self, query) -> None:
        fmt = _fmt(query)
        path = self.service.figure(
            _one(query, "rec"), int(_one(query, "lag")), _one(query, "name"),
            fmt=fmt, overrides=parse_overrides(query),
            thumbnail=query.get("thumb", ["0"])[0] == "1",
            variant=query.get("variant", ["plain"])[0],
        )
        download = query.get("download", ["0"])[0] == "1"
        self._file(path, download_as=path.name if download else None)

    def _activity(self, query) -> None:
        fmt = _fmt(query)
        path = self.service.activity_figure(
            _one(query, "rec"), _one(query, "name"),
            fmt=fmt, overrides=parse_overrides(query))
        download = query.get("download", ["0"])[0] == "1"
        self._file(path, download_as=path.name if download else None)

    def _spike_check(self, query) -> None:
        fmt = _fmt(query)
        path = self.service.spike_check_figure(
            _one(query, "rec"), _one(query, "name"), fmt=fmt)
        download = query.get("download", ["0"])[0] == "1"
        self._file(path, download_as=path.name if download else None)

    def _edge_check(self, query) -> None:
        fmt = _fmt(query)
        path = self.service.edge_check_figure(
            _one(query, "rec"), int(_one(query, "lag")), fmt=fmt)
        download = query.get("download", ["0"])[0] == "1"
        self._file(path, download_as=path.name if download else None)

    def _subnetwork(self, query) -> None:
        fmt = _fmt(query)
        path = self.service.subnetwork_figure(
            _one(query, "rec"), int(_one(query, "lag")), _one(query, "name"),
            fmt=fmt)
        download = query.get("download", ["0"])[0] == "1"
        self._file(path, download_as=path.name if download else None)

    def _comparison(self, query) -> None:
        fmt = _fmt(query)
        path = self.service.comparison(
            _one(query, "family"), _one(query, "level"), _one(query, "split"),
            _one(query, "metric"), lag=_optional_int(query, "lag"), fmt=fmt,
            thumbnail=query.get("thumb", ["0"])[0] == "1",
            overrides=parse_comparison_overrides(query),
        )
        download = query.get("download", ["0"])[0] == "1"
        self._file(path, download_as=path.name if download else None)

    def _lag_series(self, query) -> None:
        fmt = _fmt(query)
        path = self.service.lag_series_figure(
            _one(query, "series"), _one(query, "key"), fmt=fmt,
            thumbnail=query.get("thumb", ["0"])[0] == "1",
            overrides=parse_comparison_overrides(query),
        )
        download = query.get("download", ["0"])[0] == "1"
        self._file(path, download_as=path.name if download else None)

    # ── plumbing ─────────────────────────────────────────────────────────────

    def _send(self, status: int, content_type: str, body: bytes,
              extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, "application/json", json.dumps(payload).encode())

    def _file(self, path: Path, download_as: str | None = None) -> None:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        extra = ({"Content-Disposition": f'attachment; filename="{download_as}"'}
                 if download_as else {})
        self._send(200, ctype, path.read_bytes(), extra)


def _one(query: dict, key: str) -> str:
    value = query.get(key, [None])[0]
    if not value:
        raise ValueError(f"missing required parameter '{key}'")
    return value


def _optional_int(query: dict, key: str) -> int | None:
    """An optional whole-number parameter, absent or blank meaning "not given".

    ``int()``'s own message ("invalid literal for int() with base 10") reaches
    the page as the error text, so it is replaced with one naming the parameter.
    """
    value = query.get(key, [None])[0]
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"'{key}' must be a whole number, got {value!r}") from None


def _fmt(query: dict) -> str:
    fmt = query.get("fmt", ["png"])[0]
    if fmt not in ALLOWED_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; expected one of "
                         f"{list(ALLOWED_FORMATS)}")
    return fmt


#: Default port. Not 8765 — that is AnkiConnect's, and a collision there is
#: nastier than it sounds: ``HTTPServer`` sets ``SO_REUSEADDR``, so binding can
#: succeed while the browser reaches the *other* application. Hence
#: :func:`_port_in_use` below, which probes before binding rather than trusting
#: bind() to fail.
DEFAULT_PORT = 8912


def _port_in_use(host: str, port: int) -> bool:
    """Whether something is already answering on ``host:port``."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((host, port)) == 0


def serve(
    source: Path | str,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = False,
    background: bool = False,
):
    """Serve *source* (a ``.meanap`` bundle or an output folder).

    Returns ``(httpd, service)``. With ``background=True`` the server runs on a
    daemon thread and the call returns immediately — how the tests drive it;
    otherwise it blocks until interrupted.

    ``host`` defaults to loopback deliberately. The bundle is unpublished data
    and there is no authentication here, so binding to a routable address would
    expose it to the network; do that only on a machine where that is intended.
    """
    if port and _port_in_use(host, port):
        raise OSError(
            f"Port {port} on {host} is already in use by another application, so "
            f"the viewer would be unreachable there (a browser would get that "
            f"application instead). Pass --port with a free port, or 0 to let the "
            f"system choose one."
        )

    service = ViewerService(source)
    handler = type("_BoundHandler", (_Handler,), {"service": service})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    url = f"http://{host}:{httpd.server_address[1]}/"

    if open_browser:
        import webbrowser
        webbrowser.open(url)

    if background:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, service

    print(f"MEA-NAP viewer: {url}   (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        httpd.shutdown()
        service.close()
    return httpd, service


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="meanap-viewer",
        description="Browse a .meanap bundle (or an output folder) in a browser.")
    ap.add_argument("source", help="a .meanap bundle or an OutputData… folder")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="0 lets the system choose a free port")
    ap.add_argument("--no-browser", action="store_true",
                    help="don't open a browser window")
    args = ap.parse_args(argv)

    serve(args.source, args.host, args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
