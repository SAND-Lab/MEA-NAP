"""Which calcium measure(s) a CAT-NAP run analyses, and what to call each one.

``Params.twop_activity`` names one measure of neuronal activity — detected
calcium events (``peaks``), the deconvolved/denoised trace (``denoised F``),
raw fluorescence (``F``), or suite2p's own spike estimate (``spks``). Every
adjacency matrix, activity statistic and network metric in a CAT-NAP run is
computed *through* that choice, and the choice is not neutral: ``peaks`` gives
an event-time STTC network, the other three give a binned correlation network,
and the two do not produce the same numbers or necessarily the same conclusion.

That made "which measure did you use?" an unanswerable-by-inspection question
about every published CAT-NAP result. ``Params.twop_activities`` lets one run
analyse several measures over the same recordings, so the question becomes an
axis of the output rather than a decision buried in a settings file — see
:mod:`meanap.stats.measures` for the analysis that reads it back.

Everything here is deliberately tiny and dependency-free: it is imported by the
pipeline, the GUI, the statistics step and the report, and none of them should
have to agree on the spelling of ``denoisedF`` by copying it.
"""

from __future__ import annotations

__all__ = [
    "ACTIVITY_TYPES",
    "BY_ACTIVITY_DIR",
    "activity_output_root",
    "activity_params",
    "activity_subtrees",
    "ACTIVITY_SLUGS",
    "DEFAULT_ACTIVITY",
    "activity_from_slug",
    "activity_slug",
    "activity_types",
    "is_multi_activity",
    "primary_activity",
]

#: Every measure ``suite2p_to_adjm`` understands, in the order the GUI lists
#: them: the default first, then the two derived traces, then the raw one.
ACTIVITY_TYPES: tuple[str, ...] = ("peaks", "denoised F", "F", "spks")

DEFAULT_ACTIVITY = "peaks"

#: Filesystem-safe name for each measure. ``denoised F`` is the only one that
#: needs it, but the mapping is total so callers never have to special-case.
#: These strings end up in folder names (``denoisedF_1000msbin/``) and in file
#: names (``rec_denoisedF_catnap.npz``), so they are part of the output format
#: and must not be re-spelled casually.
ACTIVITY_SLUGS: dict[str, str] = {
    "peaks": "peaks",
    "denoised F": "denoisedF",
    "F": "F",
    "spks": "spks",
}


def activity_slug(activity: str) -> str:
    """Filesystem-safe name for *activity* (``'denoised F'`` → ``'denoisedF'``)."""
    name = str(activity)
    if name in ACTIVITY_SLUGS:
        return ACTIVITY_SLUGS[name]
    # An unknown measure is still worth naming rather than crashing on: strip
    # what a path cannot carry and keep going.
    return "".join(c for c in name if c.isalnum() or c in "-_") or "activity"


def activity_from_slug(slug: str) -> str | None:
    """Reverse :func:`activity_slug` for the known measures, else ``None``.

    Used when reading a run back off disk — a file name carries the slug, and
    the tables and figures want the measure's real name.
    """
    for name, known in ACTIVITY_SLUGS.items():
        if known == str(slug):
            return name
    return None


def activity_types(params) -> list[str]:
    """The measures this run analyses, primary first, de-duplicated.

    ``Params.twop_activities`` empty (the default, and what every settings file
    written before multi-measure runs existed carries) means "just
    ``twop_activity``" — so a run configured the old way behaves exactly as it
    did, down to the folder names.

    ``twop_activity`` is always first in the list whether or not it also
    appears in ``twop_activities``: it is the *primary* measure, the one whose
    outputs keep the unprefixed names, and demoting it because the user ticked
    the boxes in a different order would silently rename half a run's files.
    """
    primary = str(getattr(params, "twop_activity", DEFAULT_ACTIVITY)
                  or DEFAULT_ACTIVITY)
    out = [primary]
    for name in (getattr(params, "twop_activities", None) or ()):
        name = str(name)
        if name and name not in out:
            out.append(name)
    return out


def primary_activity(params) -> str:
    """The measure whose outputs carry the run's unprefixed names."""
    return activity_types(params)[0]


def is_multi_activity(params) -> bool:
    """Whether this run analyses more than one measure."""
    return len(activity_types(params)) > 1


# ── output layout ────────────────────────────────────────────────────────────

#: Folder holding the extra measures' outputs, one complete run subtree each.
#:
#: The *primary* measure keeps the top-level tree it has always had, so a run
#: that adds a second measure does not move a single file that a one-measure
#: run would have written. Each subtree below is a full, self-contained output
#: folder — its own ``ExperimentMatFiles``, ``2_NeuronalActivity``,
#: ``4_NetworkActivity``, ``netmet_results.json`` and ``params.json`` naming
#: that one measure — so the report, the bundle viewer and every tool that
#: already knows how to read a run folder can be pointed straight at it.
#:
#: The pooled tables at the top level are the exception, and the reason the
#: subtrees are not simply separate runs: ``NetworkActivity_RecordingLevel.csv``
#: and its three siblings carry every measure's rows with an ``ActivityType``
#: column, which is what lets step 5 compare the measures against each other
#: rather than against nothing.
BY_ACTIVITY_DIR = "ByActivityType"


def activity_output_root(output_root, params, activity: str):
    """Where *activity*'s figures, state files and JSON go within a run.

    The primary measure of any run — and every measure of a single-measure run
    — gets *output_root* itself.
    """
    from pathlib import Path

    root = Path(output_root)
    if not is_multi_activity(params) or activity == primary_activity(params):
        return root
    return root / BY_ACTIVITY_DIR / activity_slug(activity)


def activity_params(params, activity: str):
    """*params* as if the run had been configured for *activity* alone.

    Everything downstream of the measure choice — the lag-vs-bin naming, the
    adjacency builder, the activity statistics, the figure titles — already
    reads ``twop_activity`` and knows nothing about multi-measure runs. Handing
    each measure its own single-measure ``Params`` is what keeps it that way:
    the per-measure half of the pipeline is the same code doing the same thing,
    pointed at a different measure and a different output root.
    """
    import dataclasses

    return dataclasses.replace(params, twop_activity=str(activity),
                               twop_activities=())


def activity_subtrees(output_root, params):
    """``[(activity, params_for_it, output_root_for_it), …]``, primary first."""
    return [(a, activity_params(params, a), activity_output_root(output_root, params, a))
            for a in activity_types(params)]
