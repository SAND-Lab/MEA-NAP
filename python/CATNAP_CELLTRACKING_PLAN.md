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
   - solve each **connected component** separately, pinning its mean at zero, so
     a session on a genuinely different field is left where it is rather than
     averaged into a meaningless common frame.

4. **Gate and stage.** If a chain's median measured offset `< track_min_shift_px`,
   **skip pre-registration entirely** and pass the original data through. Else
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
