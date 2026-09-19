# CAT-NAP cross-day cell tracking — design

Status: design, not yet implemented. Prototype lives in `local/celltracking/`
(phases 1–20); full evidence in `local/celltracking/diagnostics/FINDINGS.md`.

The prototype tracked 93 chains of Yin's Mecp2 dataset and took the usable-chain
count from 32 to 56. This is what a supported CAT-NAP feature should look like,
with the traps that cost this session's time written into the design.

---

## 1. What the prototype established

### Registration is the whole problem

ROICaT aligns on `meanImgE`. These recordings carry a **fixed-pattern stripe
artifact bound to the detector**, so when the sample slides the stripes do not,
and the aligner sees no motion. Its *geometric* step returned exactly 0.000 px
on 20/20 chains sampled. Matching then happens on unregistered coordinates and
collapses above a ~16 px offset (median match 0.196 → 0.007).

**Trap 1 — the non-rigid step is not idle.** `fit_nonrigid` (Farneback on the
mixed image) *does* apply real corrections, ~19 px on some chains, and on
well-aligned chains it was silently doing the entire job. Concluding "ROICaT
does no registration" from a sample with small non-rigid terms cost this session
a full 94-chain run: pre-registering the ROIs while leaving the mean images
unshifted let the non-rigid step re-apply the offset we had just removed, and
the best chain in the dataset fell from **0.740 to 0.015**.

**Trap 2 — you cannot let both registrations run.** Leave the image unshifted
and the non-rigid step undoes the pre-registration; shift the image and the
stripes move with it, so the geometric step tries to undo it instead. The fix is
to register once, in our code, and set **`NullRegistration` for both
`fit_geometric` and `fit_nonrigid`**.

**Trap 3 — do not correct an offset you cannot measure.** Pre-registering a
chain whose sessions are already aligned injects error: "correcting" an 8 px
offset (one density bin) made 47 day-pairs worse. Gate on
`measured offset >= 16 px`.

### Only translation matters

Rotation/scale grid search: median NCC gain **0.0000**; pure translation was the
best fit in 378/503 pairs; of 193 pairs called "different FOV", allowing
rotation and scale rescued **1**. Non-rigid residual after the global shift:
median **0.0 px** per 3×3 block, above one bin in 17/302 pairs. The fields slide.
Do not build affine or warping machinery.

### Controls the prototype had to invent

- **ROI-only shift** — move the ROIs by a known offset, leave the image alone.
  This is what real stage drift looks like. The pre-existing `translate` control
  moved the image *with* the ROIs, so its stripes moved too; it both flattered
  ROICaT and double-corrected under pre-registration. Baseline recovers
  **0.023** on the honest control; pre-registration **1.000**.
- **Foreign-FOV floor, n >= 15** — two pairs is not enough to set a threshold on.
  Floor: median 0.023, p95 0.069, **max 0.091**. So **0.05 is below the floor**;
  use **>= 0.10**, 0.15 to be safe.
- **Retire the 0.849 "ceiling".** It was measured on a 53-ROI session; a 142-ROI
  session reaches 1.000. It does not generalise across sessions or pipelines, so
  `frac_tracked_vs_ceiling` is meaningless — drop it or re-measure per session.

### Activity validation, and what it is good for

Matching is spatial, so spatial controls cannot distinguish "the same cell" from
"a different cell in the same place". Validate with signals the matcher never
saw (after UnitMatch — van Beest, Bimbard et al.).

The null that matters is each partner's **nearest spatial neighbour**, not a
random cell. Against a random null everything looks good; against the spatial
null:

| metric | AUC vs nearest |
|---|---|
| event rate | 0.531 |
| inter-event interval | 0.538 |
| decay time | 0.565 |
| population coupling | 0.569 |
| **functional fingerprint** | **0.68** |

- **Use the fingerprint as a quality descriptor, not a filter.** At 10% FPR only
  22–31% of matches survive and usable chains fall 67 → ~13, while the
  false-match bound only improves to ~33–45%. AUC 0.68 is too weak for per-match
  accept/reject.
- **The match rate is not a per-match quality score** — fingerprint AUC is flat
  across match-rate bins.
- **Neuropil**: subtract `F - 0.7*Fneu` because it is correct and yields more
  usable data (8696 pairs/75 chains vs 6787/69), **not** because it changes any
  conclusion (AUC 0.681 vs 0.678). Neighbouring cells are correlated because
  they share real local network activity, not neuropil bleed.

---

## 2. Proposed design

```
src/meanap/catnap/tracking/
    __init__.py
    chains.py       group recordings into fields of view
    footprint.py    ROI density maps; displacement + aligned-NCC estimator
    register.py     robust per-session offsets; staging with canvas padding
    roicat.py       ROICaT invocation with the settled parameters
    validate.py     activity metrics, fingerprint, nearest-neighbour null
    controls.py     ROI-only-shift and foreign-FOV controls
    report.py       per-chain QC page and CSV outputs
```

