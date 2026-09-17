"""Run one chain, as a subprocess.

``track_dataset`` fans chains out across processes rather than threads, for two
reasons that are both ROICaT's:

* it re-extracts its 55 MB ROInet model into ``tempfile.gettempdir()`` on every
  run, so concurrent runs sharing a TMPDIR overwrite the ``.pth`` while their
  neighbours are reading it (``PytorchStreamReader failed reading zip archive``).
  A private TMPDIR per chain isolates the extraction; symlinking the
  already-downloaded zip in means no worker re-downloads it.
* torch sizes its thread pools to the whole machine unless told otherwise, so
  several workers apiece oversubscribe the box badly.

Both are set up by the parent before this module is reached.

    python -m meanap.catnap.tracking --chain <key> --spec <json>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(prog="meanap.catnap.tracking")
    ap.add_argument("--spec", required=True,
                    help="JSON file describing the chain and where to write it")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text())
    from meanap.catnap.tracking.chains import build_chains
    from meanap.catnap.tracking.pipeline import track_chain
    from meanap.catnap.tracking.source import LocalSessionSource

    chains = build_chains(spec["recordings"])
    chain = chains[spec["chain"]]
    source = LocalSessionSource(raw_data=Path(spec["raw_data"]),
                                derived_root=spec.get("derived_root") or None)
    result = track_chain(
        chain, source, Path(spec["work_dir"]),
        min_shift_px=spec.get("min_shift_px", 16.0),
        validate=spec.get("validate", True),
        viewer_dir=Path(spec["viewer_dir"]) if spec.get("viewer_dir") else None,
        viewer_cells=spec.get("viewer_cells", 40),
        neucoeff=spec.get("neucoeff", 0.7),
    )
    Path(spec["dest"]).write_text(json.dumps(asdict(result), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
