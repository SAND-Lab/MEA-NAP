# Desktop app plan (Windows + macOS)

Goal: someone who has never opened a terminal downloads one file, double-clicks
it, and gets the MEA-NAP GUI. Today's route — git clone, `uv sync`,
`uv run meanap-gui` — stays for everyone else and is unchanged by this work.

## Decisions (2026-10-21)

| Question | Decision |
|---|---|
| Approach | **Frozen app** (PyInstaller, one-folder build): Python and every dependency inside. No network needed to install or run. |
| Platforms | **Windows x64** and **macOS Apple silicon** (arm64). Not Intel Mac, not Linux (Linux users manage with uv). |
| Signing | **Unsigned for now.** Docs and the release page explain the Gatekeeper / SmartScreen bypass step by step. Signing can come later without changing the build. |
| Extras inside | **OASIS** (CAT-NAP denoising; without it results silently differ) and **spike sorting** (SpikeInterface + MountainSort5 + hdbscan). |
| Left out | CAT-NAP **cell tracking** (needs `roicat` → PyTorch, not a declared dependency); **Kilosort**; **launching MATLAB / old MATLAB-only releases**; switching between versions in place. |
| Distribution | `.dmg` (macOS) and a setup `.exe` (Windows, Inno Setup), built by GitHub Actions on each **official** release tag (and on demand) and attached to the GitHub release. Not on every dev build: hundreds of MB per merge. |
| Updates | The app checks GitHub's releases (public repo, no git, no login) and offers a link to download the newer one. |

## What has to change in the code

A frozen app has no git checkout, no `python` executable, no source tree around
the package and, on Windows, no console. Each of these breaks something today:

1. **Entry point.** One script (`packaging/meanap_app.py`) that calls
   `multiprocessing.freeze_support()` (step-1/4 workers use `spawn`) and then
   starts the GUI.
2. **`sys.executable -m …` re-entry.** `updates.launch_plan` and the CAT-NAP
   tracking runner start child Pythons this way; frozen, `sys.executable` is the
   app itself. Add a `--run-module <name>` dispatch to the entry point and a
   helper that builds the right argv either way.
3. **Version + build info.** `version.txt` / `versions.json` are bundled beside
   the package (as the wheel already does). `build_info()` reads git; bake a
   `_build_info.json` at build time instead.
4. **Repo-relative resources.** Step-4 schematics load `matlab/Images/*.png` via
   `Path(__file__).parents[3]`; bundle those images and look them up in the
   frozen location too.
5. **No console (Windows).** `sys.stdout`/`sys.stderr` are `None` in a windowed
   build; route them to a log file in the user's data folder (also what to
   attach to a bug report).
6. **numba `cache=True`.** Turned out to need nothing: with no source file,
   numba caches in its own user-wide folder, keyed to the executable's stat
   (verified on the Linux build). `NUMBA_CACHE_DIR` would be *ignored* there.
7. **Versions dialog / update check.** In the app: show the running version,
   check GitHub releases over HTTPS, button to open the download page. Hide the
   git-only parts (update `main`, open/set-default a release, MATLAB).

## Phases

1. **Freeze-safe code** — items 1–7 above, each a no-op when run from a clone,
   with tests.
2. **PyInstaller spec + local Linux build.** PyInstaller isn't a cross-compiler,
   but a Linux build exercises the same freezing problems (hidden imports for
   numba / sklearn / statsmodels / spikeinterface, data files, spawn workers,
   numba cache). Add a headless `--smoke-test` to the app: import every
   pipeline, JIT the numba kernels, run the synthetic example through steps 1–4
   with 2 workers, check OASIS and the sorter import, render the GUI offscreen.
3. **CI** — `.github/workflows/desktop-app.yml`: matrix `macos-14` +
   `windows-latest`; `uv sync --extra oasis --extra sorting` + PyInstaller;
   run the smoke test *on the built app*; package `.dmg` / Inno Setup `.exe`;
   upload as workflow artifacts, and attach to the release on official tags.
4. **Docs + release** — "Download the app" at the top of `installation.md`
   with the Gatekeeper / SmartScreen steps; README link; version bump.

## Open questions / risks

- **Size.** ~700 MB installed; the compressed downloads are 126-159 MB. Trim later (exclude tests, unused Qt modules) if it hurts.
- **Slow start (reported on Windows, 2026-10-21).** Causes found: (a)
  PyInstaller's matplotlib runtime hook sets a *new temporary* `MPLCONFIGDIR`
  on every launch, so matplotlib re-scanned every system font each time the
  app, and every worker process, started; `frozen.prepare_runtime` now keeps a
  lasting one (Linux build: matplotlib import 1.4 s → 0.2 s). (b) The main
  window imports the whole pipeline (~2,750 modules, 255 native libraries, incl.
  numba's ~100 MB LLVM DLL), which Windows antivirus scans on first load; a
  splash screen now shows before those imports. `<app> --time-startup` prints a
  per-library breakdown, and CI runs it cold + warm on both OSes. If Windows is
  still slow, next candidates: defer numba (`null_models`, `sttc`) and
  spikeinterface until a run needs them.
- **Unsigned macOS + quarantine**: on recent macOS the bypass is System
  Settings → Privacy & Security → "Open Anyway". Must be tested on a real Mac.
- No macOS/Windows machine locally: real-device testing depends on the user.

## Status

- [x] Phase 1 — freeze-safe code (`meanap.frozen`, `updates.check_app`,
      `AppVersionDialog`, `_build_info.json`, bundled `matlab/Images`);
      `python/test_desktop_app.py`
- [x] Phase 2 — `packaging/` spec + `build_app.py`; Linux build (668 MB
      unpacked) passes `--smoke-test`: workers really spawn (7 app processes
      seen), numba caches, `--run-module` works
- [x] Phase 3 — CI (`.github/workflows/desktop-app.yml`, PR #165) builds both
      and their `--smoke-test` passes on macos-14 and windows-latest (4/4
      checks each); `.dmg` 159 MB, `Setup.exe` 126 MB; ~5-7 min per job.
      Fixes needed: `CXXFLAGS=-std=c++17` for isosplit6 on macOS, `PYTHONUTF8`
- [ ] Phase 4 — docs written (`installation.md` "The desktop app", README
      link); **merge only together with cutting the v1.13.0 release**, since
      they send people to the latest release's assets
- [ ] Try the CI-built apps on a real Mac and a real Windows PC (Gatekeeper /
      SmartScreen steps, first-launch time, a real dataset)
