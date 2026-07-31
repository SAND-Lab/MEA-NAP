"""Deterministic random-number generation for the pipeline.

Several pipeline stages are stochastic: Step 3's probabilistic thresholding
(circular-shift surrogates), Step 4's modularity/consensus clustering, the
null-model randomizations behind the normalized participation coefficient and
small-worldness, NMF initialization, and a couple of "pick an example channel"
plotting choices. MATLAB's MEA-NAP never seeds any of these, so two MATLAB runs
on identical data already disagree on ``Q``/``nMod``/``SW``/``PC``/``Z`` and on
which edges survive thresholding.

This module makes that reproducible *within* the Python port (it cannot make it
reproducible against MATLAB — see ``python/PIPELINE_PORT_STATUS.md``). Set
``Params.random_seed`` to an integer and every stochastic stage derives its
generator from it; leave it ``None`` (the default) to keep the previous
non-deterministic behaviour.

The key requirement is that a run's numbers must not depend on *how* the work
was scheduled: Steps 3 and 4 run recordings across a process pool whose worker
count is auto-sized from the machine's cores/RAM, so drawing from one shared
stream would make results depend on the host. Instead every generator is
derived from ``(seed, label…)``, where the labels identify the work item
(step, recording, and where relevant the lag) — so a given recording gets the
same stream whether it ran first, last, or alone.

Labels are hashed with BLAKE2b rather than :func:`hash`, because Python
randomizes string hashing per process (``PYTHONHASHSEED``): ``hash("rec_A")``
differs between the parent and a spawned worker, which is exactly the
situation this module exists to avoid.
"""

from __future__ import annotations

import hashlib

import numpy as np

__all__ = ["make_rng", "derive_seed_int"]


def _label_to_int(label: str | int) -> int:
    """Map a label to a stable 64-bit int (stable across processes and runs)."""
    if isinstance(label, int):
        return label & 0xFFFFFFFFFFFFFFFF
    digest = hashlib.blake2b(str(label).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def make_rng(seed: int | None, *labels: str | int) -> np.random.Generator:
    """Return the generator for one unit of work.

    Parameters
    ----------
    seed
        ``Params.random_seed``. ``None`` → a fresh, OS-entropy-seeded generator
        (the port's historical behaviour: every run differs).
    labels
        Identify the work item, e.g. ``("step4", rec.filename)``. Two calls with
        the same seed and labels return generators that produce the same
        sequence; different labels give independent streams.
    """
    if seed is None:
        return np.random.default_rng()
    return np.random.default_rng(
        np.random.SeedSequence([int(seed), *(_label_to_int(x) for x in labels)])
    )


def derive_seed_int(seed: int | None, *labels: str | int) -> int:
    """A single non-negative 31-bit int derived the same way as :func:`make_rng`.

    For third-party APIs that take a plain integer seed rather than a NumPy
    generator (``sklearn``'s ``random_state``, numba's ``np.random.seed``).
    """
    return int(make_rng(seed, *labels).integers(0, 2**31 - 1))
