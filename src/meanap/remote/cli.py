"""``meanap-preflight`` — check a dataset before committing to a run.

Answers, in seconds and without downloading anything: are the recordings my
spreadsheet names actually there, how much will this transfer, and will it fit?
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import tempfile
from pathlib import Path

__all__ = ["main"]

#: Column headers a batch spreadsheet uses for the recording name, in the
#: variants MEA-NAP has accepted over time.
_NAME_HINTS = ("recording filename", "recording file name", "filename", "file name")


def _recording_names(text: str) -> list[str]:
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return []
    header = next(
        (c for c in rows[0] if c and c.strip().lower() in _NAME_HINTS),
        next((c for c in rows[0] if c and "name" in c.lower()), None),
    )
    if header is None:
        raise SystemExit(
            "Could not find a recording-name column in the spreadsheet "
            f"(saw: {', '.join(c for c in rows[0] if c)}).")
    return [r[header].strip() for r in rows if (r.get(header) or "").strip()]


def _write_fixed_spreadsheet(text: str, name_map: dict, out: Path) -> int:
    """Copy a batch spreadsheet, renaming recordings to the folders on disk.

    Rewriting the *spreadsheet* rather than the data is usually the safer half
    of the fix: a share link is read-only, and folder names may be referenced
    by other people's notes. Everything else in the file is preserved verbatim.
    """
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise SystemExit("Cannot rewrite an empty spreadsheet.")
    header = next(
        (c for c in rows[0] if c and c.strip().lower() in _NAME_HINTS),
        next((c for c in rows[0] if c and "name" in c.lower()), None),
    )
    changed = 0
    for row in rows:
        current = (row.get(header) or "").strip()
        if current in name_map:
            row[header] = name_map[current]
            changed += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="meanap-preflight",
        description="Check a local folder or Dropbox share link before a run.")
    ap.add_argument("source", help="a folder, or a Dropbox folder share link")
    ap.add_argument("--spreadsheet", default="",
                    help="batch CSV (default: the only .csv in the source)")
    ap.add_argument("--mode", choices=("catnap", "ephys"), default="catnap")
    ap.add_argument("--cache-dir", default="")
    ap.add_argument("--budget-gb", type=float, default=None)
    ap.add_argument("--prefetch-depth", type=int, default=1)
    ap.add_argument("--write-spreadsheet", metavar="OUT.csv", default="",
                    help="write a copy of the batch file with recording names "
                         "corrected to the folder names actually present")
    args = ap.parse_args(argv)

    from meanap.remote.cache import FileCache
    from meanap.remote.dropbox_link import DropboxLinkStore
    from meanap.remote.local import LocalStore
    from meanap.remote.preflight import find_spreadsheet, run_preflight

    store = (DropboxLinkStore(args.source) if "://" in args.source
             else LocalStore(args.source))

    sheet = find_spreadsheet(store, args.spreadsheet)
    if sheet is None:
        raise SystemExit(
            "No batch spreadsheet found. Pass --spreadsheet with its name, or "
            "put exactly one .csv at the top level of the source.")

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(args.cache_dir or tmp) / "meanap-cache"
        cache = FileCache(root=cache_dir, budget_bytes=10 * 1000**3)
        local = cache.get(store, sheet) if store.stat(sheet) else Path(sheet)
        # Read it here: the cache lives in the temporary directory, so the file
        # is gone by the time the rewrite below runs.
        sheet_text = local.read_text(errors="replace")
        names = _recording_names(sheet_text)
        if not names:
            raise SystemExit(f"{sheet} lists no recordings.")

        report = run_preflight(
            store, names, mode=args.mode, spreadsheet=sheet,
            cache_dir=cache_dir if store.copies else None,
            cache_budget_gb=args.budget_gb, prefetch_depth=args.prefetch_depth,
        )

    if args.write_spreadsheet:
        written = _write_fixed_spreadsheet(
            sheet_text, report.name_map,
            Path(args.write_spreadsheet))
        print(f"Wrote {written} corrected name(s) to {args.write_spreadsheet}\n")

    print(report.render())
    if not report.ok:
        print("\nThis dataset is not ready to run.", file=sys.stderr)
        return 1
    print("\nReady to run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
