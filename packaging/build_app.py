"""Build the MEA-NAP desktop app for the platform this runs on.

    uv sync --extra oasis --extra sorting --group app
    uv run python packaging/build_app.py            # → packaging/dist/MEA-NAP[.app]
    uv run python packaging/build_app.py --smoke    # … then run the app's self-check

PyInstaller does not cross-compile: the macOS app is built on a Mac, the
Windows one on Windows (CI does both; see .github/workflows/desktop-app.yml).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
DIST = HERE / "dist"


def write_build_info() -> dict:
    """Record the exact commit, since the app has no git to ask later."""
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                              text=True, check=True).stdout.strip()

    try:
        describe = git("describe", "--tags", "--match", "v[0-9]*", "--always", "--dirty")
        info = {"describe": describe, "commit": git("rev-parse", "HEAD"),
                "dirty": describe.endswith("-dirty")}
    except (OSError, subprocess.CalledProcessError):
        info = {}
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "_build_info.json").write_text(json.dumps(info))
    return info


def app_executable() -> Path:
    if sys.platform == "darwin":
        return DIST / "MEA-NAP.app" / "Contents" / "MacOS" / "MEA-NAP"
    return DIST / "MEA-NAP" / ("MEA-NAP.exe" if sys.platform == "win32" else "MEA-NAP")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--smoke", action="store_true",
                        help="run the built app's --smoke-test afterwards")
    args = parser.parse_args()

    subprocess.run([sys.executable, str(HERE / "make_icons.py")], check=True)
    print("build info:", write_build_info())
    subprocess.run([sys.executable, "-m", "PyInstaller", str(HERE / "meanap.spec"),
                    "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller")],
                   check=True)
    exe = app_executable()
    print(f"built {exe}")
    if args.smoke:
        return subprocess.run([str(exe), "--smoke-test"]).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
