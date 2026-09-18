# CAT-NAP cell tracking — handoff

Written 2026-09-17 at the end of the session that built the pipeline, and
updated the same day after the session that refined the matches (gate fix,
completion, split-chain merging). Read this with
`CATNAP_CELLTRACKING_PLAN.md` (the design) and
`local/celltracking/diagnostics/FINDINGS.md` (the evidence, with numbers).
This document is the state of play and the traps.

## 1. Status

PR #143 (the pipeline) is **merged** into `origin/main` (`31e7fb0`). The
refinements of 2026-09-17 — `complete.py`, the per-session gate, cluster
reuse, the viewer changes — are PR #144 (`catnap/tracking-completion`).

| thing | where | size |
|---|---|---|
| package | `src/meanap/catnap/tracking/` (14 modules) | ~3900 lines |
| tests | `python/test_catnap_tracking.py` | 104 pass, 1 skip, ~2 s |
| the 93-chain run, **current** | `local/celltracking/full_tracking_final_allcells/` | |
| the 93-chain run, before refinement | `local/celltracking/full_tracking/` | 5.9 GB |
| intermediate runs (v2 = ROICaT re-runs; v3 = final; v4 = rejected zeroing) | `local/celltracking/full_tracking_v{2,3,4}/` | |
| demo bundle | `local/demo_celltracking.meanap` | 217 MB |
| prototype (gitignored) | `local/celltracking/phase*.py` | 27 GB total |
| ROICaT env | `local/celltracking/.venv-roicat` (roicat 1.7.9) | |

`local/` is gitignored, so none of the runs or bundles travel with a clone —
copy them by hand.

## 2. What the run says

```
93 chains, 46 registered, 0 failed, 500 day-pairs
71 usable (median frac_tracked >= 0.10)        (was 56 before refinement)
    Het 36/39   KO 8/20   WT 27/34
median fingerprint AUC 0.666
1977 cell-days added by position (rescued AUC 0.663), 157 split cells joined (AUC 0.688)
```