### Params (`meanap.params.Params`)

```python
track_cells: bool = False           # off by default; opt in per run
track_min_shift_px: float = 16.0    # below this, leave the chain alone
track_reliable_ncc: float = 0.45    # pairs below this do not constrain the solve
track_tracked_threshold: float = 0.10   # set from the measured foreign-FOV floor
track_completion_radius_px: float = 10.0  # attach the one unmatched cell this close; 0 = off
track_density_bin_px: int = 8
track_neuropil_coeff: float = 0.7   # suite2p convention
track_validate_activity: bool = True
track_controls: bool = False        # re-measure the floor for a new rig/dataset
```

`track_tracked_threshold` must be **derived from the controls for the dataset at
hand**, not inherited. The 0.10 above belongs to this rig.

### Steps

1. **Chain discovery** (`chains.py`). A field of view is the recording name with
   *both* the imaging date and the DIV stripped — the date changes with the DIV,
   so removing only the DIV does not group them. A chain name is not a guarantee
   the FOV is shared; step 3 decides that per day-pair.

2. **Footprints** (`footprint.py`). Load `stat.npy`, **filter to `iscell` first**
   — the ~85% rejected ROIs otherwise dominate the similarity graph and yield
   drops from 45% to 6%. Rasterise lam-weighted footprints into 8 px bins,
   smooth σ=1.5 bins. Never use the mean image: unrelated cultures correlate at
   0.87 on it and phase correlation pins every pair at (0,0).

3. **Offsets** (`register.py`). Cross-correlate density maps for every day-pair →
   `(dy, dx)` and `aligned_ncc`. Then a **weighted least-squares solve over all
   pairs**, not a chain of consecutive ones:
   - drop pairs with `aligned_ncc < track_reliable_ncc` — their displacement is
     noise, and letting them constrain the solve moved one chain from 12 px to
     89 px;
   - weight surviving pairs by `ncc - threshold`;
   - solve each **connected component** separately, so a session on a genuinely
     different field is left where it is rather than averaged into a
     meaningless common frame;
   - **anchor each component on its medoid session**, not its mean. Mean-pinning
     spreads one session's 18 px drift into 13.5 / −4.5 / −4.5 / −4.5 — three
     sub-bin corrections nobody asked for — and hides the drift from the gate.
     A common translation is invisible to the matcher.

4. **Gate and stage.** If **no session would be moved by**
   `track_min_shift_px` **or more** (the largest solved per-session offset),
   **skip pre-registration entirely** and pass the original data through.
   Not the median over pairs — that hid a single drifted session (three of six
   pairs measure the drift, three measure 0; OPME240112_5's DIV21 sat 18–25 px
   off, was passed through at a median of 8.9 px, and matched nothing), and
   "registered" chains with no reliable pair at all with all-zero offsets
   while switching ROICaT's own alignment off. Not the largest pair either —
   a single 16 px pair in an aligned chain is bin-quantisation wobble, and
   registering on it nudges every session by ~8 px. Else
   shift ROI pixel coordinates and **pad the canvas** so nothing is clipped
   (padding is harmless — verified at 0.742 vs 0.740). Leave the mean images at a
   shared origin.

