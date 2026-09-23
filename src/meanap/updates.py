"""Which copy of MEA-NAP is running, which others could run, and whether it is current.

MEA-NAP is distributed as a git clone, not an installer, so "the version" is
whatever the clone has checked out. That gives two kinds of user:

**Cutting edge.** The clone tracks ``main`` on GitHub. New work lands there
between releases, and the only question is whether the local copy has fallen
behind — so :func:`check` fetches and counts, and :func:`update_main`
fast-forwards. Fast-forward only, on purpose: a user with local edits or local
commits is told so and left alone, never merged or reset on their behalf.

**A release.** Someone reproducing a paper, or who wants code that will not
move under them, runs a tagged version. Each release is checked out into its
own folder with ``git worktree`` (:func:`ensure_release`), which shares the
clone's history — no second download — and leaves the clone itself, with
whatever the user has done to it, exactly as it was. Checking a tag out *in
place* would do neither, and would make the Python GUI vanish on the spot for
any release that predates it.

Releases before the Python port are MATLAB-only, so :func:`launch_plan` works
out how a given folder is actually started: this GUI when it has one, MATLAB's
``runPipelineApp`` otherwise.

Everything here shells out to ``git`` and never raises for an ordinary
failure — offline, no git, not a clone, a remote that will not answer. Those
come back as an ``error`` string for the GUI to show, because a version check is
a courtesy and must never be the thing that stops someone running an analysis.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "MAIN",
    "UPSTREAM",
    "Checkout",
    "Release",
    "Status",
    "UpdateResult",
    "LaunchPlan",
    "find_checkout",
    "upstream_remote",
    "releases",
    "check",
    "update_main",
    "versions_dir",
    "release_dir",
    "ensure_release",
    "launch_plan",
    "launch",
]

#: The branch that "cutting edge" means.
MAIN = "main"

#: The repository releases come from, as ``owner/name``. Matched against the
#: clone's remotes rather than assuming ``origin``, because someone who forked
#: MEA-NAP has their fork as ``origin`` and ours as ``upstream`` — and a fork's
#: ``main`` is not what "out of date" should be measured against.
UPSTREAM = "SAND-Lab/MEA-NAP"

#: How long a network git command may take before we give up on it. Long enough
#: for a slow connection to fetch a few commits, short enough that a hung
#: proxy does not leave the check spinning forever.
NETWORK_TIMEOUT_S = 60

#: Release tags as MEA-NAP writes them: ``v1.10.2``, and the odd ``v1.9.2a``.
_RELEASE_TAG = re.compile(r"^v\d+\.\d+\.\d+[a-z]?$")

#: The file whose presence means a version has the Python GUI.
_PYTHON_GUI_ENTRY = "src/meanap/gui/app.py"

#: Files whose change means the Python environment may need re-syncing.
_DEPENDENCY_FILES = ("pyproject.toml", "uv.lock")


# ── git ──────────────────────────────────────────────────────────────────────

class GitError(RuntimeError):
    """A git command failed; the message is git's own, trimmed."""