The refinement (FINDINGS §"Refining the matches") did three things, each
validated by the fingerprint before being adopted: the gate now looks at the
largest per-session offset rather than a median over pairs (one drifted
session in four was invisible to the median); a tracked cell missing on a day
is completed with the one unmatched iscell ROI at its position (those cells
score AUC 0.675 vs 0.684 for ROICaT's own matches — the same population); and
two clusters on disjoint days at one position are joined (AUC 0.695 across
the join). Every added member is flagged (`rescued`/`merged` in the result,
`n_rescued`/`n_merged`/`shared_roicat` in the CSVs, a marked day in the
viewer) so an analysis can leave them out. **Per-session zeroing of sub-gate
offsets was tried and rejected** (worse on 19 of 25 chains) — do not
re-introduce it.

**The headline result is that registration was the whole problem.** ROICaT was
silently doing no useful alignment; pre-registering the fields by ROI-footprint
density cross-correlation is what recovered the match rate. Fields translate
only — rotation, scale and non-rigid terms were all measured and are
unnecessary (`FINDINGS.md` §"Rotation, scale, non-rigid").

**How much to trust a match.** Activity validation never enters the matching, so
it is independent corroboration. On the final set (8801 matched pairs, 80
chains):

| metric | AUC vs nearest neighbour |
|---|---|
| event rate | 0.531 |
| median inter-event interval | 0.538 |
| decay time | 0.565 |
| population coupling | 0.569 |
| **functional fingerprint** | **0.677** |

AUC 0.677 means a matched pair beats a co-located neighbour about two times in
three. Per-cell identity is **weak**. Report it that way. The nearest-spatial-
neighbour null is the honest one; the random null (0.727) flatters the result.

**The caveat that governs any group comparison.** Recovery covaries with prep,
and prep covaries with genotype (KO concentrates in the old OPME230505/230519
preps, which are on genuinely different fields). That sits on top of the batch
confound already recorded in the Yin memory. **Within-prep comparisons only.**

## 3. Constants, and why they are what they are

| constant | value | file |
|---|---|---|
| `RELIABLE_NCC` | 0.45 | `register.py:39` |
| `MIN_SHIFT_PX` | 16.0 | `register.py:43` |
| `DENSITY_BIN_PX` | 8 | `footprint.py:40` |
| `NEUCOEFF` | 0.7 | `validate.py:49` |
| `MASK_PREVIEW_PX` | 768 | `viewer.py:48` |
| `COMPLETION_RADIUS_PX` | 10.0 | `complete.py` |

`MIN_SHIFT_PX = 16` exists because correcting small offsets **hurts**:
"correcting" an 8 px offset (one bin, our measurement resolution) made 47 pairs
worse. Gating on >= 16 px keeps nearly all the gain (313 vs 328 pairs >= 0.10)
while harming 7 pairs instead of 47. **Caveat on record:** the 16 px value was
chosen while looking at those outcomes, so the figures are mildly optimistic —
confirming it cleanly needs held-out chains. `RELIABLE_NCC = 0.45` drops
untrustworthy pairs from the weighted least-squares offset solve entirely.

`COMPLETION_RADIUS_PX = 10` sits above the within-cluster spread (p90 4.5 px,
p99 9 px) and is where the fingerprint AUC of position-only candidates still
held (0.657 at 7–10 px). `MIN_SHIFT_PX` gates the *chain* on its largest
per-session offset; it is not applied per session (see §2).

Params live in `meanap.params.Params` as eight `track_*` fields.
`track_cells` defaults to **False** — tracking is opt-in and does not run in an
ordinary CAT-NAP run.

## 4. Traps — every one of these cost real time

**ROICaT applies a second registration you did not ask for.** Its *non-rigid*
step moves things ~19 px even when you hand it pre-aligned data. That silently
destroyed a 94-chain run (`OPME230825_2` fell 0.740 → 0.015). Fix:
`NullRegistration` — but **only when pre-registered**. Applying it
unconditionally broke the gated-out chains, which still need ROICaT's own
alignment. See `roicat.py`.

**ROICaT's defaults want network downloads.** `PhaseCorrelation` /
`OpticalFlowFarneback` are pinned explicitly; the library defaults (RoMa,
DeepFlow) fetch models. Do not "simplify" those arguments away.

**Parallel ROICaT needs a private `TMPDIR` per worker.** Four workers sharing
one tmpdir corrupt `ROInet.zip` while extracting it. This cost ~18 hours,
compounded by a waiter using `pgrep -f "phase16_isolate"` that matched *itself*
and spun forever instead of reporting the crash. Never `pgrep`/`pkill` on a
pattern your own command line contains.

**Subprocesses need `PYTHONPATH`.** The per-chain `__main__.py` entry point runs
under `.venv-roicat`, which has no `meanap` installed.

**Plain least squares on offsets drags good sessions** by letting one bad
pair pull a whole chain. The solve must be weighted and run per connected
component.

**`except Exception` hid a real bug.** `community_louvain(w, seed=...)` is the
wrong keyword; the exception was swallowed, every node landed in one module, and
"99% role stability" was measuring nothing. A test now forbids a bare
`except Exception` there. Treat any suspiciously perfect stability number as a
bug until proven otherwise.

**`rglob` does not follow symlinked directories.** `write_bundle` reported
success while producing 0 MB. Fixed with `_walk_files` plus a refusal to write
an empty bundle.

**Verify against regenerated files, not leftovers.** I once reported "render OK"
from stale `/tmp` files from an earlier demo. Check timestamps.

**`pkill -f <pattern>` kills the shell that runs it** if the pattern is in
that shell's own command line (exit 144, workers untouched). Same trap as the
`pgrep` one above, hit again on 2026-09-17. Kill the launcher by PID first,
then the workers by PID from a `ps` listing.

**A parallel run's parent holds the code it started with.** Edit
`ChainResult` while `track_dataset(workers>1)` is running and the later
subprocesses write a field the parent's dataclass does not have; the parent
then dies collecting results (`unexpected keyword argument 'merged'`) after
every chain has finished. The per-chain JSONs and ROICaT runs are intact —
re-run with `reuse_runs` pointing at that run's `work/runs` and it completes
in under a minute.

**`roi#` in the raw `stat.npy` is not `roi#` in the tracking labels.** The
labels index the *iscell-filtered* array. Look cells up by position, never by
an index carried across the filter.

**A pipe swallows a subprocess's progress.** `python ... | grep | tail` buffers
stdout until exit; you see nothing for ten minutes and assume it hung.
`PYTHONUNBUFFERED=1` and redirect to a file.

## 5. Things that look like bugs but are not

- **92 payloads for 93 chains.** `3_OPME230505_P1_pup5A_KO_MOI25000` has
  `frac_tracked [0.0, 0.0]` — a 224.6 px shift across DIVs 16→44. Zero matches,
  so nothing to render. Correct behaviour.
- **The network view has no stored numbers.** `metricStability` / `stability`
  are computed live by `tracking_network(chain)` on request. An empty
  `network` key in a payload JSON is expected.
- **The "Cell tracking" tab ships hidden.** It un-hides only after
  `/api/tracking` answers (`viewer/page.py:1776-1779`). A statically saved HTML
  page therefore never shows it, with no error. The tab exists only in the
  served viewer.

## 6. Open items

1. **The longitudinal analysis on the 71 usable chains has not been run.** This
   is the actual science and the obvious next step — everything built so far is
   machinery for it. Within-prep only (see §2). With completion and merging,
   1,351 cells in the viewer payloads span ≥ 3 days (was 561).
2. **Neuropil validation used a proxy.** Real `F - 0.7*Fneu` gave AUC 0.681 and
   did *not* reproduce the strong proxy result (0.741). Phases 15/18 are
   superseded by phase 20, not comparable to it.
3. **The 16 px threshold has never been validated on held-out chains** (§3).
   If a group result ends up leaning on it, this is the hole a reviewer finds.
4. **KO coverage is poor** (8 of 20 chains usable) and structurally so — those
   preps really are different fields. More processing will not fix it.
5. **ROICaT's own registration may hurt aligned chains.** `OPME240112_5`'s
   0 px pairs improved 2.5× just from `NullRegistration`; one earlier chain
   went the other way (0.36 → 0.06). Test on aggregate before changing the
   passthrough branch.
6. **66% of a tracked cell's missing days have no suite2p ROI at all** (a
   bright, transient-free soma is invisible to suite2p). Only seeded
   re-extraction from the movies recovers those; matching cannot.
7. **3,966 singleton-to-singleton candidates** (unmatched ROI with an
   unmatched ROI ≤ 10 px away next day) are untested — no cluster anchor.

## 7. Running it

```bash
# viewer on the packaged run
.venv/bin/python -m meanap.viewer local/demo_celltracking.meanap

# tests
.venv/bin/python -m pytest python/test_catnap_tracking.py -q
```

Tracking in a pipeline run is enabled with `track_cells=True`, or the tracking
box in the CAT-NAP GUI panel.

## 8. Unrelated uncommitted work in the tree

At handoff time these were modified and are **not** tracking-related; do not
sweep them into a tracking commit:
`catnap/activities.py`, `gui/panels/stats.py`, `pipeline/plotting_step2.py`,
`pipeline/plotting_step4.py`, `stats/measures.py`.