5. **ROICaT** (`roicat.py`), with:
   ```python
   params["alignment"]["fit_geometric"]["method"] = "NullRegistration"
   params["alignment"]["fit_nonrigid"]["method"]  = "NullRegistration"
   params["general"]["random_seed"] = 0     # the pipeline is deterministic
   ```
   Only `meanImgE` is read from `ops.npy`, so a minimal ops built from the
   sidecar is enough — the real 462 MB `ops.npy` is never needed, which is what
   makes a full-dataset run affordable. Note ROICaT's learned appearance
   features are near-useless here (suite2p ROIs are ~4 px across), so matching is
   driven by spatial footprint — which is exactly why independent validation
   matters.

   **Keep only `results_clusters.json`.** `run_data.richfile.zip` is ~400 MB per
   chain (109 GB across this session's runs) and nothing downstream reads it.

   A re-run can hand `track_dataset(reuse_runs=<old>/work/runs)` and any chain
   whose gate decision *and* staged geometry are unchanged reads its clusters
   back (seconds) instead of recomputing them (~10 min). The check is against
   ROICaT's own `params_used.json` and the earlier chain result's offsets.

5b. **Completion** (`complete.py`). ROICaT clusters on footprint similarity and
   is conservative about it. Audited over the 93-chain run: for every tracked
   cell and every day it was missing from, what sat at its expected position?

   | at the expected position (≤ 10 px) | slots | share |
   |---|---|---|
   | an iscell ROI ROICaT left unmatched | 2,089 | 24% |
   | an iscell ROI in another cluster | 682 | 8% |
   | a non-iscell ROI | 274 | 3% |
   | nothing — suite2p extracted no ROI | 5,857 | 66% |

   The first row is recovered by position: a tracked cluster missing on a day,
   with **exactly one** unmatched iscell ROI within `track_completion_radius_px`
   of its expected position, claimed by **exactly one** cluster, gets it. The
   rule is strict because ambiguity is rare (66 of 2,116 slots had two
   candidates; 32 ROIs were claimed twice), so strictness costs almost nothing
   and never guesses. Whether those cells are really the same cell was asked of
   the activity fingerprint, with exactly the test the accepted matches got:

   | | n | matched | nearest null | AUC |
   |---|---|---|---|---|
   | ROICaT's accepted matches, same day-pairs | 8,603 | +0.539 | +0.274 | 0.684 |
   | declined ROIs ≤ 10 px from the cell | 1,747 | +0.543 | +0.267 | 0.675 |

   Candidates against the accepted pool: AUC 0.499 — the same population.
   It holds within bins (≤ 4 px: 0.701; 7–10 px: 0.657; Jaccard < 0.2: 0.613).
   Added members are flagged everywhere (`rescued` in the result JSON,
   `n_rescued` / `shared_roicat` in the CSVs, a marked day in the viewer) and
   validated separately (`rescued_fingerprint_auc`), so an analysis can leave
   them out.

   The second row is the other repair: **split chains**, one cell ROICaT
   tracked as two clusters on disjoint days (DIV21–29 as one, DIV36–44 as
   another) because the mask changed across the gap. Two tracked clusters with
   **disjoint** day sets (a shared day means two cells side by side) whose mean
   positions lie within the radius, each the other's **only** such partner,
   are folded into one (`merge_split_clusters`, run before completion). The
   fingerprint across the join — one half's last day against the other's
   first, versus the nearest neighbour — scored AUC **0.695** on 163 candidate
   pairs (median +0.626 vs null +0.350), again as strong as ROICaT's own
   matches. Merging lengthens chains rather than adding matches; the absorbed
   half's days are flagged (`merged` in the result, `n_merged` in the CSV,
   marked in the viewer) and validated separately (`merged_fingerprint_auc`).

   What completion does **not** do, and why: the 66% "nothing there" slots are
   suite2p's detection — a cell with no transients that day is invisible to a
   detector built on temporal fluctuation (a bright, saturated soma with no ROI
   is the typical case) — and no matching step fixes that; it needs seeded
   re-extraction from the movie. Feeding non-iscell ROIs to ROICaT has a 3%
   ceiling (most at iscell prob ~0.1) and a documented cost (yield 45% → 6%).

6. **Validation** (`validate.py`). Stream `F`/`Fneu`, compute
   `F - track_neuropil_coeff * Fneu`, reduce each recording to its cell-by-cell
   correlation matrix and population coupling, discard the arrays. 345
   recordings reduce to **26 MB** this way rather than 8.7 GB. Then per matched
   pair compute the fingerprint and its **nearest-neighbour null**, and report
   AUC per chain and per day-pair as a quality descriptor.

7. **Report** (`report.py`). Per chain: measured offsets, whether
   pre-registration was applied, per-day-pair match rate, fingerprint AUC, and
   the centroid-overlay figure. Plus a dataset-level QC page carrying the
   control-derived floor and ceiling.

### Outputs

```
<output>/CellTracking/
    tracking_by_chain.csv     chain, genotype, prep, div, n_roi, frac_tracked
    tracking_by_pair.csv      + measured shift, aligned_ncc, fingerprint AUC
    manifest.json             per chain: offsets, gate decision, source run
    controls.json             ROI-shift recovery and foreign-FOV floor
    figures/<chain>.png
```

---

## 3. Reporting rules

- Quote the match rate **with the control-derived floor next to it**. A rate
  below the floor is not a weak result, it is no result.
- Report **usable chains**, not mean match rate — it is what gates any
  longitudinal analysis.
- Carry the fingerprint AUC alongside every match rate. They are independent and
  they disagree: high-match-rate chains are not reliably better-matched.

## 4. Known confound in this dataset

Recovery covaries with prep, and prep covaries with genotype: usable chains are
**WT 67%, Het 72%, KO 45%**, because KO concentrates in the older preps
(OPME230505, OPME230519) whose sessions are on genuinely different fields —
which pre-registration correctly refuses to move. Any WT-vs-KO comparison built
on tracked cells inherits this, on top of the existing batch confound.
**Within-prep comparisons only.**

## 5. Open items

- Event-based metrics still come from events detected on uncorrected
  `Fdenoised`; re-detecting on neuropil-corrected traces is untested.
- `track_min_shift_px = 16` was chosen while looking at the outcomes it improves.
  It is independently justified (two bins = measurement resolution, and the
  empirical cliff), but a clean confirmation needs held-out chains.
- The padded canvas makes ROICaT log alignment z-scores of ~1e10 against a
  normal ~2000. Harmless in every test run, cause not understood.
