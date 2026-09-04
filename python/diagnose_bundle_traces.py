"""Why a bundle shows no peak-detection traces.

    uv run python python/diagnose_bundle_traces.py <run>.meanap

Reads the bundle's own manifest and params, so it answers the question without
the output folder, the raw data or the run's log.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from meanap.pipeline.bundle import open_bundle  # noqa: E402
from meanap.pipeline.render import (  # noqa: E402
    TRACE_DIR, available_trace_figures, load_context,
)

NEEDS_DENOISING = ("peaks", "denoised F", "spks")


def _measures(params) -> list[str]:
    """Every measure of activity the run analysed, primary first."""
    from meanap.catnap.activities import activity_types

    return activity_types(params)


def _denoising_measures(params) -> list[str]:
    """The measures that make the run denoise — any one is enough for traces."""
    return [a for a in _measures(params) if a in NEEDS_DENOISING]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    path = Path(argv[1])
    with open_bundle(path) as bundle:
        ctx = load_context(bundle)
        params = bundle.params

        print(f"{path.name}")
        print(f"  mode              {bundle.manifest.get('mode')}")
        print(f"  express           {bundle.manifest.get('express')}")
        print(f"  embedded figures  {bundle.manifest.get('embedded_figures') or 'none'}")

        if params is not None:
            print(f"  num_2p_traces     {params.num_2p_traces}")
            print(f"  twop_activity     {params.twop_activity!r}")
            print(f"  twop_redo_denoising {params.twop_redo_denoising}")
        else:
            print("  (no params.json in this bundle)")

        packed = sorted((bundle.root / TRACE_DIR).rglob("*.png"))
        print(f"\n  {len(packed)} trace PNG(s) packed under {TRACE_DIR}")
        for p in packed[:6]:
            print(f"    {p.relative_to(bundle.root)}")
        if len(packed) > 6:
            print(f"    …and {len(packed) - 6} more")

        print("\n  What the viewer would list, per recording:")
        for name in ctx.recordings:
            figs = available_trace_figures(ctx, name)
            print(f"    {name}: {len(figs)}"
                  + (f"  ({', '.join(f.label for f in figs[:4])})" if figs else ""))

        # The diagnosis.
        print()
        if packed:
            listed = any(available_trace_figures(ctx, n) for n in ctx.recordings)
            if listed:
                print("  → The figures are here and the viewer can find them. If the "
                      "page shows none, it is a viewer/browser problem, not the run.")
            else:
                print("  → The figures are packed but the viewer cannot match them to "
                      "a recording — the folder names under\n"
                      f"    {TRACE_DIR}/<group>/<recording>/ do not match the "
                      "spreadsheet's recording names.")
        elif params is not None and not params.num_2p_traces:
            print("  → The run had 'Trace figures to save per recording' set to 0, so "
                  "they were never drawn.\n    They cannot be recovered from the "
                  "bundle; set it above 0 (CAT-NAP tab → Denoising settings → "
                  "Advanced) and re-run.")
        elif params is not None and not _denoising_measures(params):
            named = " / ".join(repr(a) for a in _measures(params))
            print(f"  → Activity type is {named}, which skips "
                  "denoising — and these figures plot the\n    denoised trace "
                  "against the detected events. Set it to 'peaks' and re-run.")
        else:
            print("  → The run meant to draw them and did not. The run log says why; "
                  "look for lines\n    containing '2P trace' or 'could not re-read "
                  "suite2p data'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
