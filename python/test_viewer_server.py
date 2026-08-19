"""Test the local web viewer: real HTTP requests against a real bundle.

Run from the repo root::

    uv run python python/test_viewer_server.py

Driven over a socket rather than by calling handlers directly, because the
things most likely to break are at that boundary — query-string coercion, the
content types a browser needs to display an SVG inline, the download headers,
and the path guard on cached assets.

The behaviour worth protecting above all: **an unstyled request must return the
figure the pipeline drew.** The viewer is only trustworthy if its default view
is the real one, so that is checked byte-for-byte against a full pipeline run.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "python"))

from test_bundle_render import (  # noqa: E402
    BUNDLE_SUFFIX, LAG, _digest, _run,
)

Check = tuple[str, bool, str]


def _report(title: str, checks: list[Check]) -> tuple[int, int]:
    print(f"\n{title}")
    n_pass = 0
    for name, ok, detail in checks:
        flag = "✓" if ok else "✗"
        suffix = "" if ok else (f"  [{detail}]" if detail else "")
        print(f"  {flag} {name}{suffix}")
        n_pass += bool(ok)
    print(f"  → {n_pass}/{len(checks)} passed")
    return n_pass, len(checks)


def _get(url: str) -> tuple[int, bytes, dict]:
    """GET, returning ``(status, body, headers)`` without raising on 4xx/5xx."""
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def _all_checks() -> list[Check]:
    from meanap.viewer.server import serve

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = _run(tmp, "Full", express=False)
        express = _run(tmp, "Express", express=True)
        bundle = express.with_suffix(BUNDLE_SUFFIX)

        httpd, service = serve(bundle, port=0, background=True)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            # ── the page ────────────────────────────────────────────────────
            status, body, headers = _get(base + "/")
            checks.append(("page is served", status == 200, str(status)))
            checks.append(("page is html",
                           headers.get("Content-Type", "").startswith("text/html"), ""))
            checks.append(("page has the control panel and gallery containers",
                           b'id="controls-panel"' in body and b'id="gallery"' in body, ""))

            # ── manifest ────────────────────────────────────────────────────
            status, body, _ = _get(base + "/api/manifest")
            man = json.loads(body)
            checks.append(("manifest is served", status == 200, str(status)))
            checks.append(("manifest lists both recordings",
                           {r["name"] for r in man["recordings"]} == {"recA", "recB"},
                           f"{[r['name'] for r in man['recordings']]}"))
            rec = man["recordings"][0]
            checks.append(("manifest lists lags and figures",
                           rec["lags"] == [LAG] and len(rec["figures"][str(LAG)]) >= 5,
                           f"{rec['lags']}"))
            checks.append(("manifest advertises comparison families",
                           len(man["families"]) >= 2, f"{man['families']}"))
            checks.append(("manifest carries the control schema",
                           len(man["controls"]) == 11,
                           f"{len(man['controls'])}"))
            checks.append(("controls declare kind, default and options",
                           all({"key", "kind", "default", "options"} <= set(c)
                               for c in man["controls"]), ""))

            fig = "2_MEA_NetworkPlot"

            # ── the load-bearing one: default view == the pipeline's figure ──
            status, body, headers = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}")
            checks.append(("figure is served", status == 200, str(status)))
            checks.append(("figure is a png",
                           headers.get("Content-Type") == "image/png",
                           headers.get("Content-Type", "")))
            served = tmp / "served.png"
            served.write_bytes(body)
            original = (full / "4_NetworkActivity" / "4A_IndividualNetworkAnalysis"
                        / "WT" / "recA" / f"{LAG}mslag" / f"{fig}.png")
            checks.append(("unstyled request is pixel-identical to the pipeline's",
                           _digest(original) == _digest(served), ""))

            # ── styling ─────────────────────────────────────────────────────
            _, styled, _ = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}&colormap=magma")
            checks.append(("a styling parameter changes the image",
                           styled != body, ""))
            _, same, _ = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}&colormap=viridis")
            checks.append(("passing a default is a no-op (still the pipeline's)",
                           same == body, ""))
            _, layout, _ = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}"
                "&layout=Circular&max_edges=4&node_size_scale=2")
            checks.append(("several controls compose", layout not in (body, styled), ""))

            # ── vector formats and downloads ────────────────────────────────
            status, svg, headers = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}&fmt=svg")
            checks.append(("svg is served as svg",
                           status == 200 and "svg" in headers.get("Content-Type", ""),
                           headers.get("Content-Type", "")))
            checks.append(("svg body is vector markup", b"<svg" in svg[:400], ""))
            status, pdf, headers = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}&fmt=pdf")
            checks.append(("pdf is served", status == 200 and pdf[:4] == b"%PDF", ""))
            _, _, headers = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}&fmt=svg&download=1")
            checks.append(("download sets an attachment filename",
                           "attachment" in headers.get("Content-Disposition", ""),
                           headers.get("Content-Disposition", "")))

            # ── families ────────────────────────────────────────────────────
            status, body, _ = _get(base + "/api/family?key=network")
            fam = json.loads(body)
            checks.append(("family renders", status == 200 and fam["count"] > 50,
                           f"{fam.get('count')}"))
            checks.append(("first family view is not cached", fam["cached"] is False, ""))
            checks.append(("family items carry asset refs, not file paths",
                           all("asset" in i and not i["asset"].startswith("/")
                               for i in fam["items"]), ""))
            _, body2, _ = _get(base + "/api/family?key=network")
            checks.append(("second family view is cached",
                           json.loads(body2)["cached"] is True, ""))

            asset = fam["items"][0]["asset"]
            status, img, headers = _get(
                base + "/api/asset?path=" + urllib.parse.quote(asset))
            checks.append(("a family asset is served",
                           status == 200 and headers.get("Content-Type") == "image/png",
                           str(status)))

            # ── step-2 activity figures ─────────────────────────────────────
            # This fixture is a CAT-NAP bundle, which has no step-2 ephys data,
            # so the correct answer is an empty list — not a broken endpoint.
            # The ephys path is covered in test_bundle_render.py, against a
            # bundle that actually has spike times.
            act = man["recordings"][0].get("activity", [])
            checks.append(("a CAT-NAP bundle offers no ephys activity figures",
                           act == [], f"{act}"))
            status, body, _ = _get(base + "/api/activity?rec=recA&name=3_Raster")
            checks.append(("asking for one anyway is a 400 with a reason",
                           status == 400
                           and "step-2 activity data" in json.loads(body)["error"],
                           str(status)))

            # ── errors are actionable, not stack traces ─────────────────────
            status, body, _ = _get(base + "/api/asset?path=../../../etc/passwd")
            checks.append(("path traversal on assets is refused",
                           status == 404, str(status)))
            status, body, _ = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}&fmt=exe")
            checks.append(("an unsupported format is rejected with 400",
                           status == 400 and "unsupported format"
                           in json.loads(body)["error"], str(status)))
            status, body, _ = _get(
                f"{base}/api/figure?rec=recA&lag={LAG}&name={fig}&layout=Nonsense")
            checks.append(("an invalid control value is rejected with 400",
                           status == 400 and "layout" in json.loads(body)["error"],
                           str(status)))
            status, body, _ = _get(f"{base}/api/figure?rec=recA&lag={LAG}")
            checks.append(("a missing parameter is reported by name",
                           status == 400 and "name" in json.loads(body)["error"],
                           str(status)))
            status, body, _ = _get(base + "/api/figure?rec=ghost&lag=25&name=" + fig)
            checks.append(("an unknown recording is a 400, not a 500",
                           status == 400, str(status)))
            status, _, _ = _get(base + "/api/nope")
            checks.append(("unknown routes 404", status == 404, str(status)))
        finally:
            httpd.shutdown()
            service.close()
    return checks


def _comparison_checks() -> list[Check]:
    """``/api/comparison``: the facets, and one figure at a time.

    The gallery route can only hand over a whole family — 274 figures on a
    three-lag run. These are the requests the comparison tab makes instead, so
    what matters is that the advertised facets are exactly the addresses that
    render, and that a bad one comes back as an actionable 400 rather than a
    traceback.
    """
    from meanap.viewer.server import serve

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = _run(tmp, "Full", express=False)
        express = _run(tmp, "Express", express=True)
        bundle = express.with_suffix(BUNDLE_SUFFIX)

        httpd, service = serve(bundle, port=0, background=True)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            _, body, _ = _get(base + "/api/manifest")
            man = json.loads(body)
            comparisons = {c["key"]: c for c in man.get("comparisons", [])}
            checks.append(("the manifest advertises the network comparison family",
                           "network" in comparisons, f"{sorted(comparisons)}"))
            net = comparisons.get("network", {})
            checks.append(("…with this run's lags", net.get("lags") == [LAG],
                           f"{net.get('lags')}"))
            checks.append(("…both levels, each with its metric list",
                           {lv["key"] for lv in net.get("levels", [])}
                           == {"recording", "node"}
                           and all(lv["metrics"] for lv in net["levels"]),
                           f"{[(lv['key'], len(lv['metrics'])) for lv in net.get('levels', [])]}"))
            checks.append(("…and both splits",
                           [s["key"] for s in net.get("splits", [])] == ["group", "age"],
                           f"{net.get('splits')}"))
            checks.append(("every facet carries a label for the UI",
                           all(lv.get("label") for lv in net["levels"])
                           and all(s.get("label") for s in net["splits"])
                           and all(m.get("label")
                                   for lv in net["levels"] for m in lv["metrics"]), ""))

            metric = net["levels"][0]["metrics"][0]["name"]
            address = (f"family=network&level=recording&split=group"
                       f"&metric={metric}&lag={LAG}")

            status, body, headers = _get(f"{base}/api/comparison?{address}")
            checks.append(("a comparison figure is served", status == 200, str(status)))
            checks.append(("…as a png", headers.get("Content-Type") == "image/png",
                           headers.get("Content-Type", "")))
            checks.append(("…with actual bytes in it", len(body) > 1000, f"{len(body)}"))

            # The load-bearing one: what the endpoint serves must be the figure
            # the pipeline wrote, not merely something plausible.
            original = (full / "4_NetworkActivity" / "4B_GroupComparisons"
                        / "3_RecordingsByGroup" / "HalfViolinPlots" / f"Lag{LAG}ms"
                        / f"{metric}_byGroup.png")
            checks.append(("…identical to the figure the full run wrote",
                           original.exists()
                           and hashlib.sha256(body).hexdigest() == _digest(original),
                           f"{original.name} exists={original.exists()}"))

            _, svg, headers = _get(f"{base}/api/comparison?{address}&fmt=svg")
            checks.append(("svg is vector markup",
                           headers.get("Content-Type") == "image/svg+xml"
                           and b"<svg" in svg[:600], headers.get("Content-Type", "")))

            _, _, headers = _get(f"{base}/api/comparison?{address}&download=1")
            checks.append(("download sets a filename",
                           f"{metric}_byGroup.png"
                           in headers.get("Content-Disposition", ""),
                           headers.get("Content-Disposition", "")))

            _, thumb, _ = _get(f"{base}/api/comparison?{address}&thumb=1")
            checks.append(("a thumbnail is smaller than the full render",
                           0 < len(thumb) < len(body), f"{len(thumb)} vs {len(body)}"))

            # Every advertised address must actually render — an offered
            # control that 500s is worse than one that isn't there.
            rendered = failed = 0
            for level in net["levels"]:
                for split in net["splits"]:
                    for m in level["metrics"]:
                        st, _, _ = _get(
                            f"{base}/api/comparison?family=network&level={level['key']}"
                            f"&split={split['key']}&metric={m['name']}&lag={LAG}&thumb=1")
                        rendered += st == 200
                        failed += st != 200
            checks.append((f"every advertised address renders ({rendered} of them)",
                           failed == 0 and rendered > 0, f"{failed} failed"))

            for query, expect, name in [
                ("family=nope&level=recording&split=group&metric=Dens&lag=25",
                 "Unknown comparison family", "unknown family"),
                ("family=network&level=cells&split=group&metric=Dens&lag=25",
                 "Unknown level", "unknown level"),
                ("family=network&level=recording&split=sideways&metric=Dens&lag=25",
                 "Unknown split", "unknown split"),
                ("family=network&level=recording&split=group&metric=Nope&lag=25",
                 "recording-level metric", "unknown metric"),
                ("family=network&level=recording&split=group&metric=Dens&lag=999",
                 "this run has", "a lag the run lacks"),
                ("family=network&level=recording&split=group&metric=Dens",
                 "per-lag", "a missing lag"),
                ("family=network&level=recording&split=group&metric=Dens&lag=abc",
                 "whole number", "a non-numeric lag"),
                ("family=network&level=recording&metric=Dens&lag=25",
                 "missing required parameter 'split'", "a missing facet"),
                ("family=network&level=recording&split=group&metric=Dens&lag=25&fmt=tiff",
                 "unsupported format", "an unsupported format"),
            ]:
                status, body, _ = _get(f"{base}/api/comparison?{query}")
                message = json.loads(body).get("error", "")
                checks.append((f"{name} is a 400 that says why",
                               status == 400 and expect in message,
                               f"{status}: {message[:60]}"))
        finally:
            httpd.shutdown()
            service.close()
    return checks


def _lag_series_checks() -> list[Check]:
    """The Across-lags tab: figures whose subject is the lag itself.

    Needs a two-lag run — the sets are deliberately not offered on a one-lag
    run, since a curve through one point says nothing, and that suppression is
    itself worth checking.
    """
    from meanap.viewer.server import serve

    checks: list[Check] = []
    lags = (10, 25)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = _run(tmp, "MultiFull", express=False, lags=lags)
        express = _run(tmp, "MultiExpress", express=True, lags=lags)

        httpd, service = serve(express.with_suffix(BUNDLE_SUFFIX), port=0,
                               background=True)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            _, body, _ = _get(base + "/api/manifest")
            man = json.loads(body)
            sets = {s["key"]: s for s in man.get("lag_series", [])}
            checks.append(("a multi-lag run offers both across-lag sets",
                           {"graph_metrics", "cartography"} <= set(sets),
                           f"{sorted(sets)}"))
            checks.append(("graph metrics are keyed by metric",
                           sets["graph_metrics"]["keyed_by"] == "metric"
                           and len(sets["graph_metrics"]["options"]) > 5,
                           f"{len(sets.get('graph_metrics', {}).get('options', []))}"))
            checks.append(("cartography is keyed by lag, one per lag",
                           sets["cartography"]["keyed_by"] == "lag"
                           and [o["key"] for o in sets["cartography"]["options"]]
                           == [str(x) for x in lags],
                           f"{[o['key'] for o in sets['cartography']['options']]}"))
            checks.append(("lag options are labelled in ms",
                           all(o["label"].endswith(" ms")
                               for o in sets["cartography"]["options"]), ""))

            metric = sets["graph_metrics"]["options"][0]["key"]
            status, curve, headers = _get(
                f"{base}/api/lagseries?series=graph_metrics&key={metric}")
            checks.append(("a lag curve is served", status == 200, str(status)))
            checks.append(("…as a png",
                           headers.get("Content-Type") == "image/png", ""))
            original = (full / "4_NetworkActivity" / "4B_GroupComparisons"
                        / "5_GraphMetricsByLag" / f"{metric}.png")
            checks.append(("…identical to the figure the full run wrote",
                           original.exists()
                           and hashlib.sha256(curve).hexdigest() == _digest(original),
                           f"{original.name} exists={original.exists()}"))

            status, roles, _ = _get(
                f"{base}/api/lagseries?series=cartography&key={lags[0]}")
            cart = (full / "4_NetworkActivity" / "4B_GroupComparisons"
                    / "6_NodeCartographyByLag" / f"NodeCartography{lags[0]}mslag.png")
            checks.append(("a cartography figure is served and identical",
                           status == 200 and cart.exists()
                           and hashlib.sha256(roles).hexdigest() == _digest(cart),
                           f"{status} exists={cart.exists()}"))

            _, svg, headers = _get(
                f"{base}/api/lagseries?series=graph_metrics&key={metric}&fmt=svg")
            checks.append(("across-lag figures export as vector svg",
                           headers.get("Content-Type") == "image/svg+xml"
                           and b"<svg" in svg[:600], ""))

            rendered = failed = 0
            for spec in sets.values():
                for opt in spec["options"]:
                    st, _, _ = _get(f"{base}/api/lagseries?series={spec['key']}"
                                    f"&key={opt['key']}&thumb=1")
                    rendered += st == 200
                    failed += st != 200
            checks.append((f"every advertised across-lag figure renders ({rendered})",
                           failed == 0 and rendered > 0, f"{failed} failed"))

            for query, expect, name in [
                ("series=nope&key=Dens", "Unknown across-lag set", "an unknown set"),
                ("series=graph_metrics&key=Nope", "recording-level metric",
                 "an unknown metric"),
                ("series=cartography&key=999", "this run has", "a lag the run lacks"),
                ("series=cartography&key=abc", "keyed by lag", "a non-numeric lag"),
                ("series=graph_metrics", "missing required parameter 'key'",
                 "a missing key"),
            ]:
                status, body, _ = _get(f"{base}/api/lagseries?{query}")
                message = json.loads(body).get("error", "")
                checks.append((f"{name} is a 400 that says why",
                               status == 400 and expect in message,
                               f"{status}: {message[:60]}"))
        finally:
            httpd.shutdown()
            service.close()

        # A one-lag run must not advertise a tab with nothing behind it.
        single = _run(tmp, "SingleLag", express=True)
        httpd, service = serve(single.with_suffix(BUNDLE_SUFFIX), port=0,
                               background=True)
        try:
            _, body, _ = _get(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/manifest")
            checks.append(("a one-lag run offers no across-lag sets",
                           json.loads(body)["lag_series"] == [],
                           f"{json.loads(body)['lag_series']}"))
        finally:
            httpd.shutdown()
            service.close()
    return checks


def _color_checks() -> list[Check]:
    """Age and group colours over HTTP: presets, custom lists, and defaults.

    The default path is the one that matters most — an unstyled request must
    still be the pipeline's own figure, which is what every parity claim in
    these suites rests on.
    """
    from meanap.viewer.server import serve

    checks: list[Check] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        full = _run(tmp, "Full", express=False)
        express = _run(tmp, "Express", express=True)

        httpd, service = serve(express.with_suffix(BUNDLE_SUFFIX), port=0,
                               background=True)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            _, body, _ = _get(base + "/api/manifest")
            controls = {c["key"]: c for c in json.loads(body).get("comparison_controls", [])}
            checks.append(("the manifest advertises the colour controls",
                           {"age_color_scheme", "age_colors", "group_color_scheme",
                            "group_colors"} == set(controls),
                           f"{sorted(controls)}"))
            checks.append(("the schemes are offered as options",
                           len(controls["group_color_scheme"]["options"]) >= 3
                           and len(controls["age_color_scheme"]["options"]) >= 5, ""))
            checks.append(("custom colours are a free-text control",
                           controls["group_colors"]["kind"] == "colors", ""))
            checks.append(("every control explains itself",
                           all(c["help"] for c in controls.values()), ""))

            address = ("family=network&level=recording&split=age&metric=Dens"
                       f"&lag={LAG}")
            _, plain, _ = _get(f"{base}/api/comparison?{address}")
            _, same, _ = _get(
                f"{base}/api/comparison?{address}&group_color_scheme=meanap")
            _, okabe, _ = _get(
                f"{base}/api/comparison?{address}&group_color_scheme=okabe-ito")
            _, custom, _ = _get(
                f"{base}/api/comparison?{address}&group_colors=%23ff0000,%230000ff")

            original = (full / "4_NetworkActivity" / "4B_GroupComparisons"
                        / "4_RecordingsByAge" / "HalfViolinPlots" / f"Lag{LAG}ms"
                        / "Dens_byDIV.png")
            checks.append(("an unstyled request is still the pipeline's figure",
                           original.exists()
                           and hashlib.sha256(plain).hexdigest() == _digest(original),
                           f"exists={original.exists()}"))
            checks.append(("asking for the default scheme changes nothing",
                           hashlib.sha256(same).hexdigest()
                           == hashlib.sha256(plain).hexdigest(), ""))
            checks.append(("a preset changes the figure",
                           hashlib.sha256(okabe).hexdigest()
                           != hashlib.sha256(plain).hexdigest(), ""))
            checks.append(("custom colours change it differently again",
                           len({hashlib.sha256(b).hexdigest()
                                for b in (plain, okabe, custom)}) == 3, ""))

            # Across-lag figures colour their lines by DIV, so they read the
            # age scheme; the same panel drives both, so it must reach here.
            metric = "Dens"
            _, curve, _ = _get(f"{base}/api/lagseries?series=graph_metrics&key={metric}")
            _, curve2, _ = _get(f"{base}/api/lagseries?series=graph_metrics"
                                f"&key={metric}&age_color_scheme=plasma")
            checks.append(("across-lag figures honour the age scheme",
                           len(curve) > 0 and hashlib.sha256(curve).hexdigest()
                           != hashlib.sha256(curve2).hexdigest(), ""))

            for query, expect, name in [
                ("&group_colors=%23zzzzzz", "is not a colour", "a bad colour code"),
                ("&age_color_scheme=jet", "is not one of", "a scheme that isn't offered"),
            ]:
                status, body, _ = _get(f"{base}/api/comparison?{address}{query}")
                message = json.loads(body).get("error", "")
                checks.append((f"{name} is a 400 that says why",
                               status == 400 and expect in message,
                               f"{status}: {message[:60]}"))
        finally:
            httpd.shutdown()
            service.close()
    return checks


def _page_checks() -> list[Check]:
    """The page ships the three tabs and their panels.

    The page is one static string with no build step, so a missing element is
    a silent dead control rather than a failure anything else would catch.
    """
    from meanap.viewer.page import PAGE_HTML

    ids = [
        "tab-recordings", "tab-comparisons", "tab-lags",
        "side-recordings", "side-comparisons", "side-lags",
        "cmp-family", "cmp-metrics", "cmp-lag", "cmp-level", "cmp-split",
        "lag-series", "lag-options", "facets-panel", "controls-panel",
        "cmp-controls", "cmp-reset", "facets-head",
        "single", "pair", "gallery", "families",
    ]
    checks: list[Check] = [
        (f"the page has #{name}", f'id="{name}"' in PAGE_HTML, "")
        for name in ids
    ]
    checks.append(("the tab strip drives all three panes",
                   PAGE_HTML.count('data-tab="') == 3,
                   f"{PAGE_HTML.count('data-tab=')}"))
    checks.append(("it asks the endpoints the server actually serves",
                   all(route in PAGE_HTML for route in
                       ("/api/manifest", "/api/figure", "/api/activity",
                        "/api/comparison", "/api/lagseries", "/api/family",
                        "/api/asset")), ""))
    checks.append(("nothing external is fetched",
                   "http://" not in PAGE_HTML and "https://" not in PAGE_HTML, ""))
    return checks


def _trace_checks() -> list[Check]:
    """CAT-NAP peak-detection traces: carried in the bundle, served as stored.

    These are the only record of what peak detection did, and the one figure
    family a bundle cannot rebuild — they need the full fluorescence matrices,
    which are deliberately not stored. ``write_bundle`` packed them all along,
    and the manifest even declared ``embedded_figures: ["2p_traces"]``, but
    nothing listed or served them: a run with the default ``num_2p_traces = 3``
    produced figures the viewer showed no sign of.

    Served rather than rendered, so unlike every other family there is no
    format choice and no styling — which is exactly why the path guard matters
    more here than elsewhere.
    """
    import zipfile
    from meanap.viewer.server import serve

    checks: list[Check] = []
    payload = b"\x89PNG\r\n\x1a\n" + b"trace-bytes" * 8
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        express = _run(tmp, "Traces", express=True)
        bundle = express.with_suffix(BUNDLE_SUFFIX)
        # Append figures where a CAT-NAP run writes them. Appending rather than
        # running the 2P path keeps this test about the viewer.
        with zipfile.ZipFile(bundle, "a", zipfile.ZIP_DEFLATED) as z:
            for unit in (1, 2, 10):
                z.writestr(
                    "2_NeuronalActivity/2A_IndividualNeuronalAnalysis/"
                    f"WT/recA/unit_{unit}_2ptraces.png", payload)

        httpd, _service = serve(bundle, port=0, background=True)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            status, body, _ = _get(base + "/api/manifest")
            man = json.loads(body)
            by = {r["name"]: r for r in man["recordings"]}
            labels = [t["label"] for t in by["recA"].get("traces", [])]
            checks.append(("the manifest lists the packed traces",
                           labels == ["Unit 1", "Unit 2", "Unit 10"], f"{labels}"))
            checks.append(("…in unit order, not lexical (9 before 10)",
                           labels[-1] == "Unit 10", f"{labels}"))
            checks.append(("a recording with no traces lists none",
                           by["recB"].get("traces") == [], f"{by['recB'].get('traces')}"))

            name = by["recA"]["traces"][1]["name"]
            status, img, headers = _get(f"{base}/api/trace?rec=recA&name={name}")
            checks.append(("a trace is served", status == 200, str(status)))
            checks.append(("…byte-for-byte as it was packed", img == payload,
                           f"{len(img)} vs {len(payload)}"))
            checks.append(("…as an image",
                           headers.get("Content-Type", "").startswith("image/"),
                           headers.get("Content-Type", "")))

            # The name comes from a URL and is matched against the discovered
            # set, never joined onto a path.
            for bad in ("../../params", "../../../../etc/passwd", "nope"):
                status, _b, _h = _get(f"{base}/api/trace?rec=recA&name={bad}")
                checks.append((f"refuses {bad!r}", status == 404, str(status)))

            status, body, _ = _get(base + "/")
            checks.append(("the page has a section for them",
                           b"Peak detection traces" in body, ""))
        finally:
            httpd.shutdown()
    return checks


def main() -> int:
    print("=" * 70)
    print("MEA-NAP web viewer")
    print("=" * 70)
    total_pass = total = 0
    for title, build in [
        ("Serving a bundle over HTTP:", _all_checks),
        ("Comparison figures by facet:", _comparison_checks),
        ("Across-lag figures:", _lag_series_checks),
        ("Age and group colours:", _color_checks),
        ("The page's three tabs:", _page_checks),
        ("CAT-NAP peak-detection traces:", _trace_checks),
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
