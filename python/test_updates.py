"""Choosing a MEA-NAP version, and keeping the cutting edge current.

Everything runs against throwaway git repositories standing in for GitHub, so
the checks need no network and cannot touch the real clone. Four groups:

  A. what is running — main, a release worktree, a branch, no clone at all;
  B. is it current — behind/ahead counts, new releases, which remote counts;
  C. updating — fast-forward only, and every refusal leaves the clone as it was;
  D. releases — each in its own worktree, started the right way;
  E. the GUI — the version button's badge and the versions dialog;
  F. the default version — what ``meanap-gui`` opens, and how it is chosen.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                   "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_CONFIG_NOSYSTEM": "1"}.items():
    os.environ[key] = value

from meanap import updates as U  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: object = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}"
          + (f"   [{detail}]" if detail != "" and not condition else ""))
    if not condition:
        FAILURES.append(name)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_world(tmp: Path) -> tuple[Path, Path, Path]:
    """A bare "GitHub", a user's clone of it, and a maintainer's clone that pushes."""
    github = tmp / "github.git"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(github))
    dev = tmp / "dev"
    git(tmp, "clone", "-q", str(github), str(dev))
    git(dev, "checkout", "-q", "-b", "main")
    commit(dev, {"version.txt": "1.0.0\n", "MEApipeline.m": "% v1\n",
                 "runPipelineApp.m": "% app\n", "pyproject.toml": "deps = 1\n"},
           "first release")
    git(dev, "tag", "v1.0.0")
    commit(dev, {"version.txt": "1.1.0\n",
                 "src/meanap/gui/app.py": "# gui\n"}, "python gui")
    git(dev, "tag", "v1.1.0")
    git(dev, "push", "-q", "origin", "main", "--tags")
    user = tmp / "user"
    git(tmp, "clone", "-q", str(github), str(user))
    return github, dev, user


def wait(job, app, timeout=30.0) -> None:
    """Let a background job finish and its result reach the UI thread."""
    end = time.time() + timeout
    while job._thread.is_alive() and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(5):
        app.processEvents()


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        os.environ["MEANAP_VERSIONS_DIR"] = str(tmp / "versions")
        github, dev, user = make_world(tmp)

        print("\nA — what is running")
        co = U.find_checkout(user)
        check("a clone on main is found", co is not None and co.is_main, co)
        check("…and is its own clone", co.clone == user.resolve(), co)
        check("…and is not a release", not co.is_release)
        check("a folder that is not a clone gives None",
              U.find_checkout(tmp) is None)
        st = U.check(U.find_checkout(tmp))
        check("…and a check of it explains itself, not raises",
              st.error is not None and not st.update_available, st.error)

        print("\nB — is it current")
        st = U.check(co)
        check("freshly cloned: nothing behind", st.behind == 0 and st.ahead == 0,
              (st.behind, st.ahead, st.error))
        check("no update is offered", not st.update_available)
        check("releases are listed newest first",
              [r.tag for r in st.releases] == ["v1.1.0", "v1.0.0"], st.releases)
        check("…knowing which have the Python GUI",
              {r.tag: r.python_gui for r in st.releases}
              == {"v1.1.0": True, "v1.0.0": False}, st.releases)
        new = commit(dev, {"MEApipeline.m": "% v2\n"}, "new work")
        git(dev, "push", "-q", "origin", "main")
        st = U.check(co)
        check("a commit pushed to GitHub shows as 1 behind",
              st.behind == 1, (st.behind, st.error))
        check("…and is offered as an update", st.update_available)
        check("the user's files are untouched by checking",
              (user / "MEApipeline.m").read_text() == "% v1\n")
        git(dev, "tag", "v1.2.0")
        git(dev, "push", "-q", "origin", "--tags")
        st = U.check(co)
        check("a new release arrives with the check",
              st.latest_release == "v1.2.0", st.latest_release)

        fork = tmp / "fork"
        git(tmp, "clone", "-q", str(user), str(fork))
        git(fork, "remote", "add", "upstream",
            "git@github.com:SAND-Lab/MEA-NAP.git")
        check("a fork measures against SAND-Lab's remote, not its own origin",
              U.upstream_remote(fork) == "upstream", U.upstream_remote(fork))
        check("…whatever the URL form",
              U._normalise_url("https://github.com/sand-lab/MEA-NAP.git/")
              == "sand-lab/mea-nap")
        check("otherwise origin", U.upstream_remote(user) == "origin")

        print("\nC — updating")
        result = U.update_main(co, "origin")
        check("the update fast-forwards to GitHub", result.ok
              and git(user, "rev-parse", "HEAD") == new, result.message)
        check("…and brings the new file content",
              (user / "MEApipeline.m").read_text() == "% v2\n")
        check("no dependency warning when none changed",
              result.dependencies_changed == [], result.dependencies_changed)
        again = U.update_main(co, "origin")
        check("updating again is a no-op that says so",
              again.ok and again.old == again.new, again.message)

        commit(dev, {"pyproject.toml": "deps = 2\n"}, "new dependency")
        git(dev, "push", "-q", "origin", "main")
        result = U.update_main(co, "origin")
        check("a changed pyproject.toml is reported",
              result.ok and result.dependencies_changed == ["pyproject.toml"],
              (result.message, result.dependencies_changed))

        commit(dev, {"MEApipeline.m": "% v3\n"}, "more work")
        git(dev, "push", "-q", "origin", "main")
        (user / "MEApipeline.m").write_text("% my edit\n")
        before = git(user, "rev-parse", "HEAD")
        result = U.update_main(co, "origin")
        check("a local edit the update would overwrite is refused",
              not result.ok and "local changes" in result.message, result.message)
        check("…naming the file", "MEApipeline.m" in result.message, result.message)
        check("…leaving the edit and the commit alone",
              (user / "MEApipeline.m").read_text() == "% my edit\n"
              and git(user, "rev-parse", "HEAD") == before)
        git(user, "checkout", "-q", "--", "MEApipeline.m")

        commit(user, {"notes.txt": "mine\n"}, "a local commit")
        before = git(user, "rev-parse", "HEAD")
        result = U.update_main(co, "origin")
        check("a clone with its own commits is refused, not merged",
              not result.ok and "commits of its own" in result.message, result.message)
        check("…and left where it was", git(user, "rev-parse", "HEAD") == before)
        git(user, "reset", "-q", "--hard", "origin/main")

        git(user, "checkout", "-q", "-b", "experiment")
        result = U.update_main(co, "origin")
        check("a clone on another branch is refused",
              not result.ok and "experiment" in result.message, result.message)
        st = U.check(U.find_checkout(user))
        check("…and a feature branch is not nagged about",
              not st.update_available)
        git(user, "checkout", "-q", "main")

        print("\nD — releases")
        folder = U.ensure_release(user, "v1.0.0")
        check("a release is checked out into its own folder",
              folder == tmp / "versions" / "MEA-NAP-v1.0.0" and
              (folder / "version.txt").read_text() == "1.0.0\n", folder)
        check("…without moving the clone",
              git(user, "symbolic-ref", "--short", "HEAD") == "main")
        rel = U.find_checkout(folder)
        check("the release knows what it is", rel.is_release and rel.tag == "v1.0.0", rel)
        check("…and where cutting edge lives", rel.clone == user.resolve(), rel)
        st = U.check(rel, fetch=False)
        check("an old release is told a newer one exists", st.update_available,
              (st.latest_release, rel.tag))
        check("choosing it again reuses the folder",
              U.ensure_release(user, "v1.0.0") == folder)
        (tmp / "versions" / "MEA-NAP-v1.1.0").mkdir()
        (tmp / "versions" / "MEA-NAP-v1.1.0" / "mine.txt").write_text("x")
        try:
            U.ensure_release(user, "v1.1.0")
            refused = False
        except U.GitError:
            refused = True
        check("a folder in the way is refused, not overwritten",
              refused and (tmp / "versions" / "MEA-NAP-v1.1.0" / "mine.txt").exists())
        subprocess.run(["rm", "-rf", str(tmp / "versions" / "MEA-NAP-v1.1.0")], check=True)
        try:
            U.ensure_release(user, "v9.9.9")
            ok = False
        except U.GitError:
            ok = True
        check("a release that does not exist is an error", ok)
        py = U.ensure_release(user, "v1.1.0")
        plan = U.launch_plan(py)
        check("a release with the Python GUI opens in Python",
              plan.kind == "python" and plan.env["PYTHONPATH"].startswith(str(py / "src")),
              plan)
        plan = U.launch_plan(folder, matlab="/opt/matlab")
        check("an older release opens in MATLAB when it is there",
              plan.kind == "matlab" and "runPipelineApp" in plan.args[-1]
              and str(folder) in plan.args[-1], plan)
        plan = U.launch_plan(folder, matlab="")
        check("…and otherwise says what to do",
              plan.kind == "manual" and "runPipelineApp" in plan.explanation, plan)
        subprocess.run(["rm", "-rf", str(folder)], check=True)
        check("a release folder deleted by hand is recreated",
              U.ensure_release(user, "v1.0.0").exists())

        print("\nE — the GUI")
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from meanap.gui.main_window import MainWindow
        from meanap.gui.versions_dialog import CUTTING_EDGE, VersionsDialog

        window = MainWindow()
        plain = window._version_label.text()
        check("the version button starts plain", "update" not in plain, plain)
        commit(dev, {"MEApipeline.m": "% v4\n"}, "yet more")
        git(dev, "push", "-q", "origin", "main")
        status = U.check(U.find_checkout(user))
        window._on_update_status(status)
        check("an update marks the version button",
              "update" in window._version_label.text(), window._version_label.text())
        check("…and its tooltip says how far behind",
              "1 new commit" in window._version_label.toolTip(),
              window._version_label.toolTip())

        dlg = VersionsDialog(checkout=status.checkout)
        dlg.set_status(status)
        items = [dlg._list.item(i) for i in range(dlg._list.count())]
        check("the dialog lists cutting edge first, then every release",
              [i.data(0x0100) for i in items] == [CUTTING_EDGE, "v1.2.0", "v1.1.0", "v1.0.0"],
              [i.text() for i in items])
        check("…marks the one running", "running" in items[0].text(), items[0].text())
        check("…and the MATLAB-only ones", "MATLAB" in items[3].text()
              and "MATLAB" not in items[2].text(), [i.text() for i in items])
        check("the running version cannot be 'opened' again",
              not dlg._open_button.isEnabled())
        dlg._list.setCurrentRow(3)
        check("a release can", dlg._open_button.isEnabled())
        check("the download button is offered when behind",
              not dlg._update_button.isHidden())
        dlg._on_update()
        check("the download runs in the background", len(dlg._jobs) == 1)
        wait(dlg._jobs[0], app)
        check("downloading brings the clone up to date",
              git(user, "rev-parse", "HEAD") == git(dev, "rev-parse", "HEAD"),
              dlg._update_message.text())
        check("…offers a restart", not dlg._restart_button.isHidden(),
              dlg._update_message.text())
        check("…and stops offering the download", dlg._update_button.isHidden())
        window._on_update_status(dlg._status)
        check("the badge follows the dialog's status",
              "update" not in window._version_label.text(), window._version_label.text())

        print("\nF — the default version")
        from PyQt6.QtCore import QSettings
        from meanap.gui import app as gui_app
        from meanap.gui.versions_dialog import default_version, set_default_version
        # Settings in the temp dir, so choosing a default here cannot change
        # the one on the machine running the tests.
        QSettings.setPath(QSettings.Format.NativeFormat,
                          QSettings.Scope.UserScope, str(tmp / "settings"))
        QSettings.setPath(QSettings.Format.IniFormat,
                          QSettings.Scope.UserScope, str(tmp / "settings"))
        set_default_version(None)
        here = U.find_checkout(user)
        check("never chosen: no default", default_version() is None)
        check("…and nothing to switch to", U.default_folder(None, here) is None)
        check("the default already running: stay",
              U.default_folder("main", here) is None)
        target = U.default_folder("v1.1.0", here)
        check("a Python release as default: switch to its folder",
              target == U.release_dir("v1.1.0"), target)
        check("a MATLAB-only release is never switched to automatically",
              U.default_folder("v1.0.0", here) is None)
        check("an unknown release is ignored, not an error",
              U.default_folder("v9.9.9", here) is None
              and U.default_folder("rm -rf", here) is None)
        rel = U.find_checkout(U.release_dir("v1.1.0"))
        check("from a release, a default of main switches to the clone",
              U.default_folder("main", rel) == user.resolve(),
              U.default_folder("main", rel))
        os.environ[U.NO_REDIRECT_ENV] = "1"
        check("a copy started by a switch does not switch again",
              U.default_folder("v1.1.0", here) is None)
        del os.environ[U.NO_REDIRECT_ENV]
        check("…because every Python launch carries the guard",
              U.launch_plan(U.release_dir("v1.1.0")).env.get(U.NO_REDIRECT_ENV) == "1")
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, sys.argv[1]);"
             "from meanap import updates as U;"
             "U.exec_into(U.LaunchPlan(U.Path('.'), 'python', sys.executable,"
             " ('-c', 'import os,sys; print(sys.argv[1:], os.environ.get(\"X\"))'),"
             " {'X': 'y'}), ('--mode', 'catnap'))",
             str(REPO_ROOT / "src")], capture_output=True, text=True)
        check("switching becomes the other copy, arguments and all",
              out.stdout.strip() == "['--mode', 'catnap'] y", out.stdout + out.stderr)

        calls = []
        real_exec, real_find = U.exec_into, U.find_checkout
        U.exec_into = lambda plan, args=(): calls.append((plan.folder, args))
        # Only "what is running" is faked; every other lookup stays real.
        U.find_checkout = lambda start=None: here if start is None else real_find(start)
        try:
            gui_app._open_default_version(["--mode", "catnap"])
            check("with no default, meanap-gui opens itself", calls == [], calls)
            set_default_version("v1.1.0")
            gui_app._open_default_version(["--mode", "catnap"])
            check("with one, it switches, passing its arguments on",
                  calls == [(U.release_dir("v1.1.0"), ("--mode", "catnap"))], calls)
            check("--here is an option", gui_app._parse_args(["--here"]).here)
        finally:
            U.exec_into, U.find_checkout = real_exec, real_find

        set_default_version(None)
        dlg = VersionsDialog(checkout=here)
        dlg.set_status(U.check(here, fetch=False))
        rows = {dlg._list.item(i).data(0x0100): i for i in range(dlg._list.count())}
        check("no star without a default",
              not any("default" in dlg._list.item(i).text() for i in rows.values()))
        check("…and the dialog says what happens instead",
              "No default" in dlg._default_label.text(), dlg._default_label.text())
        dlg._list.setCurrentRow(rows["v1.0.0"])
        check("a MATLAB release cannot be made the default",
              not dlg._default_button.isEnabled())
        dlg._list.setCurrentRow(rows["v1.1.0"])
        check("a Python one can", dlg._default_button.isEnabled())
        dlg._on_set_default()
        check("Set as default stores it", default_version() == "v1.1.0",
              default_version())
        check("…stars it", "★ default" in dlg._list.item(rows["v1.1.0"]).text(),
              dlg._list.item(rows["v1.1.0"]).text())
        check("…and the button has nothing more to do",
              not dlg._default_button.isEnabled())
        launched = []
        real_launch = U.launch
        U.launch = lambda plan, args=(): launched.append(plan.folder)
        try:
            dlg._launch_folder(user, CUTTING_EDGE)
            check("opening a version makes it the default",
                  launched == [user] and default_version() == "main",
                  (launched, default_version()))
            check("…and moves the star",
                  "★ default" in dlg._list.item(rows[CUTTING_EDGE]).text()
                  and "★" not in dlg._list.item(rows["v1.1.0"]).text())
            U.launch = lambda plan, args=(): launched.append(plan.folder)
            dlg._launch_folder(U.release_dir("v1.0.0"), "v1.0.0")
            check("opening a MATLAB release leaves the default alone",
                  default_version() == "main", default_version())
        finally:
            U.launch = real_launch
            set_default_version(None)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED:\n  " + "\n  ".join(FAILURES))
        return 1
    print("All update checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
