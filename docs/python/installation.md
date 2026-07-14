# Installation

The Python port requires **Python 3.11 or later** (the repository itself is
pinned to 3.13 via `.python-version`) and is installed straight from a clone
of the MEA-NAP repository — it isn't on PyPI yet.

```bash
git clone https://github.com/SAND-Lab/MEA-NAP.git
cd MEA-NAP
```

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
