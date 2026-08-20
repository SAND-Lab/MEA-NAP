"""Downloading a peak-detection trace saves a file, like every other figure.

"Download PNG" worked everywhere except CAT-NAP's peak-detection traces, where
it opened the image in a tab instead. Two independent halves of the same
oversight, and either alone was enough to break it:

* ``/api/trace`` was the one image route handled inline in ``do_GET`` rather
  than by a ``_xxx`` method, and so the only one that never read ``download``.
* ``figureURL``'s trace branch dropped its ``extra`` argument entirely. That
  was right for ``fmt`` — a trace is a stored PNG, not a render — but it took
  ``download`` with it, which is not a rendering option at all.

So both are checked, and so is the invariant that made the first half possible:
every route that serves a single image honours ``download``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from meanap.pipeline.render import TRACE_DIR  # noqa: E402
from meanap.viewer.page import PAGE_HTML  # noqa: E402
from meanap.viewer.server import serve  # noqa: E402

from test_bundle_render import LAG, _run  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}" if detail else name)


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


# ── The page asks for it ──────────────────────────────────────────────────────

print("\nThe page's request")

trace_branch = re.search(
    r'if \(VIEW\.kind === "trace"\) \{(.*?)\n  \}', PAGE_HTML, re.S)
check("figureURL still has a branch for traces", trace_branch is not None, "")
if trace_branch:
    # Comments stripped: this branch explains itself at length, and the prose
    # names the very identifiers being looked for.
    body = re.sub(r"//.*", "", trace_branch.group(1))
    check("…which forwards `download` to the server",
          "extra.download" in body, body.strip()[:120])
    # Still deliberately absent: a trace is a stored PNG, so offering svg/pdf
    # would promise a conversion that never happens.
    check("…and still does not pretend a format can be chosen",
          "fmt" not in body, body.strip()[:120])

check("the trace view hides the vector download buttons",
      'if (kind === "trace")' in PAGE_HTML, "")


# ── The server honours it ─────────────────────────────────────────────────────

print("\nThe server's response")

tmp = Path(tempfile.mkdtemp())
# A folder rather than a bundle: the synthetic fixture ships no traces, so one
# is planted where available_trace_figures looks, and a bundle's extracted root
# does not outlive the handle it came from.
root = _run(tmp, "Trace", express=False)
trace_dir = root / TRACE_DIR / "WT" / "recA"
trace_dir.mkdir(parents=True, exist_ok=True)
fig = plt.figure()
plt.plot([0, 1], [0, 1])
fig.savefig(trace_dir / "recA_unit1.png")
plt.close(fig)

httpd, service = serve(root, port=0, background=True)
base = f"http://127.0.0.1:{httpd.server_address[1]}"
try:
    man = json.loads(urllib.request.urlopen(base + "/api/manifest", timeout=60).read())
    rec = next(r for r in man["recordings"] if r["name"] == "recA")
    names = [t["name"] for t in rec.get("traces", [])]
    check("the manifest advertises the trace", names == ["recA_unit1"], str(names))

    status, headers = _get(f"{base}/api/trace?rec=recA&name=recA_unit1")
    check("a plain request still just shows the image",
          status == 200 and "Content-Disposition" not in headers,
          headers.get("Content-Disposition", ""))
    check("…as a png", headers.get("Content-Type") == "image/png",
          headers.get("Content-Type", ""))

    status, headers = _get(f"{base}/api/trace?rec=recA&name=recA_unit1&download=1")
    disposition = headers.get("Content-Disposition", "")
    check("download=1 makes it a file save", "attachment" in disposition, disposition)
    check("…named after the trace, not something generic",
          'filename="recA_unit1.png"' in disposition, disposition)

    # The invariant behind the bug: traces were the odd one out because they
    # alone had no handler. Every single-image route should behave alike.
    routes = {
        "trace": "/api/trace?rec=recA&name=recA_unit1",
        "figure": f"/api/figure?rec=recA&lag={LAG}&name=2_MEA_NetworkPlot",
    }
    for kind, route in routes.items():
        _, h = _get(f"{base}{route}&download=1")
        check(f"every single-image route saves a file — {kind}",
              "attachment" in h.get("Content-Disposition", ""),
              h.get("Content-Disposition", ""))
finally:
    httpd.shutdown()


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("All trace-download checks passed.")
