# Installation

There are two ways to get the Python version of MEA-NAP:

- **The desktop app** — download one file, double-click, done. No Python, no
  terminal. For Windows and Macs (Apple silicon or Intel).
- **From the source code** — a clone of the repository and a few commands in a
  terminal. For Linux, for the newest code between releases, and for anyone
  who wants to change MEA-NAP itself.

Both run the same pipeline with the same pinned libraries, so they give the
same results.

## The desktop app (easiest)

Click the download for your computer. It always gets the newest release.

| Your computer | Download |
|---|---|
| Windows 10 or 11 (64-bit) | [**⬇ MEA-NAP for Windows**](https://github.com/SAND-Lab/MEA-NAP/releases/latest/download/MEA-NAP-Windows-x64-Setup.exe) |
| Mac with Apple silicon (M1, M2, M3, M4 …) | [**⬇ MEA-NAP for Mac (Apple silicon)**](https://github.com/SAND-Lab/MEA-NAP/releases/latest/download/MEA-NAP-macOS-AppleSilicon.dmg) |
| Mac with an Intel processor | [**⬇ MEA-NAP for Mac (Intel)**](https://github.com/SAND-Lab/MEA-NAP/releases/latest/download/MEA-NAP-macOS-Intel.dmg) |

What changed in each version, and older versions, are on the
[releases page](https://github.com/SAND-Lab/MEA-NAP/releases).

Not sure which Mac you have? Apple menu → **About This Mac**: "Chip: Apple M…"
means Apple silicon; "Processor: … Intel …" means an Intel Mac. Either needs
macOS 12 (Monterey) or later.

The download is 130–180 MB (about 700 MB once installed): it carries its own Python
and every library MEA-NAP uses, including OASIS for CAT-NAP and the spike
sorters.

**If your browser warns about the download.** Chrome in particular may say
the file is *suspicious*, *dangerous* or *not commonly downloaded*, and hold it
back. It says this about any program that isn't signed with a paid
certificate and that few people have downloaded yet — and each new release
starts that count again. To keep the file in Chrome:

1. Open the downloads list: the download icon at the top right, or
   **Ctrl+J** (Windows) / **⌘+Shift+J** (Mac).
2. Find the MEA-NAP file and choose **Keep** (or **Download suspicious
   file**).
3. Confirm with **Keep anyway** (or **Download anyway**).

In Edge, it's the **…** beside the download → **Keep** → **Show more** →
**Keep anyway**. Only download MEA-NAP from the
[GitHub releases page](https://github.com/SAND-Lab/MEA-NAP/releases) — that is
what makes it safe to click through.

### Installing on Windows

1. Double-click `MEA-NAP-Windows-x64-Setup.exe`.
2. Windows may show **"Windows protected your PC"**. This appears for any
   app that is not yet signed with a paid certificate. Click
   **More info**, then **Run anyway**.
3. Click through the installer. It installs for your user only and doesn't
   need administrator rights. Tick **Create a desktop shortcut** if you want one.
4. Start MEA-NAP from the Start menu (or the desktop shortcut).

To update, download the newer installer and run it: it replaces the old
version and keeps your settings. To uninstall: **Settings → Apps → Installed
apps → MEA-NAP → Uninstall**.

### Installing on a Mac

1. Double-click the `MEA-NAP-macOS-….dmg` you downloaded, then drag **MEA-NAP** onto
   the **Applications** folder in the window that opens.
2. Open MEA-NAP from Applications (or Launchpad). The first time, macOS says
   it **"could not verify MEA-NAP is free of malware"** (older macOS: "cannot
   be opened because the developer cannot be verified"). This appears for any
   app that is not yet notarised by Apple. Click **Done**.
3. Open **System Settings → Privacy & Security**, scroll down to the line
   about MEA-NAP, and click **Open Anyway**. Enter your password if asked,
   then **Open**.

   On macOS 14 (Sonoma) or earlier you can instead right-click (or
   Control-click) MEA-NAP in Applications and choose **Open**, then **Open**
   again.
4. From then on MEA-NAP opens normally.

To update, download the newer `.dmg` and drag MEA-NAP into Applications
again, replacing the old one. To uninstall, drag MEA-NAP from Applications to
the Bin.

If macOS instead says MEA-NAP **"is damaged and can't be opened"**, the
download was quarantined in a way step 3 doesn't clear. Open **Terminal**
(Applications → Utilities), paste this line, press Return, and open MEA-NAP
again:

```bash
xattr -dr com.apple.quarantine /Applications/MEA-NAP.app
```

### Good to know

**The first analysis is slower than later ones.** Parts of step 4 are compiled
for your processor the first time they run, and the result is kept for next
time. On Windows, antivirus software may also scan the app the first time it
starts, so the window can take a minute to appear.

**Updates.** The version number in the toolbar, beside the **Mode**
selector, shows **⬆ update** when a newer release is out. Click it, then
**Download**.

**What the app doesn't include.** Running MATLAB or switching between
MEA-NAP versions from inside the GUI, CAT-NAP's cell tracking across days
(which needs PyTorch), and Kilosort. Use a source install for those.

**Something went wrong?** The app writes everything it would have printed to
a log file. Please attach it when you
[report a problem](https://github.com/SAND-Lab/MEA-NAP/issues):

- Windows: `%LOCALAPPDATA%\MEA-NAP\logs\meanap.log` (paste that into the
  File Explorer address bar)
- macOS: `~/Library/Logs/MEA-NAP/meanap.log` (Finder → Go → Go to Folder…)

The log of the run before is kept beside it as `meanap.previous.log`.

## From the source code

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

### macOS prerequisites

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

### Installing

Install with either uv or pip — **from the `MEA-NAP` folder** you changed into
above. If you have opened a new terminal since then, `cd` back into it first.

#### With uv (recommended)

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

#### With pip / venv

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

The same install gives the `meanap` command, which runs a saved parameter
file without the GUI — see [Running from the command line](command-line.md).
On a machine with no screen, `meanap example` is a quick check that
everything works.

> **"No `pyproject.toml` found" / "Neither 'setup.py' nor 'pyproject.toml'
> found"?** Both errors mean the same thing: the command ran in the wrong
> directory. Run `pwd` — the path should end in `/MEA-NAP` — and `ls`, which
> should list `pyproject.toml` next to the `src/`, `python/` and `docs/`
> folders. If you are inside `python/`, run `cd ..` and try again.

### Optional: OASIS deconvolution (CAT-NAP)

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

### Optional: spike sorting

Step 1 can [sort spikes into units](spike-sorting.md) instead of detecting
them per electrode, so that each neuron — not each electrode — is a node of
the network. That needs [SpikeInterface](https://spikeinterface.readthedocs.io)
and a sorter, installed together as the `sorting` extra:

```bash
cd /path/to/MEA-NAP
uv sync --extra sorting
```

About 300 MB, pure CPU, no GPU or compiler needed. This is deliberately *not*
`spikeinterface[full]`, which pulls a multi-gigabyte CUDA build of PyTorch
onto machines with no GPU to use it. The Spike detection tab greys out the
**Sort spikes** option until this is installed, and:

```bash
uv run python -c "from meanap.pipeline.spike_sorting import installed_sorters; print(installed_sorters())"
```

should list `tridesclous2` and `mountainsort5`. Kilosort4 users can add
`kilosort` (and a CUDA PyTorch) themselves; it then appears in the same list.

### Verifying your install

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
