# How long a run takes, and what it needs

This page answers the questions people ask before starting a big batch: *how
long will it take*, *will my computer cope*, and *would a faster computer
help*. The last section explains why MEA-NAP is written in Python, and why
rewriting it in a "faster" language like C would not make it meaningfully
faster.

```{admonition} The short version
:class: tip
- A typical recording (64 electrodes, 10 minutes) takes **about 40 seconds**
  on a 16-core computer and **about 2 minutes** on a single core. The original
  MATLAB pipeline takes about 7 minutes per recording on the same machine.
- **16 GB of RAM** is enough for typical recordings. Plan on roughly
  **up to 3 GB for every recording step 4 works on at once**, plus room for
  the recording being spike-detected.
- More cores help spike detection a lot (about 7× from 1 to 16 cores), and
  help step 4 only when there are **at least as many recordings as cores**.
- **Express mode** removes most of the remaining time on a large machine. It
  skips the figures and keeps every number.
```

## Expected run times

All numbers on this page come from the bundled example dataset run end to
end (steps 1–4):

- 2 recordings, 64 electrodes each (Axion), 10 minutes at 12.5 kHz;
- 3 STTC lags (10, 25, 50 ms) and 200 thresholding shuffles, the defaults;
- either every figure drawn (**full**) or [express mode](express-mode.md).

The computer was a 16-core AMD Ryzen AI Max+ 395 with 110 GB of RAM, running
Linux and MEA-NAP 1.18. To mimic smaller computers, each run was restricted
to the first *N* cores.

| Cores | Step 1 (spikes) | Step 2 (activity) | Step 3 (connectivity) | Step 4 (networks) | **Full run** | **Express run** |
|---|---|---|---|---|---|---|
| 1  | 119 s | 7 s | 4 s | 100 s | **229 s** (3.8 min) | **161 s** |
| 2  | 107 s | 7 s | 3 s | 83 s  | **199 s** (3.3 min) | **135 s** |
| 4  | 44 s  | 7 s | 3 s | 58 s  | **112 s** (1.9 min) | **63 s**  |
| 8  | 27 s  | 7 s | 3 s | 55 s  | **91 s** (1.5 min)  | **42 s**  |
| 16 | 17 s  | 7 s | 2 s | 55 s  | **82 s** (1.4 min)  | **31 s**  |

### Compared with MATLAB, and with express mode

The same two recordings, the same settings and the same computer, using all
16 cores:

```{image} imgs/performance/matlab-vs-python-light.png
:alt: Run time of MATLAB (893 s), Python (82 s) and Python in express mode (31 s), split by step
:class: only-light
```

```{image} imgs/performance/matlab-vs-python-dark.png
:alt: Run time of MATLAB (893 s), Python (82 s) and Python in express mode (31 s), split by step
:class: only-dark
```

| | Step 1 | Step 2 | Step 3 | Step 4 | **Total** |
|---|---|---|---|---|---|
| MATLAB (R2025b, 16 workers) | 445 s | 62 s | 9 s | 377 s | **893 s** (14.9 min) |
| Python | 17 s | 7 s | 2 s | 55 s | **82 s** (11× faster) |
| Python, express mode | 16 s | 0 s | 3 s | 13 s | **31 s** (29× faster) |

Express mode computes exactly the same numbers. It saves its time in steps 2
and 4, which in a full run are mostly spent drawing figures.

### How the Python version got faster

The same run again, through each version of the Python port that changed its
speed. The dashed line is MATLAB.

```{image} imgs/performance/speedup-by-version-light.png
:alt: Run time of each Python version, falling from 1167 s in July 2026 to 82 s in version 1.18.0
:class: only-light
```

```{image} imgs/performance/speedup-by-version-dark.png
:alt: Run time of each Python version, falling from 1167 s in July 2026 to 82 s in version 1.18.0
:class: only-dark
```

