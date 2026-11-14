"""Every wavelet MATLAB MEA-NAP offers, against MATLAB itself.

    uv run python test_spike_detection_wavelets.py

``test_fixtures/wavelets_matlab_reference.npz`` holds MATLAB R2025b's
answers on a synthetic filtered trace (``make_wavelet_reference.m``): each
standard wavelet's ``intwave``, its legacy ``cwt``, ``determine_scales`` at
12.5/20/25 kHz and ``detectSpikesWavelet``'s spike frames at 25 and 12.5 kHz;
and for ``mea`` the template ``getTemplate`` finds and the wavelet
``adaptWavelet`` + ``pat2cwav`` make from it.

Two differences from MATLAB are expected and asserted as such:

* at 12.5 kHz one spike of bior1.5, bior1.3 and sym2 lands 2–3 samples away
  — ``_parse_spike_index``'s merging, which predates this and is fixed
  separately;
* ``mea``'s scales: MATLAB lets aliased narrow scales into its width table
  (or crashes when one lacks a zero crossing); the port leaves them out.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from meanap.pipeline import spike_detection as sd  # noqa: E402

REF = np.load(HERE / "test_fixtures" / "wavelets_matlab_reference.npz")
STANDARD = ("bior1.5", "bior1.3", "db2", "sym2", "haar")
#: (wavelet, kHz) whose spike frames differ from MATLAB's by one merged spike.
PARSE_DIFFERENCE = {("bior1.5", 12.5), ("bior1.3", 12.5), ("sym2", 12.5)}

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok or not detail else f"  — {detail}"))
    if not ok:
        fails.append(name)


def main() -> int:
    trace = REF["trace"].astype(float)
    scales = REF["scales"].astype(float)
    lo, hi = REF["cwt_window"]

    for wname in STANDARD:
        key = wname.replace(".", "p")
        print(wname)
        int_psi, _ = sd._intwave(wname)
        ref_psi = REF[f"{key}_psi"]
        check("intwave matches MATLAB's", int_psi.shape == ref_psi.shape
              and np.allclose(int_psi, ref_psi, rtol=0, atol=1e-11),
              f"max diff {np.max(np.abs(int_psi - ref_psi)) if int_psi.shape == ref_psi.shape else 'shape'}")
        got = sd._cwt(trace[:5000], scales, sd._intwave(wname))[:, lo:hi]
        ref = REF[f"{key}_cwt"]
        rel = np.max(np.abs(got - ref)) / np.max(np.abs(ref))
        check("cwt matches MATLAB's", rel < 1e-10, f"relative {rel:.1e}")
        for khz in (12.5, 20, 25):
            got = sd._determine_scales(wname, (0.4, 0.8), khz * 1000, 5)
            ref = REF[f"{key}_scales_{round(khz * 10)}"].astype(float)
            check(f"scales at {khz} kHz {np.round(got, 2).tolist()}", np.allclose(got, ref),
                  f"MATLAB {list(ref)}")
        for khz in (25, 12.5):
            got = sd.detect_spikes_wavelet(trace, khz * 1000, (0.4, 0.8), 5, "l", -0.12, wname)
            ref = REF[f"{key}_spikes_{round(khz * 10)}"].astype(int) - 1   # MATLAB is 1-based
            if (wname, khz) in PARSE_DIFFERENCE:
                ok = len(got) == len(ref) and np.sum(got != ref) == 1 \
                    and np.max(np.abs(got - ref)) <= 3
                check(f"spikes at {khz} kHz: MATLAB's but one merged 2-3 samples away",
                      ok, f"{len(got)} vs {len(ref)}")
            else:
                check(f"spikes at {khz} kHz identical to MATLAB's ({len(ref)})",
                      np.array_equal(got, ref), f"{len(got)} vs {len(ref)}")

    print("mea")
    template = sd.get_template(trace, 25000.0, multiplier=4.5, ref_period_ms=2.0, n_spikes=100)
    check("the template is MATLAB getTemplate's", template is not None
          and np.allclose(template, REF["gt_ave"], rtol=0, atol=1e-12))
    wavelet = sd.adapt_wavelet(REF["gt_ave"])
    check("the wavelet made from it is MATLAB's (adaptWavelet + pat2cwav)",
          np.allclose(wavelet[0], REF["mea_psi"], rtol=0, atol=1e-12))
    got = sd._cwt(trace[:5000], scales, wavelet)[:, lo:hi]
    rel = np.max(np.abs(got - REF["mea_cwt"])) / np.max(np.abs(REF["mea_cwt"]))
    check("its cwt matches MATLAB's", rel < 1e-10, f"relative {rel:.1e}")
    for khz in (10, 12.5, 25):
        got = sd._determine_scales("mea", (0.4, 0.8), khz * 1000, 5, wavelet)
        check(f"scales at {khz} kHz rise with width {got.tolist()}",
              len(got) == 5 and np.all(np.diff(got) >= 0) and got[0] > 2)
    spikes = sd.detect_spikes_wavelet(trace, 25000.0, wname="mea", template=REF["gt_ave"])
    planted = np.arange(200, len(trace) - 200, 1373) - 1
    found = sum(np.min(np.abs(spikes - p)) <= 10 for p in planted)
    check(f"mea finds the planted spikes ({found}/{len(planted)}, {len(spikes)} in all)",
          found >= 0.9 * len(planted))
    quiet = np.random.default_rng(0).standard_normal((20000, 1))
    params = sd.SpikeDetectionParams(fs=25000.0, wname_list=["mea"], thresholds=[],
                                     template_multiplier=8.0)
    result = sd.detect_spikes_recording(quiet, np.array([11]), 25000.0, params, max_workers=1)
    check("an electrode with too few spikes for a template gets none, not an error",
          sd.get_template(quiet[:, 0], 25000.0, multiplier=8.0) is None
          and len(result.spike_times[0]["mea"]) == 0)

    print("a recording")
    rng = np.random.default_rng(1)
    dat = rng.standard_normal((25000, 3)) * 5
    for k in range(300, 24700, 997):
        dat[k - 25:k + 26, :2] += np.interp(np.arange(51), np.arange(len(REF['gt_ave'])),
                                            REF["gt_ave"])[:, None]
    params = sd.SpikeDetectionParams(fs=25000.0, wname_list=list(sd.WAVELETS),
                                     thresholds=[], template_multiplier=4.5)
    result = sd.detect_spikes_recording(dat, np.array([11, 12, 13]), 25000.0, params, max_workers=1)
    names = set(result.spike_times[0])
    check("step 1 runs every wavelet and stores each by its own name",
          names == {"bior1p5", "bior1p3", "db2", "sym2", "haar", "mea"}, str(sorted(names)))
    try:
        sd._determine_scales("coif1", (0.4, 0.8), 25000.0, 5)
        check("an unknown wavelet is refused by name", False)
    except ValueError as err:
        check("an unknown wavelet is refused by name", "coif1" in str(err), str(err))

    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
