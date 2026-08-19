# Running on remote data

A batch that doesn't fit on your disk can still be analysed. Put a **Dropbox
folder share link** in the **Raw data folder** field instead of a path, and
recordings are fetched one at a time, analysed, and discarded — so the storage
a run needs is one or two recordings, not the whole dataset.

```python
from meanap.params import Params

params = Params(
    raw_data="https://www.dropbox.com/scl/fo/…?rlkey=…",   # instead of a path
    output_data_folder="/data/analysis",
    spreadsheet_file_name="/data/batch.csv",
    suite2p_mode=True,        # or leave unset for electrophysiology
)
```

Both analysis paths work this way. CAT-NAP fetches a `suite2p/plane0` folder per
recording; electrophysiology fetches one `.mat`/`.h5`/`.raw` file. Each is
released once its results are written — spike times for electrophysiology,
adjacency and activity stats for CAT-NAP — so the later steps never need the raw
data again.

```{note}
One Axion `.raw` holds a whole plate, and MEA-NAP treats each well as its own
recording. The plate is fetched once and kept until the *last* of its wells has
been analysed, rather than re-downloaded per well.
```

Nothing else needs setting. The fetch cache and the derived-data folder both
default under `output_data_folder`:

```
/data/analysis/
├── MEANAP-cache/      recordings being fetched — transient, bounded, self-clearing
├── MEANAP-derived/    denoising outputs and cached ops fields — kept, reused
└── OutputData07Aug2026/
```

Both sit beside the dated run folders rather than inside one, so a second run
reuses the denoising instead of redoing it.

## What it costs

Measured on a real 13-recording Dropbox folder:

| | |
|---|---|
| Source data | 6.4 GB (1.96 GB for the 4 recordings run) |
| Peak local storage | **0.72 GB** |
| Output (express mode) | 2.6 MB |
| Throughput | 6–9 MB/s |

The peak does not grow with the batch: 4 recordings and 40 recordings both hold
one or two at a time.

Roughly a fifth of each suite2p folder is never fetched at all — the `.csv`
exports, `Fneu.npy` and `stat.xlsx` that the pipeline never opens. Sizes come
from the folder listing, so that decision costs no transfer.

## Check before you run

```bash
uv run meanap-preflight 'https://www.dropbox.com/scl/fo/…?rlkey=…'
```

Listing a remote folder returns names *and sizes* without transferring
anything, so a full check takes seconds:

```
  ✓ 13 of 381 recordings ready
  ✗ …and 360 more not found
  ! CAP-NAP-master — present but not in the spreadsheet
  · 1 of 13 need denoising, which will run locally

  Download        6.38 GB   (0.11 GB skipped — files the pipeline never opens)
  Est. transfer     18 min at 6 MB/s
  Peak storage    1.11 GB   (budget 50.00 GB, 227 GB free)  OK
```

A remote run does this automatically and **refuses to start** if the source
isn't usable. That is deliberate: the batch-wide statistics — group
comparisons, and the node-cartography boundaries — are computed from whichever
recordings actually ran, so a batch that quietly analyses a fraction of what
you asked for still produces results, and they look complete.

### When folder names don't match the spreadsheet

The commonest reason a batch shrinks is a folder that has been renamed — a
suffix added, usually. Pre-flight matches these up and names them:

```
  Problem: 12 recording(s) exist in the source under a slightly different
  folder name (e.g. 'OPME240607_5_…DIV36' vs 'OPME240607_5_…DIV36 David
  Oluigbo'). Rename the folders, or edit the spreadsheet to match.
```

To fix it without touching either the folders (often read-only, or shared) or
your original spreadsheet:

```bash
uv run meanap-preflight '<link>' --write-spreadsheet batch-fixed.csv
```

That writes a copy with the recording names corrected and everything else
preserved. Point `spreadsheet_file_name` at it.

### When a suite2p folder contradicts itself

```
  ✗ OPME240520_17_…_DIV13 — iscell.npy describes 5040 ROIs, which does not
    divide F.npy — the suite2p output is inconsistent and will not load
    (re-save the recording in the suite2p GUI)
```

`iscell.npy` says which ROIs are cells *by row position*, so it has to have one
row per trace in `F.npy`. When it doesn't, nothing downstream can tell which
classification belongs to which neuron, and MEA-NAP skips the recording rather
than guess.

The usual cause is ROIs drawn by hand in the suite2p GUI. suite2p prepends them
and stamps them with a classifier probability of exactly 1.0, then saves
`stat.npy`, `F.npy`, `Fneu.npy`, `spks.npy` and `iscell.npy` together — so a
folder where only `iscell.npy` grew is one where that save did not finish. The
loader spells this out when it sees the signature, including how many rows the
two files are out of step by. Re-open the recording in the suite2p GUI and save
it again; the traces for the drawn ROIs only exist there.

Pre-flight catches the arithmetically impossible cases from file sizes alone,
before anything is downloaded. A mismatch that happens to divide slips past it
and is caught at load time instead — after the download, but still before
denoising.

## Storage budget

By default the cache may grow to a quarter of free disk, capped at 50 GB.

```python
params.cache_budget_gb = 5.0     # explicit ceiling
params.prefetch_depth = 1        # recordings fetched ahead (default 1)
```

The budget must hold `prefetch_depth + 1` recordings at once. Pre-flight checks
that up front and says what to change if it can't:

```
This run needs 3.00 GB resident at once (the largest recording, plus anything
fetched ahead of it), but the cache budget is 1.00 GB. Raise
Params.cache_budget_gb, reduce Params.prefetch_depth, or free disk space.
```

`prefetch_depth = 1` fetches the next recording while the current one is
analysed, which hides the download almost entirely — on CAT-NAP data, about
95 s of transfer against 275 s of compute per recording. Deeper prefetching
costs another recording's worth of disk for little gain once compute dominates.

## Your share link is not sent with your results

`params.json` is packed into every `.meanap` bundle, and a public share link is
an unauthenticated grant of access to the whole dataset. So a URL in
`raw_data`, `prior_analysis_path` or `spreadsheet_file_name` is replaced with
`<remote source redacted>` in the bundled copy. The copy in your own output
folder keeps it, for reproducibility.

A local path in the same field is left alone — it reveals a directory layout,
not a way in.

```{warning}
A public Dropbox link needs no password. Anyone who has the URL can download
the entire folder. Treat it as a credential.
```

## Limitations

- **Dropbox folder share links only.** Not file links (`/scl/fi/…`), and not
  other providers. A synced Dropbox folder or an `rclone mount` works too — and
  is the more robust option, since it uses supported interfaces.
- **The Dropbox reader uses undocumented endpoints.** It is what dropbox.com's
  own front end uses, and Dropbox can change it without notice. When that
  happens the failure is explicit and names the alternatives, rather than
  producing an empty folder listing.
- **Bandwidth, not disk, becomes the limit.** At 6 MB/s a 14 GB dataset takes
  around 40 minutes to stream once. Derived outputs are cached, so a second run
  over the same data re-fetches nothing.
- **Very large folders** are listed in full: Dropbox returns them a page at a
  time, and the reader follows the pages to the end. If it ever cannot, it
  refuses rather than returning a listing that is silently short — a truncated
  listing is indistinguishable from a small dataset.

See {doc}`express-mode` for keeping the *outputs* small too — the two compose:
stream the inputs, ship a 2 MB bundle.
