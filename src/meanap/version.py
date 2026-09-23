"""Which version of which pipeline produced a result.

Three pipelines ship from this repository and move at different speeds, so one
number cannot describe them: MEA-NAP's electrophysiology path is mature and
versioned back to 2023, CAT-NAP is a recent port, and MEA-Stim is mid-port.
A result is only reproducible if it records the version of the pipeline that
actually ran, which is the mode's version, not the repository's.

**Where the numbers live.** MEA-NAP's stays in ``version.txt`` at the repo
root, unchanged and unduplicated: MATLAB's ``getParamsFromApp.m`` reads that
file into ``Params.version``, and ``getVersion.m`` compares it against the copy
on GitHub to tell users they are out of date. Writing it in a second place
would let the two disagree, and the MATLAB side is the one users are told to
check. The two newer subsystems have no such history, so they are declared in
``versions.json`` beside it.

**Which build.** Between official releases ``main`` moves on every merge while
``version.txt`` stays put, so "1.11.0" alone cannot tell last week's result
from today's. :func:`build_info` adds what git knows — the development-build
tag (``v1.11.0-dev.23``, see ``.github/workflows/dev-build.yml``), the commit,
and whether the code had uncommitted edits — and :func:`version_stamp` records
it with every run.

Both files are read at import and cached. A missing or unparseable file yields
:data:`UNKNOWN` rather than raising — a version string is metadata, and failing
a run because it could not be stamped would be a poor trade.
"""

from __future__ import annotations

import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

__all__ = [
    "UNKNOWN",
    "PIPELINE_NAMES",
    "meanap_version",
    "pipeline_version",
    "pipeline_label",
    "all_versions",
    "version_stamp",
    "build_info",
    "build_label",
]

#: What a version reads as when the file it comes from is missing or malformed.
#: Deliberately not ``"0.0.0"``: a real number would be silently comparable and
#: silently wrong, while this cannot be mistaken for one.
UNKNOWN = "unknown"

#: Display names, keyed by the mode keys in :mod:`meanap.gui.modes`.
PIPELINE_NAMES = {
    "meanap": "MEA-NAP",
    "catnap": "CAT-NAP",
    "meastim": "MEA-Stim",
}

_VERSION_TXT = "version.txt"
_VERSIONS_JSON = "versions.json"


def _version_file(name: str) -> Path | None:
    """Locate one version file, or ``None``.

    Two places, because MEA-NAP is used both ways. From a clone —
    ``src/meanap/version.py`` → three parents up is the repo root — the files
    sit beside ``MEApipeline.m``, which is what lets MATLAB and Python read the
    same ``version.txt``. From an installed wheel there is no repo, so the
    build copies them in beside this module (see ``force-include`` in
    ``pyproject.toml``); without that an installed copy would report
    :data:`UNKNOWN` for everything.
    """
    here = Path(__file__).resolve()
    for candidate in (here.parent / name, here.parents[2] / name):
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def meanap_version() -> str:
    """MEA-NAP's version, from ``version.txt`` — the same file MATLAB reads."""
    path = _version_file(_VERSION_TXT)
    if path is None:
        return UNKNOWN
    try:
        text = path.read_text().strip()
    except OSError:
        return UNKNOWN
    return text.splitlines()[0].strip() if text else UNKNOWN


@lru_cache(maxsize=1)
def _subsystem_versions() -> dict[str, str]:
    path = _version_file(_VERSIONS_JSON)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: str(v).strip() for k, v in data.items()
            if not k.startswith("_") and isinstance(v, (str, int, float))}


def pipeline_version(mode: str) -> str:
    """Version of one pipeline, by mode key (``meanap`` / ``catnap`` / ``meastim``).

    Unknown keys return :data:`UNKNOWN` rather than raising: this is called
    while stamping output, and an unrecognised mode should cost the stamp, not
    the run.
    """
    if mode == "meanap":
        return meanap_version()
    return _subsystem_versions().get(mode, UNKNOWN)


def pipeline_label(mode: str) -> str:
    """``"CAT-NAP 1.0.1"`` — the form shown in the GUI and written into output."""
    name = PIPELINE_NAMES.get(mode, mode)
    return f"{name} {pipeline_version(mode)}"


def all_versions() -> dict[str, str]:
    """Every pipeline's version, for the manifest and the About box."""
    return {key: pipeline_version(key) for key in PIPELINE_NAMES}


@lru_cache(maxsize=1)
def build_info() -> dict[str, object]:
    """The exact code running, from git: ``{"describe", "commit", "dirty"}``.

    ``describe`` is the nearest version tag plus any commits since, e.g.
    ``v1.11.0-dev.23`` on a tagged build or ``v1.11.0-dev.23-2-g1a2b3c4`` two
    commits past it, with ``-dirty`` when files were edited. Empty when there
    is no git checkout (an installed wheel) or no git — the version number is
    then all there is to say, and saying nothing is better than guessing.
    """
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return {}
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True,
            timeout=10, env=env, check=True).stdout.strip()

    try:
        commit = git("rev-parse", "HEAD")
        describe = git("describe", "--tags", "--match", "v[0-9]*",
                       "--always", "--dirty")
    except (OSError, subprocess.SubprocessError):
        return {}
    return {"describe": describe, "commit": commit,
            "dirty": describe.endswith("-dirty")}


def build_label() -> str | None:
    """``"v1.11.0-dev.23"`` (or its describe string) for display, if known."""
    return build_info().get("describe") or None


def version_stamp(mode: str) -> dict:
    """What a run records about the code that produced it.

    Carries the running pipeline's own version *and* the whole set. The set
    costs three short strings and answers the question a result raises years
    later — "which CAT-NAP was this?" — even when the reader has forgotten
    which mode the run used.
    """
    stamp = {
        "pipeline": mode,
        "pipeline_name": PIPELINE_NAMES.get(mode, mode),
        "version": pipeline_version(mode),
        "versions": all_versions(),
    }
    build = build_info()
    if build:
        stamp["build"] = dict(build)
    return stamp
