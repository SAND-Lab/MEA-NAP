---
key: cell_tracking
name: Cross-day cell tracking
tab: CAT-NAP (calcium imaging)
labels: Cross-day cell tracking
params: track_cells, track_min_shift_px, track_tracked_threshold, track_completion_radius_px, track_validate_activity
related: cell_types, catnap_mode
---
Finds the same cells in recordings of the same field of view made on different days (DIVs), so each cell's activity and network role can be followed through development.

## What it does

With **Track the same cells across DIVs** ticked (off by default), after the recordings are analysed MEA-NAP:

1. **Groups recordings into chains**: recordings whose names are the same apart from the `DIV<n>` token and an 8-digit date. A shared name is only a hypothesis; each pair of days is checked from the layout of the ROIs.
2. **Registers each chain** from the ROI footprints. A chain in which no day would move by at least **Register above** (default 16 px) is left unregistered, because correcting an offset smaller than the measurement can resolve adds error.
3. **Matches cells with ROICaT**, using MEA-NAP's registration in place of ROICaT's own.
4. **Completes** a tracked cell that is missing on one day with the single unmatched cell within **Complete within** (default 10 px) of where it should be. Cells added this way are flagged in every output; 0 turns this off.
5. **Validates** the matches, if *Validate matches against activity the matcher never saw* is ticked (the default). Each matched cell's activity fingerprint across days is compared with that of its nearest spatial neighbour: a different cell in the same place.

A chain counts as tracked when its median match rate between days is at least **Tracked above** (default 0.10).

## Choosing a value

**Tracked above** should sit above the match rate you get between fields of view that are known to differ. 0.10 is the false-positive floor measured on one dataset (the Mecp2 cultures) and does not transfer, so measure it on your own rig. Leave **Register above** at its default unless your ROI density differs a lot.

## How MEA-NAP uses it

Results go to `CellTracking/` in the output folder: per-chain results, a manifest and a quality-control page per chain. Choose a chain and **Open in viewer** to see every tracked cell's footprint and trace on each day, worst match first. The cell-type labels are read from the same places as *Cell-type file*.

## Things to watch for

- Tracking needs ROICaT and multi-DIV chains. If it fails, it logs why and the rest of the run is kept.
- A match rate means little without validation. Keep validation on.
- Names that carry other varying tokens, such as a time or a plate index, will not form chains.
