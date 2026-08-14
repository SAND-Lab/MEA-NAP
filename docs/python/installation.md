# Installation

The Python port requires **Python 3.11 or later** (the repository itself is
pinned to 3.13 via `.python-version`) and is installed straight from a clone
of the MEA-NAP repository — it isn't on PyPI yet.

```bash
git clone https://github.com/SAND-Lab/MEA-NAP.git
cd MEA-NAP
```

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

::::{tab-set}

:::{tab-item} uv (recommended)
[uv](https://docs.astral.sh/uv/) manages the virtual environment and the
lockfile (`uv.lock`) for you, so every contributor gets identical dependency
versions.

Install uv if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then, from the repository root:

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
If you'd rather manage your own virtual environment:

```bash
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

## Optional: OASIS deconvolution (CAT-NAP)

The calcium-imaging denoising pipeline ([CAT-NAP](catnap.md)) uses
[OASIS](https://github.com/j-friedrich/OASIS) deconvolution when available. It
isn't on PyPI, so it's not installed by default — without it, denoising falls
back to Savitzky-Golay smoothing (noted with a warning in the CAT-NAP tab).
To install it:

```bash
uv run pip install git+https://github.com/j-friedrich/OASIS.git
```

OASIS is built from source, so on macOS it needs the toolchain from
[macOS prerequisites](#macos-prerequisites) above.

## Verifying your install

The fastest sanity check is the GUI's own **🧪 Test pipeline** button — it
downloads a small bundled example dataset and runs the full 4-step pipeline
against it. See [Quickstart](quickstart.md) for the walkthrough.

If you'd rather verify from the command line first:

```bash
uv run python -c "import meanap; print(meanap.__version__)"
uv run pytest
```

## Adding dependencies (contributors)

```bash
uv add <package>          # runtime dependency
uv add --dev <package>    # dev-only (pytest, ruff, ...)
```

Both commands update `pyproject.toml` and `uv.lock` automatically — don't
edit either file by hand.
