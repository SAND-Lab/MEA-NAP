# Installation

The Python port requires **Python 3.11 or later** (the repository itself is
pinned to 3.13 via `.python-version`) and is installed straight from a clone
of the MEA-NAP repository — it isn't on PyPI yet.

```bash
git clone https://github.com/SAND-Lab/MEA-NAP.git
cd MEA-NAP
```

That `cd` matters: every install command on this page is run from inside the
`MEA-NAP` folder, not from the folder you cloned it into and not from one of
its subfolders. If you downloaded a ZIP from GitHub instead of cloning, the
folder is called `MEA-NAP-main` — use `cd MEA-NAP-main`.

## macOS prerequisites

On macOS some dependencies have no pre-built wheel for your Python version or
chip and are compiled from source during the install, which needs a C/C++
toolchain that macOS doesn't ship by default. Install these **before** running
`uv sync` / `pip install -e .`:

1. **Homebrew** — the package manager used to get the other two
   ([brew.sh](https://brew.sh)):

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   Follow the "Next steps" it prints at the end — on Apple Silicon it asks you
   to add `/opt/homebrew/bin` to your `PATH` before `brew` is usable.

2. **CMake** — the build system several source packages use:

   ```bash
   brew install cmake
   ```

3. **LLVM** — provides `clang` and the OpenMP runtime that Apple's stock
   command line tools leave out:

   ```bash
   brew install llvm
   ```

   `brew info llvm` prints the exact `export` lines for your machine; on Apple
   Silicon they look like this, and are worth adding to `~/.zshrc`:

   ```bash
   export PATH="/opt/homebrew/opt/llvm/bin:$PATH"
   export CC="/opt/homebrew/opt/llvm/bin/clang"
   export CXX="/opt/homebrew/opt/llvm/bin/clang++"
   export LDFLAGS="-L/opt/homebrew/opt/llvm/lib"
   export CPPFLAGS="-I/opt/homebrew/opt/llvm/include"
   ```

You may also be prompted to install Apple's Command Line Tools
(`xcode-select --install`) — accept it if so.

If a fresh install fails with `error: command 'cmake' not found`, `clang: error:
unsupported option '-fopenmp'`, or a long `Building wheel for ... did not run
successfully` traceback, it's almost always one of the three above missing.

Install with either uv or pip — **from the `MEA-NAP` folder** you changed into
above. If you have opened a new terminal since then, `cd` back into it first.

::::{tab-set}

:::{tab-item} uv (recommended)
[uv](https://docs.astral.sh/uv/) manages the virtual environment and the
lockfile (`uv.lock`) for you, so every contributor gets identical dependency
versions.

Install uv if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from the `MEA-NAP` folder:

```bash
uv sync
```

This creates a `.venv/` and installs every dependency pinned in `uv.lock`. You
don't need to activate the environment — prefix commands with `uv run`:

```bash
uv run meanap-gui
```
:::

:::{tab-item} pip / venv
If you'd rather manage your own virtual environment — again from the
`MEA-NAP` folder:

```bash
cd /path/to/MEA-NAP
python3 -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e .
```

This installs `meanap` in editable mode using the dependencies declared in
`pyproject.toml`. Launch the GUI the same way as any installed console script:

```bash
meanap-gui
```
:::

::::

:::{admonition} "No `pyproject.toml` found" / "Neither 'setup.py' nor 'pyproject.toml' found"
:class: tip
Both errors mean the same thing: the command ran in the wrong directory. Run
`pwd` — the path should end in `/MEA-NAP` — and `ls`, which should list
`pyproject.toml` next to the `src/`, `python/` and `docs/` folders. If you are
inside `python/`, run `cd ..` and try again.
:::

## Optional: OASIS deconvolution (CAT-NAP)

The calcium-imaging denoising pipeline ([CAT-NAP](catnap.md)) deconvolves each
trace with [OASIS](https://github.com/j-friedrich/OASIS). It is optional, and
left out of the default install because it is a compiled extension. Run this
from the `MEA-NAP` folder, the same one you installed from:

```bash
cd /path/to/MEA-NAP
uv sync --extra oasis
```

Prebuilt wheels cover CPython 3.9–3.13 on Linux, macOS (Apple silicon) and
Windows, so no compiler is needed on those. Anywhere else it builds from
source, which on macOS needs the toolchain from
[macOS prerequisites](#macos-prerequisites) above.

Install it **before** your first CAT-NAP run. Without it, denoising falls back
to Savitzky-Golay smoothing — that is not a slower route to the same answer,
it is a different peak train and therefore different adjacency matrices. The
CAT-NAP tab warns when it is missing, and:

```bash
uv run python -c "from meanap.catnap.denoising import oasis_available; print(oasis_available())"
```

Note that denoising output is cached as `Fdenoised.npy` and carries no record
of which method produced it, so installing OASIS after a run will not
recompute anything — tick **Redo denoising** to force it.

## Verifying your install

The fastest sanity check is the GUI's own **🧪 Test pipeline** button — it
downloads a small bundled example dataset and runs the full 4-step pipeline
against it. See [Quickstart](quickstart.md) for the walkthrough.

If you'd rather verify from the command line first:

```bash
uv run python -c "import meanap; print(meanap.__version__)"
uv run pytest
```

Note `meanap.__version__` is the *Python package* version from
`pyproject.toml`, which is not the same thing as the pipeline versions below —
use `meanap.version.all_versions()` for those.

## Adding dependencies (contributors)

```bash
uv add <package>          # runtime dependency
uv add --dev <package>    # dev-only (pytest, ruff, ...)
```

Both commands update `pyproject.toml` and `uv.lock` automatically — don't
edit either file by hand.

## Version numbers

Three pipelines ship from this repository and move at different speeds, so each
carries its own version:

| pipeline | version lives in | why |
|---|---|---|
| MEA-NAP | `version.txt` | unchanged since the MATLAB release; MATLAB reads it and the update check compares it against GitHub |
| CAT-NAP | `versions.json` | newer subsystem, no MATLAB release history |
| MEA-Stim | `versions.json` | same |

MEA-NAP's number is deliberately **not** duplicated into `versions.json`: it is
the one users are told to check, and two copies could disagree.

Every run records the version of the pipeline that produced it — as the first
line of the run log, under `_meanap` in `params.json`, and in a bundle's
`manifest.json`. The GUI shows the running mode's version beside the Mode
selector, with all three in its tooltip.

```bash
uv run python -c "from meanap.version import all_versions; print(all_versions())"
```