| Version | What changed | Full run | Express mode |
|---|---|---|---|
| July 2026 | The first complete port | 1167 s | not yet available |
| July 2026 | Spike detection on threads, compiled null models, faster network plots | 350 s | not yet available |
| 1.14.1 | STTC computed once per electrode instead of once per pair; dense-network fixes | 236 s | 181 s |
| 1.15.0 | STTC across cores; NMF fits in parallel, stopping once enough variance is explained; null models in parallel | 126 s | 53 s |
| 1.15.1 | Faster file reading and wavelet filtering in spike detection | 82 s | 30 s |
| 1.18.0 (current) | No speed changes; new metrics and fixes | 82 s | 31 s |

From the first port to today, a full run is **14× faster** and an express
run is **38× faster**.

Each speed-up was checked to give the same results as the code it replaced,
so the time saved comes from doing the same work faster, not from doing less
of it. (Other changes between versions, such as bug fixes and new metrics,
mean the July and current outputs are not identical byte for byte.) How each change achieves that is
explained in [Why not rewrite MEA-NAP in C?](#why-not-rewrite-mea-nap-in-c)
below.

When each number was measured:

- July versions: on 9 July 2026.
- MATLAB and the 1.15.0 full run: back to back on 25 October.
- Everything else: on 29 October.

All were measured on this computer with these settings. Re-runs of the
October versions came within a few seconds of what was recorded at the
time. To redraw the figures, run
`python/plot_performance_figures.py`.

**For a batch, multiply per recording, then divide by how much runs at
once.** Eight copies of the same two recordings (8 recordings in total) took:

| Cores | Step 1 | Step 2 | Step 3 | Step 4 | **Full run** |
|---|---|---|---|---|---|
| 4  | 180 s | 21 s | 7 s | 161 s | **369 s** (6.2 min, 46 s per recording) |
| 16 | 68 s  | 21 s | 4 s | 95 s  | **188 s** (3.1 min, 23 s per recording) |

So a plate of 24 similar recordings is roughly 10 minutes on a 16-core
desktop and 20 minutes on a 4-core laptop.

These are measurements on one machine. Your computer can be faster or slower
per core, so use them to estimate the order of magnitude, not to predict to
the second. To see what *your* computer will do, open **🖥 This computer** in
the toolbar of the desktop app. It lists the cores and free memory MEA-NAP
can see, how many recordings each step will run at once, and anything holding
the run back. It also runs a short benchmark that scores the machine.

### What makes a run longer

| What you change | Which step | How the time grows |
|---|---|---|
| Longer recordings, higher sampling rate, more electrodes | 1 | In proportion to the total number of samples |
| More electrodes or units (nodes) | 3, 4 | Faster than proportional: connectivity compares every *pair* of nodes |
| More spikes | 3 | In proportion: STTC walks every spike of every pair |
| More STTC lags | 3, 4 | One full pass of each per lag |
| More shuffles (`prob_thresh_rep_num`) | 3 | In proportion: each shuffle recomputes the whole matrix |
| Denser networks (long lags, loose thresholds) | 4 | Faster than proportional: several graph measures slow down sharply near full density |
| Drawing figures | 2, 4 | Most of step 4 in a full run: about 43 of its 55 s here |

Two examples at the larger end:

- **Spike-sorted data with hundreds of units.** A 306-unit MaxOne recording
  (2 minutes long) takes about 8 minutes for steps 1–4, mostly in steps 3 and
  4. See [Importing sorted data](sorted-import.md).
- **Calcium imaging with a long lag.** A 270-cell suite2p recording at a
  1000 ms lag takes about 3 minutes, because such a long window leaves the
  network almost fully connected. A shorter lag is both faster and more
  informative. See [CAT-NAP](catnap.md).

## How it uses more cores

Each step uses cores differently, which explains the pattern in the table
above:

**Step 1, spike detection: threads over electrodes.** One recording is loaded
at a time, and its electrodes are split across cores. This step benefits most
from cores: 119 s on one core, 17 s on sixteen. It stops improving once every
electrode has its own core, and in practice somewhat before that, because the
cores also compete for memory bandwidth.

**Step 2, neuronal activity: one core.** It is already fast (about 3 s per
recording), and in a full run most of that is drawing figures.

**Step 3, functional connectivity: recordings in parallel, pairs across
cores.** Recordings run side by side, and within each one the pair-by-pair
STTC calculation is spread across the cores. For 64 electrodes
it takes only a couple of seconds either way. For hundreds of sorted units,
the cores are what make it practical (about 10× faster on 16 cores).

**Step 4, network metrics and figures: one recording per core.** Recordings
are processed in parallel, each in its own worker process. Two consequences:

- With **2 recordings**, step 4 cannot use more than 2 cores' worth of
  recording-level parallelism. That is why it stops at 55 s above 4 cores in
  the first table.
- With **8 recordings**, going from 4 to 16 cores cut step 4 from 161 s to
  95 s.

A batch also can't finish before its largest single recording does.

**MEA-NAP leaves one core free** so the computer stays responsive, which is
why 2 cores is barely faster than 1 for spike detection: both run on a single
detection thread. It counts *physical* cores, not hyper-threads, because the
work is limited by memory bandwidth as much as by arithmetic, and two
hyper-threads share both.

To set the number of recordings processed at once yourself (for example on a
shared server), use `meanap run --workers N` on the
[command line](command-line.md), or set `recording_workers` (and
`spike_detection_channel_workers` for step 1) in a saved parameter file.
Leaving them empty lets MEA-NAP decide.

More cores are not the only way to go faster:

- [Express mode](express-mode.md) skips the figures and keeps every number
  (identical to a full run). Any figure can be redrawn later from the
  `.meanap` bundle. On 16 cores it cut the run from 82 s to 31 s.
- [Sharing a run](shared-run.md) splits one batch across several computers.
- Switching off the two dimensionality metrics (`compute_nmf`,
  `compute_eff_rank`) removes most of step 4's computation, if you don't need
  them.

## How much memory it needs

Peak memory use (all MEA-NAP processes together) on the example dataset:

| Cores | During step 1 | During step 4, 2 recordings | During step 4, 8 recordings |
|---|---|---|---|
| 1  | 5.7 GB  | 3.6 GB | |
| 4  | 4.1 GB  | 6.9 GB | 10.2 GB |
| 8  | 6.7 GB  | 7.2 GB | |
| 16 | 11.6 GB | 7.6 GB | about 18 GB |

Steps 2 and 3 never exceeded 4 GB.

Two things decide the peak:

**Step 1 holds one whole recording in memory**, plus a working copy of one
electrode per detection thread:

- The recording costs 4 bytes per sample per electrode: 1.9 GB for 64
  electrodes × 10 minutes × 12.5 kHz.
- Each thread adds about 0.6 GB for a recording of this length, and that
  grows with the number of samples per electrode.

That is why 16 cores use more memory than 8 here. On one or two cores the
file is read in a slower way that briefly needs a second, double-precision
copy, which is why 1 core uses more than 4.

**Step 4 holds up to about 3 GB per recording in progress**, and runs as many
at once as it has cores (minus one). Eight at once peaked at about 18 GB.

As a rule of thumb, for 64-electrode recordings of about 10 minutes:

| RAM | What to expect |
|---|---|
| 8 GB  | Works, but use few workers (`--workers 2`) and close other applications |
| 16 GB | Comfortable on a 4–8 core laptop; on 8 cores with many recordings, `--workers 4` avoids swapping |
| 32 GB or more | No constraints for typical data |

Longer or higher-rate recordings scale step 1's figures in proportion. A
30-minute recording at 25 kHz has 6× the samples of the example, so expect
roughly 6× its step-1 memory. If memory is tight, the advice in
[System requirements](../system-requirements.rst) still applies: shorten or
downsample long recordings.

```{admonition} Running out of memory looks like a slow computer
:class: warning
When a computer runs out of RAM it starts using the disk as memory
("swapping"), which can make a run ten or a hundred times slower without
any error message. If a run is much slower than the tables above suggest,
open **🖥 This computer** or your system's activity monitor. If memory is
full, lower the number of workers.
```

## Why not rewrite MEA-NAP in C?

People often assume that Python is slow and C is fast, so rewriting the
pipeline in C (or C++, Rust, Fortran) would make it much faster. For MEA-NAP
that is mostly not true. There are three reasons.

### 1. The heavy lifting already runs as compiled code

Python is an *interpreted* language: a program reads your code one
instruction at a time and carries it out. That is flexible but slow, often
10–100× slower than compiled code for tight loops of arithmetic. The way
around this, which almost all scientific Python uses, is to keep the
interpreter for the "glue" (reading settings, deciding what to do next,
looping over recordings) and to hand every large calculation to code that was
compiled to machine instructions beforehand:

| Part of MEA-NAP | Runs in |
|---|---|
| Filtering, wavelet convolution, medians (step 1) | numpy / SciPy, written in C and Fortran |
| Decompressing `.mat` files | zlib, written in C |
| Matrix factorisation (NMF), linear algebra | scikit-learn (Cython, compiled to C) and BLAS/LAPACK (C, Fortran, assembly) |
| STTC, null-model rewiring (steps 3–4) | MEA-NAP's own loops, compiled by **numba** (below) |
| Rasterising figures to pixels | matplotlib's Agg renderer, written in C++ |

We profiled a full single-core run of the example dataset.

- **About 60% of the time was spent inside compiled code** like this. The
  profiler counts 43% directly. The rest it books to the Python function
  that made the call: h5py's decompression, scikit-learn's NMF solver, the
  numba kernels, and numpy arithmetic written as `a * b`.
- **At most about 40% was Python being interpreted.** More than half of that
  was matplotlib working out figure layouts. Only about 6% was MEA-NAP's own
  Python code.

Rewriting MEA-NAP in C could only save part of that 40%, and most of it is
plotting code that a rewrite would have to replace (see below).

### 2. numba compiles Python loops to the same machine code a C compiler would

Some calculations don't fit a ready-made numpy function. STTC, for instance,
walks two spike trains side by side looking for coincidences. Written as a
plain Python loop, that would be very slow, so MEA-NAP compiles these loops
with **numba**. A function marked `@njit` goes through these stages:

1. **On the first call, numba reads the function's Python bytecode** and
   works out the type of every variable from the arguments it was given (an
   array of 64-bit floats, a 64-bit integer, …). Python itself never needs to
   know these types; numba needs them to generate fast code.
2. **It translates the function into LLVM IR.** LLVM is the compiler toolkit
   behind clang (a widely used C/C++ compiler), Rust and Swift. Its IR is a
   low-level, CPU-independent description of the program, close to assembly.
3. **LLVM optimises the IR and emits machine code for your exact CPU.** This
   is the same optimiser clang uses on C code: register allocation, loop
   unrolling, vector instructions.
4. **The machine code is cached on disk** (`cache=True`), so later runs skip
   compilation. Calls from Python go straight to it.

Two further options matter for MEA-NAP:

- `nogil=True` lets the compiled code run on several threads at once.
  Normally Python's global interpreter lock (GIL) allows only one thread to
  run Python code at a time.
- `parallel=True` with `prange` spreads a loop's iterations across all
  cores.

The cost is that numba understands only a subset of Python: numbers, numpy
arrays and simple loops, not arbitrary Python objects. That is why it is
applied to a handful of hot loops rather than to the whole program.

To check that claim, we ran the same STTC calculation four ways. The
calculation was 64 electrodes (2016 pairs, 175 000 spikes), and the C version
was a line-by-line hand translation compiled with `gcc -O3`. Each version was
pinned to a fixed set of cores:

| Version | Time | vs. numba, 1 core |
|---|---|---|
| Plain Python (no numba) | 1128 ms | 14× slower |
| **numba, 1 core** (as shipped) | **82 ms** | — |
| Hand-written C, 1 core | 73 ms | 11% faster |
| numba, 16 cores (as shipped) | 7.4 ms | 11× faster |

All four produced bit-for-bit identical results. At 300 units the picture
was the same:

| Version (300 units) | Time |
|---|---|
| numba, 1 core | 1775 ms |
| Hand-written C, 1 core | 1576 ms |
| numba, 16 cores | 158 ms |

What the experiment shows:

- **Compiling is what matters, and numba already does it.** Plain Python to
  compiled code is a 14× step. Going from numba to C gains about 11%. Part of
  that gap is a safety check numba adds on each array access (Python allows
  negative indices like `a[-1]`, and the compiled code has to allow for them).
  A C programmer would skip that check, and so could we, at the cost of a
  less safe program.
- **Using the cores is worth far more than the language.** Spreading the loop
  over 16 cores was worth 11×. With numba that takes `parallel=True` and
  writing `prange` instead of `range`.
- **"C" isn't a single speed.** Compiling the same C with `-march=native`
  changed results by about one part in 10¹⁶. The compiler was then allowed to
  fuse a multiply and an add into a single CPU instruction, which rounds
  differently. Compiler flags shift both speed and the last bits of the
  answer. numba does not take that liberty unless asked to (`fastmath`),
  which is one reason its results match the reference exactly.

### 3. The big speed-ups came from doing less work, not faster instructions

MEA-NAP's Python port went from 25% *slower* than MATLAB to 7–11× faster.
Almost none of that came from a faster language:

- **Better algorithms.** One STTC quantity was recomputed for every *pair* of
  electrodes when it depends on only one electrode. Computing it once per
  electrode made step 3 4× faster at 64 electrodes. A pure-Python shortest-path
  search running once per node was replaced, making local efficiency 18×
  faster. Two rewrites of the null-model loop, one of which picks a few random
  ranks without sorting the whole edge list, made the null models 5× faster. A C rewrite of the old algorithms would have kept all of these
  costs.
- **Using the cores.** Electrodes in step 1, recordings in step 4, pairs in
  step 3.
- **Drawing less, and drawing it more cleverly.** Drawing all of a network
  plot's edges as one object instead of hundreds of separate lines made the
  figure stage 4× faster. Express mode skips the figures altogether.

Steps 2 and 4 of a full run are now mostly figures. A C rewrite would only
help there by replacing matplotlib, the standard and well-tested plotting
library, with a hand-written renderer.

Against an 11% best case, a rewrite would cost:

- the scientific Python libraries MEA-NAP is built on (SciPy's filters,
  scikit-learn's NMF, matplotlib's figures), each of which would have to be
  rewritten or bound to by hand;
- code that neuroscientists can read and change;
- the cross-platform desktop app, which today ships one codebase to Windows,
  macOS and Linux;
- the parity tests that pin every step to MATLAB's output, which would all
  have to be re-established.

If a part of MEA-NAP ever is too slow, the remedy is the one used so far:

1. measure where the time goes;
2. look for a better algorithm or less work;
3. use the cores;
4. compile the remaining hot loop with numba.

That last step already gets within about 10% of C.

```{admonition} For contributors
:class: seealso
The engineering log behind these numbers — every optimisation, what it
changed, and how each was checked to give identical results — is in the
"MATLAB vs Python speed comparison" section of
[`python/PIPELINE_PORT_STATUS.md`](https://github.com/SAND-Lab/MEA-NAP/blob/main/python/PIPELINE_PORT_STATUS.md).
```