def _git(repo: Path, *args: str, timeout: float = 15, stdin: str | None = None) -> str:
    """Run ``git -C repo args…`` and return stdout, or raise :class:`GitError`.

    ``GIT_TERMINAL_PROMPT=0`` because this runs from a GUI with no terminal: a
    remote that wants a password must fail, not wait for input nobody can type.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout, env=env,
            check=False, input=stdin,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed, or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} took longer than {timeout:.0f} s") from exc
    if out.returncode != 0:
        msg = (out.stderr or out.stdout).strip()
        raise GitError(msg or f"git {args[0]} failed ({out.returncode})")
    return out.stdout.strip()


# ── What is running ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Checkout:
    """The working tree this code was loaded from."""

    root: Path
    #: The clone that owns the history. Same as ``root`` for an ordinary clone;
    #: for a release worktree it is the clone the worktree was made from, which
    #: is where "cutting edge" lives.
    clone: Path
    commit: str
    branch: str | None     # None when detached, as a release worktree is
    tag: str | None        # the release tag at HEAD, if there is one

    @property
    def is_main(self) -> bool:
        return self.branch == MAIN

    @property
    def is_release(self) -> bool:
        return self.tag is not None and self.branch is None

    def describe(self) -> str:
        """``"main"``, ``"v1.10.2"``, or ``"branch foo"`` — for the dialog."""
        if self.is_release:
            return self.tag
        if self.branch:
            return self.branch if self.is_main else f"branch {self.branch}"
        return f"commit {self.commit[:7]}"


def find_checkout(start: Path | None = None) -> Checkout | None:
    """Describe the working tree containing *start* (default: this package).

    ``None`` when there is no working tree — an installed wheel, or no git —
    in which case there is nothing to select or update from inside the GUI.
    """
    start = Path(start) if start is not None else Path(__file__).resolve().parent
    try:
        root = Path(_git(start, "rev-parse", "--show-toplevel"))
        common = Path(_git(root, "rev-parse", "--git-common-dir"))
        commit = _git(root, "rev-parse", "HEAD")
    except GitError:
        return None
    if not common.is_absolute():
        common = (root / common).resolve()
    # A bare common dir has no working tree to call "the clone"; fall back to
    # the tree we are in, which is at least somewhere real.
    clone = common.parent if common.name == ".git" else root
    try:
        branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except GitError:
        branch = None
    tag = None
    try:
        for t in _git(root, "tag", "--points-at", "HEAD").splitlines():
            if _RELEASE_TAG.match(t):
                tag = t
                break
    except GitError:
        pass
    return Checkout(root=root, clone=clone, commit=commit, branch=branch, tag=tag)


def _normalise_url(url: str) -> str:
    """``git@github.com:SAND-Lab/MEA-NAP.git`` → ``sand-lab/mea-nap``."""
    url = url.strip().lower().removesuffix("/").removesuffix(".git")
    return "/".join(re.split(r"[:/]", url)[-2:])


def upstream_remote(repo: Path) -> str | None:
    """Name of the remote that points at :data:`UPSTREAM`, else ``origin``.

    ``None`` when the clone has no remotes at all (a copied folder, say).
    """
    try:
        names = _git(repo, "remote").split()
    except GitError:
        return None
    want = UPSTREAM.lower()
    for name in names:
        try:
            if _normalise_url(_git(repo, "remote", "get-url", name)) == want:
                return name
        except GitError:
            continue
    if "origin" in names:
        return "origin"
    return names[0] if names else None


# ── Releases ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Release:
    tag: str
    date: str    # YYYY-MM-DD, from the tag
    #: Whether this release includes the Python GUI. Those before it are
    #: MATLAB-only, which decides how :func:`launch_plan` starts them.
    python_gui: bool = False


def releases(repo: Path) -> list[Release]:
    """Release tags known to the clone, newest first.

    Only what has been fetched — :func:`check` fetches tags, so after one check
    this includes anything published since the clone was made.
    """
    try:
        out = _git(repo, "tag", "--list", "v*", "--sort=-v:refname",
                   "--format=%(refname:short)\t%(creatordate:short)")
    except GitError:
        return []
    tagged = [(t, d) for t, _, d in (ln.partition("\t") for ln in out.splitlines())
              if _RELEASE_TAG.match(t)]
    # One batch lookup rather than a git call per tag: which releases carry the
    # Python GUI, without checking any of them out.
    python_gui: set[str] = set()
    if tagged:
        try:
            probe = _git(repo, "cat-file", "--batch-check", stdin="".join(
                f"refs/tags/{t}:{_PYTHON_GUI_ENTRY}\n" for t, _ in tagged))
            python_gui = {t for (t, _), line in zip(tagged, probe.splitlines())
                          if not line.endswith("missing")}
        except GitError:
            pass
    return [Release(tag=t, date=d, python_gui=t in python_gui) for t, d in tagged]


# ── Is it current? ───────────────────────────────────────────────────────────

@dataclass
class Status:
    """The outcome of one :func:`check`."""

    checkout: Checkout | None
    remote: str | None = None
    #: Commits on the remote's ``main`` that the clone's ``main`` lacks, and
    #: the reverse. ``None`` when that could not be worked out.
    behind: int | None = None
    ahead: int | None = None
    latest_release: str | None = None
    releases: list[Release] = field(default_factory=list)
    #: Why the check could not finish, in words a user can act on.
    error: str | None = None

    @property
    def update_available(self) -> bool:
        """Something newer exists for what is *running*.

        For cutting edge that is new commits on ``main``; for a release, a
        newer release. A feature branch is somebody's work in progress and is
        not nagged about.
        """
        co = self.checkout
        if co is None:
            return False
        if co.is_main:
            return bool(self.behind)
        if co.is_release and self.latest_release:
            return _tag_key(self.latest_release) > _tag_key(co.tag)
        return False


def _tag_key(tag: str) -> tuple:
    m = re.match(r"^v(\d+)\.(\d+)\.(\d+)([a-z]?)$", tag or "")
    if not m:
        return ()
    return (int(m[1]), int(m[2]), int(m[3]), m[4])


#: Default for :func:`check`: "whatever is running", as distinct from an
#: explicit ``None``, which means "not a clone" and must not be second-guessed.
_RUNNING = object()


def check(checkout: Checkout | None = _RUNNING, *, fetch: bool = True,  # type: ignore[assignment]
          remote: str | None = None) -> Status:
    """Fetch from GitHub and say how far the clone's ``main`` is behind.

    Compares the clone's ``main`` branch — not whatever is checked out — with
    the remote's, so the answer means the same thing from a release worktree
    as from the clone itself. Tags come down in the same fetch, which is how a
    new release shows up in the list.
    """
    checkout = find_checkout() if checkout is _RUNNING else checkout
    status = Status(checkout=checkout)
    if checkout is None:
        status.error = ("This copy of MEA-NAP is not a git clone, so it cannot "
                        "check for or download updates itself.")
        return status
    repo = checkout.clone
    status.remote = remote or upstream_remote(repo)
    if status.remote is None:
        status.error = "This clone has no remote to check against."
        status.releases = releases(repo)
        return status
    if fetch:
        try:
            _git(repo, "fetch", "--quiet", "--tags", status.remote,
                 f"+refs/heads/{MAIN}:refs/remotes/{status.remote}/{MAIN}",
                 timeout=NETWORK_TIMEOUT_S)
        except GitError as exc:
            status.error = f"Could not reach GitHub to check for updates ({exc})."
    status.releases = releases(repo)
    status.latest_release = status.releases[0].tag if status.releases else None
    try:
        counts = _git(repo, "rev-list", "--left-right", "--count",
                      f"{MAIN}...{status.remote}/{MAIN}")
        ahead, behind = (int(n) for n in counts.split())
        status.ahead, status.behind = ahead, behind
    except (GitError, ValueError) as exc:
        status.error = status.error or f"Could not compare with {status.remote}/{MAIN} ({exc})."
    return status


# ── Updating cutting edge ────────────────────────────────────────────────────

@dataclass
class UpdateResult:
    ok: bool
    message: str
    old: str | None = None
    new: str | None = None
    #: Dependency files the update changed. Non-empty means the Python
    #: environment may be missing a package the new code imports.
    dependencies_changed: list[str] = field(default_factory=list)


def update_main(checkout: Checkout, remote: str, *, fetch: bool = True) -> UpdateResult:
    """Fast-forward the clone's ``main`` to the remote's.

    Refuses rather than improvise: the clone must have ``main`` checked out,
    and git itself refuses when the fast-forward would overwrite a local edit
    or when local commits mean there is nothing to fast-forward to. Either way
    the clone is left exactly as it was and the message says why.
    """
    repo = checkout.clone
    try:
        branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    except GitError:
        branch = None
    if branch != MAIN:
        where = f"branch '{branch}'" if branch else "a detached commit"
        return UpdateResult(False, (
            f"The MEA-NAP folder ({repo}) is on {where}, not '{MAIN}', so it "
            f"was not updated. Switch it to '{MAIN}' with git to follow the "
            "cutting edge."))
    try:
        old = _git(repo, "rev-parse", "HEAD")
        if fetch:
            _git(repo, "fetch", "--quiet", "--tags", remote,
                 f"+refs/heads/{MAIN}:refs/remotes/{remote}/{MAIN}",
                 timeout=NETWORK_TIMEOUT_S)
        _git(repo, "merge", "--ff-only", "--quiet", f"{remote}/{MAIN}", timeout=120)
        new = _git(repo, "rev-parse", "HEAD")
    except GitError as exc:
        return UpdateResult(False, _explain_merge_failure(str(exc), repo))
    if old == new:
        return UpdateResult(True, "Already up to date.", old, new)
    changed = _git(repo, "diff", "--name-only", old, new, "--", *_DEPENDENCY_FILES)
    n = _git(repo, "rev-list", "--count", f"{old}..{new}")
    return UpdateResult(
        True, f"Updated {old[:7]} → {new[:7]} ({n} new commit{'s' if n != '1' else ''}).",
        old, new, [c for c in changed.splitlines() if c])


def _explain_merge_failure(err: str, repo: Path) -> str:
    low = err.lower()
    if "would be overwritten" in low:
        files = [ln.strip() for ln in err.splitlines()
                 if ln.startswith(("\t", "    "))]
        listed = ("\n  " + "\n  ".join(files[:8])) if files else ""
        return ("Not updated: you have local changes to files the update also "
                f"changes.{listed}\n\nCommit or stash them in {repo} and try "
                "again. Nothing was modified.")
    if "not possible to fast-forward" in low or "diverg" in low:
        return ("Not updated: this clone's 'main' has commits of its own that "
                "GitHub's does not, so it cannot simply move forward. Merge or "
                f"rebase in {repo} with git. Nothing was modified.")
    return f"Not updated: {err}"


# ── Running a release ────────────────────────────────────────────────────────

def versions_dir() -> Path:
    """Where release worktrees go: ``~/.meanap/versions`` unless overridden.

    Outside the clone, so they never show up in its ``git status``; one folder
    per release, so switching back and forth costs nothing after the first time.
    """
    override = os.environ.get("MEANAP_VERSIONS_DIR")
    return Path(override).expanduser() if override else Path.home() / ".meanap" / "versions"


def release_dir(tag: str, root: Path | None = None) -> Path:
    return (root or versions_dir()) / f"MEA-NAP-{tag}"


def ensure_release(clone: Path, tag: str, root: Path | None = None) -> Path:
    """Check release *tag* out into its own folder, or reuse it; return the folder.

    Raises :class:`GitError` when *tag* is not a release the clone knows, or
    the folder exists but is something else — never deletes to make room.
    """
    if not _RELEASE_TAG.match(tag):
        raise GitError(f"'{tag}' is not a release tag")
    target = release_dir(tag, root)
    if target.exists():
        co = find_checkout(target)
        if co is not None and co.root.resolve() == target.resolve() and co.tag == tag:
            return target
        raise GitError(f"{target} already exists and is not MEA-NAP {tag}; "
                       "move it aside and try again")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Prune first: a worktree whose folder someone deleted by hand is still
    # registered, and git refuses to add another at the same path until it
    # forgets the old one.
    try:
        _git(clone, "worktree", "prune")
    except GitError:
        pass
    _git(clone, "worktree", "add", "--detach", str(target), f"refs/tags/{tag}",
         timeout=300)
    return target


@dataclass(frozen=True)
class LaunchPlan:
    """How to start the copy of MEA-NAP in ``folder``."""

    folder: Path
    kind: str                 # "python" | "matlab" | "manual"
    program: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    #: What happens, or what to do when nothing can be started for the user.
    explanation: str = ""


def launch_plan(folder: Path, *, matlab: str | None = None) -> LaunchPlan:
    """Work out how to start the MEA-NAP in *folder*.

    A version with the Python GUI is started with this same interpreter, its
    own ``src`` first on the path so its code — not ours — is what loads. An
    older, MATLAB-only release opens in MATLAB when MATLAB can be found, and
    otherwise gets instructions, because only the user knows where theirs is.
    """
    folder = Path(folder)
    if (folder / _PYTHON_GUI_ENTRY).is_file():
        env = {"PYTHONPATH": os.pathsep.join(
            [str(folder / "src"), *filter(None, [os.environ.get("PYTHONPATH")])])}
        return LaunchPlan(
            folder, "python", sys.executable, ("-m", "meanap.gui.app"), env,
            "Opens this version's MEA-NAP window in a new process, using the "
            "current Python environment.")
    entry = ("runPipelineApp" if (folder / "runPipelineApp.m").is_file()
             else "edit MEApipeline")
    matlab = matlab if matlab is not None else shutil.which("matlab")
    how = (f"In MATLAB, go to {folder} and run {entry.removeprefix('edit ')}.")
    if matlab:
        quoted = str(folder).replace("'", "''")
        return LaunchPlan(
            folder, "matlab", matlab, ("-r", f"cd('{quoted}'); {entry}"), {},
            "This version predates the Python GUI, so it opens in MATLAB. " + how)
    return LaunchPlan(
        folder, "manual", explanation=(
            "This version predates the Python GUI and runs in MATLAB, which "
            "could not be found on this computer's PATH. " + how))


def launch(plan: LaunchPlan, extra_args: tuple[str, ...] = ()) -> subprocess.Popen:
    """Start *plan* detached from this process, so closing this window leaves it running."""
    if plan.program is None:
        raise GitError(plan.explanation)
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [plan.program, *plan.args, *extra_args], cwd=plan.folder,
        env={**os.environ, **plan.env}, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
