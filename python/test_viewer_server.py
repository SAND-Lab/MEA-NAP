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


def main() -> int:
    print("=" * 70)
    print("MEA-NAP web viewer")
    print("=" * 70)
    total_pass, total = _report("Serving a bundle over HTTP:", _all_checks())
    print(f"\n{'=' * 70}")
    print(f"Total: {total_pass}/{total} checks passed")
    print("=" * 70)
    return 0 if total_pass == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
