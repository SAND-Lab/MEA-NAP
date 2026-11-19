"""MEA-Sim: simulator, edge measures, line searches, pair tests, window.

Run: ``uv run python test_sim.py`` (from ``python/``; ~1 min).

What it has to show:
- the simulator plants what it says (density, modules, no edges for "none"),
  is reproducible from its seed, and keeps the planted graph fixed when only a
  nuisance dial changes (common random numbers);
- each nuisance does what it claims: bursts and slow states add shared
  activity; stimulation puts responders' spikes after each stimulus;
- the measures recover the planted graph on a quiet culture, and the
  circular-shift null fills in edges once there are network bursts (the
  known failure the tool exists to show);
- line-search scoring calls a flat metric robust and a moving one followed;
- Cutts & Eglen's tests reproduce their verdicts: STTC passes N1–N6, the
  correlation index fails N2 and N4; and STTC as MEA-NAP stores it (negative
  values zeroed) cannot tell anti-correlation from none (N6);
- inhibitory edges lower the partner's firing and give negative STTC that
  ranks them apart from unconnected pairs, which no thresholded method keeps;
  shared bursts hide it;
- fitting to a simulated recording (written as a step-1 file) recovers its
  bursts, slow state and coupling, and the burst detector finds no bursts in
  independent firing however fast it is;
- the two views of correlation: regional bursts make pairs in one region
  co-activate more; raw STTC recovers that co-activation better than the
  beyond-burst methods, which in turn recover planted connections better than
  within-burst STTC once there are bursts; burst dials are signal in one view
  and nuisance in the other; cutting bursts out keeps spikes and time right;
- the window builds headlessly and its Explore and Match tabs run.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def model_checks() -> None:
    from meanap.sim.model import SimSpec, simulate

    print("Simulator")
    iu = np.triu_indices(40, 1)
    dens = [simulate(SimSpec(n_nodes=40, graph="random", density=0.2, seed=s)).adjacency[iu].mean()
            for s in range(1, 9)]
    check("random graph has the density asked for", abs(np.mean(dens) - 0.2) < 0.03,
          f"{np.mean(dens):.3f}")
    sim = simulate(SimSpec(n_nodes=30, graph="modular", within_module=1.0, seed=3))
    same = sim.modules[:, None] == sim.modules[None, :]
    check("'modules' with all edges inside keeps them inside",
          sim.adjacency.any() and not (sim.adjacency & ~same).any())
    check("'none' plants nothing", not simulate(SimSpec(graph="none")).adjacency.any())
    a, b = simulate(SimSpec(seed=5)), simulate(SimSpec(seed=5))
    check("same seed, same trains", all(np.array_equal(x, y) for x, y in zip(a.trains, b.trains)))
    c = simulate(SimSpec(seed=5, rate_hz=6.0))
    check("changing a nuisance keeps the planted graph", np.array_equal(a.adjacency, c.adjacency))
    check("…and changes what it should", c.rates_hz().mean() > 2 * a.rates_hz().mean())
    check("trains are sorted and inside the recording",
          all(np.all(np.diff(t) >= 0) and (t.size == 0 or (t[0] >= 0 and t[-1] < 120))
              for t in a.trains))

    quiet = simulate(SimSpec(graph="none", seed=2))
    bursty = simulate(SimSpec(graph="none", seed=2, burst_rate_hz=0.2))
    check("bursts add spikes, at the burst times",
          bursty.spike_counts().sum() > quiet.spike_counts().sum() and bursty.burst_times.size > 5)
    stim = simulate(SimSpec(graph="none", seed=2, stim_interval_s=2.0, rate_hz=0.2,
                            stim_spikes=3.0))
    resp = np.nonzero(stim.responders)[0]
    lat = []
    for i in resp:
        t = stim.trains[i]
        k = np.searchsorted(stim.stim_times, t, "right") - 1
        ok = k >= 0
        lat.append(t[ok] - stim.stim_times[k[ok]])
    lat = np.concatenate(lat)
    check("stimulus responses land ~latency after each stimulus",
          np.mean((lat > 0.005) & (lat < 0.03)) > 0.8, f"{np.mean((lat > 0.005) & (lat < 0.03)):.2f}")


def measure_checks() -> None:
    from meanap.sim.measure import EdgeSettings, measure
    from meanap.sim.model import SimSpec, simulate

    print("Edge methods")
    st = EdgeSettings(rep_num=60)
    quiet = measure(simulate(SimSpec(seed=4)), ("circular", "jitter", "top"), st,
                    with_metrics=False)
    check("quiet culture: STTC ranks planted edges first (AUC > 0.95)",
          quiet["circular"].metrics["edgeAUC"] > 0.95, f"{quiet['circular'].metrics['edgeAUC']}")
    check("quiet culture: both nulls find most planted edges with few false ones",
          all(quiet[m].metrics["recall"] > 0.9 and quiet[m].metrics["falsePosRate"] < 0.35
              for m in ("circular", "jitter")),
          str({m: (quiet[m].metrics["recall"], quiet[m].metrics["falsePosRate"]) for m in quiet}))
    n = 30
    check("'strongest pairs' keeps the fraction asked for",
          abs(quiet["top"].metrics["nEdges"] - round(0.1 * n * (n - 1) / 2)) <= 1)
    bursty = measure(simulate(SimSpec(seed=4, burst_rate_hz=0.2, burst_spikes=5)),
                     ("circular", "jitter"), st, with_metrics=False)
    fp_c, fp_j = (bursty[m].metrics["falsePosRate"] for m in ("circular", "jitter"))
    check("bursts: the circular null turns most non-edges into edges, the jitter null fewer",
          fp_c > 0.8 and fp_j < fp_c, f"circular {fp_c:.2f}, jitter {fp_j:.2f}")
    full = measure(simulate(SimSpec(seed=4)), ("circular",), st)
    check("step 4's metrics come back", all(k in full["circular"].metrics
                                             for k in ("Dens", "Q", "PCmean", "Eglob")))


def sweep_checks() -> None:
    from meanap.sim.measure import EdgeSettings
    from meanap.sim.model import SimSpec
    from meanap.sim.sweep import jobs_for, run_job, score, summarise

    print("Line searches")
    jobs = jobs_for(SimSpec(n_nodes=16, duration_s=60), "rate_hz", [1.0, 4.0], 2, ["top"],
                    EdgeSettings(rep_num=30), metrics=["Dens", "meanSTTC"])
    check("one job per value × replicate", len(jobs) == 4)
    check("replicate k has the same seed at every value",
          jobs[0]["spec"]["seed"] == jobs[2]["spec"]["seed"]
          and jobs[0]["spec"]["seed"] != jobs[1]["spec"]["seed"])
    df = pd.DataFrame([r for j in jobs for r in run_job(j)])
    check("rows for every metric and the achieved rate",
          set(df["metric"]) == {"Dens", "meanSTTC", "meanRate"})
    check("summary has a mean per point", len(summarise(df)) == 2 * 3)

    rows = []
    for v in (1, 2, 3):
        for rep in range(3):
            rows.append({"dial": "rate_hz", "value": v, "rep": rep, "method": "m",
                         "metric": "flat", "val": 1.0 + 0.1 * rep})
            rows.append({"dial": "rate_hz", "value": v, "rep": rep, "method": "m",
                         "metric": "climbs", "val": v + 0.1 * rep})
            rows.append({"dial": "coupling", "value": v, "rep": rep, "method": "m",
                         "metric": "climbs", "val": v + 0.1 * rep})
    sc = score(pd.DataFrame(rows)).set_index(["dial", "metric"])["verdict"]
    check("a flat metric is robust to a nuisance", sc[("rate_hz", "flat")] == "robust")
    check("a metric that climbs with a nuisance follows it", sc[("rate_hz", "climbs")] == "follows")
    check("…and responds to a signal", sc[("coupling", "climbs")] == "responds")


def pair_checks() -> None:
    from meanap.sim.pairs import PairTestSettings, run_all

    print("Cutts & Eglen")
    res = {(r.prop, r.measure): r.passed for r in run_all(PairTestSettings(repeats=12))}
    check("STTC passes N1–N6", all(res[(p, "sttc")] for p in ("N1", "N2", "N3", "N4", "N5", "N6")),
          str({p: res[(p, "sttc")] for p in ("N1", "N2", "N3", "N4", "N5", "N6")}))
    check("the correlation index fails N2 (rate) and N4 (bounds)",
          res[("N2", "corr_index")] is False and res[("N4", "corr_index")] is False)
    check("…but is symmetric (N1)", res[("N1", "corr_index")] is True)
    check("STTC as MEA-NAP stores it cannot show anti-correlation (N6)",
          res[("N6", "sttc_stored")] is False)


def inhibition_checks() -> None:
    from meanap.sim.measure import EdgeSettings, measure
    from meanap.sim.model import SimSpec, simulate

    print("Inhibition")
    exc = simulate(SimSpec(seed=6))
    inh = simulate(SimSpec(seed=6, inhibitory_frac=0.5, inhibition=0.9))
    check("the same edges, some now inhibitory",
          np.array_equal(exc.adjacency, inh.adjacency) and inh.inhibitory.any()
          and (inh.inhibitory == inh.inhibitory.T).all())
    check("inhibition lowers firing", inh.rates_hz().mean() < exc.rates_hz().mean())
    m = measure(inh, ("circular",), EdgeSettings(rep_num=60), with_metrics=False)["circular"]
    check("inhibitory pairs have negative signed STTC", m.metrics["inhibSTTC"] < -0.01,
          f"{m.metrics['inhibSTTC']:.3f}")
    check("…which picks them out from unconnected pairs (AUC > 0.85)",
          m.metrics["inhibAUC"] > 0.85, f"{m.metrics['inhibAUC']:.2f}")
    check("no thresholded method keeps them", m.metrics["inhibKept"] == 0.0)
    b = measure(simulate(SimSpec(seed=6, inhibitory_frac=0.5, inhibition=0.9,
                                 burst_rate_hz=0.15, burst_spikes=5)),
                ("circular",), EdgeSettings(rep_num=60), with_metrics=False)["circular"]
    check("bursts hide it: fewer negative pairs", b.metrics["fracNegative"]
          < m.metrics["fracNegative"] - 0.15,
          f"{m.metrics['fracNegative']:.2f} → {b.metrics['fracNegative']:.2f}")


def view_checks() -> None:
    from meanap.sim.measure import EdgeSettings, coactivation_truth, measure, splice
    from meanap.sim.model import SimSpec, burst_regions, simulate
    from meanap.sim.sweep import DIALS

    print("What counts as correlation")
    spec = SimSpec(burst_rate_hz=0.25, burst_spikes=5.0, burst_scope="regions", burst_leak=0.1,
                   coupling=0.08, seed=7)
    sim = simulate(spec)
    reg = burst_regions(spec, sim.modules)
    co = coactivation_truth(sim)
    same = (reg[:, None] == reg[None, :]) & ~np.eye(sim.n, dtype=bool)
    diff = reg[:, None] != reg[None, :]
    check("regional bursts: pairs in one region share more of them",
          co[same].mean() > 3 * co[diff].mean(), f"{co[same].mean():.3f} vs {co[diff].mean():.3f}")
    r = measure(sim, ("raw", "excess", "outside", "within"), EdgeSettings(rep_num=40),
                with_metrics=False)
    m = {k: v.metrics for k, v in r.items()}
    check("co-activation: raw STTC recovers it better than the beyond-burst methods",
          m["raw"]["coactRho"] > max(m["excess"]["coactRho"], m["outside"]["coactRho"]) + 0.1,
          str({k: round(v["coactRho"], 2) for k, v in m.items()}))
    check("coupling: within-burst STTC recovers planted edges worst",
          m["within"]["edgeAUC"] < min(m[k]["edgeAUC"] for k in ("raw", "excess", "outside")),
          str({k: round(v["edgeAUC"], 2) for k, v in m.items()}))
    check("edges found / false positives are blank for unthresholded methods",
          np.isnan(m["raw"]["recall"]) and np.isnan(m["excess"]["falsePosRate"]))
    check("burst rate is signal for co-activation, a nuisance beyond bursts",
          DIALS["burst_rate_hz"].kind_for("coactivation") == "signal"
          and DIALS["burst_rate_hz"].kind_for("coupling") == "nuisance"
          and DIALS["rate_hz"].kind_for("coactivation") == "nuisance")
    trains = [np.array([0.5, 1.5, 2.5, 7.0]), np.array([3.0, 8.5])]
    out, length = splice(trains, np.array([[1.0, 3.0], [7.0, 9.0]]))
    check("splicing keeps the spikes inside and closes the gaps",
          length == 4.0 and np.allclose(out[0], [0.5, 1.5, 2.0]) and np.allclose(out[1], [3.5]),
          f"{out}, {length}")


def propagation_checks() -> None:
    from meanap.sim.measure import EdgeSettings, measure
    from meanap.sim.model import SimSpec, simulate

    print("Bursts that spread along connections")
    spec = SimSpec(burst_rate_hz=0.25, burst_spikes=4.0, burst_scope="propagate",
                   burst_participation=0.5, burst_leak=0.0, coupling=0.03, seed=9)
    sim = simulate(spec)
    on = sim.burst_onsets
    check("each burst starts at a leader, at time 0",
          all(np.any(sim.burst_leader_nodes & (on[:, b] == 0)) for b in range(on.shape[1])))
    # Without spill-over, every node that joined was reached through a planted
    # edge from an earlier node of the same burst.
    ok = True
    for b in range(on.shape[1]):
        o = on[:, b]
        for i in np.nonzero(np.isfinite(o) & (o > 0))[0]:
            prev = np.nonzero(sim.excitatory[i] & np.isfinite(o) & (o < o[i]))[0]
            ok &= prev.size > 0
    check("…and reaches every other node along planted connections", bool(ok))
    hop = spec.burst_hop_ms / 1000
    nb = np.isfinite(on)
    lag_edge = [abs(on[i, b] - on[j, b]) for b in range(on.shape[1])
                for i, j in zip(*np.nonzero(np.triu(sim.excitatory, 1))) if nb[i, b] and nb[j, b]]
    check("connected nodes join within about one step of each other",
          np.median(lag_edge) <= 1.5 * hop, f"{np.median(lag_edge) * 1000:.1f} ms")
    r = measure(sim, ("raw",), EdgeSettings(rep_num=30), with_metrics=False)["raw"].metrics
    check("raw STTC then finds the wiring too (co-activation and coupling no longer separate)",
          r["edgeAUC"] > 0.9, f"{r['edgeAUC']:.2f}")


def estimator_checks() -> None:
    from meanap.sim.estimators import binned, estimate
    from meanap.sim.pairs import PairTestSettings, run_property

    print("Measures from other papers")
    rng = np.random.default_rng(0)
    T = 40.0
    a = np.sort(rng.uniform(0, T, 200))
    b = np.sort(np.concatenate([a[rng.random(200) < 0.5] + 0.003, rng.uniform(0, T, 100)]))
    c = np.sort(rng.uniform(0, T, 150))
    tr = [a, b, c]

    X = binned(tr, T, 0.001) > 0
    nb = X.shape[1]

    def te_direct(i, j, d):
        j1, j0 = X[j, 1:], X[j, :-1]
        idx = np.arange(nb - 1) + 1 - d
        xi = np.where(idx >= 0, X[i, np.clip(idx, 0, None)], False)
        out, N = 0.0, nb - 1
        for A in (0, 1):
            for B in (0, 1):
                for C in (0, 1):
                    nabc = np.sum((j1 == A) & (j0 == B) & (xi == C))
                    if nabc:
                        out += nabc / N * np.log2(nabc * np.sum(j0 == B)
                                                  / (np.sum((j0 == B) & (xi == C))
                                                     * np.sum((j1 == A) & (j0 == B))))
        return out

    direct = max(te_direct(i, j, d) for i, j in ((0, 1), (1, 0)) for d in range(1, 11))
    te = estimate("te", tr, T, 10)
    check("transfer entropy equals the direct count", np.isclose(te[0, 1], direct),
          f"{te[0, 1]} vs {direct}")
    check("…and is near 0 for an unconnected pair", te[0, 2] < 0.1 * te[0, 1])
    d = (b[None, :] - a[:, None]).ravel()
    d = d[np.abs(d) <= 0.0105]
    hist = np.bincount(np.round(d / 0.001).astype(int) + 10, minlength=21)
    check("cross-correlation peak equals the direct count",
          np.isclose(estimate("cch", tr, T, 10)[0, 1], hist.max() / np.sqrt(a.size * b.size)))
    Xc = binned(tr, T, 0.01)
    P = Xc[2]

    def res(y):
        A = np.c_[np.ones_like(P), P]
        return y - A @ np.linalg.lstsq(A, y, rcond=None)[0]
    check("population-regressed correlation equals a direct regression",
          np.isclose(estimate("popreg", tr, T, 10)[0, 1],
                     np.corrcoef(res(Xc[0]), res(Xc[1]))[0, 1]))
    s = PairTestSettings(repeats=8)
    check("Schreiber similarity is not 0 for independent trains (fails N4)",
          run_property("N4", "schreiber", s).passed is False)
    check("the cross-correlation peak depends on firing rate (fails N2)",
          run_property("N2", "cch", s).passed is False)


def _write_sim(path, spec):
    from meanap.pipeline.io import save_spike_times_npz
    from meanap.sim.model import simulate

    sim = simulate(spec)
    save_spike_times_npz(path, {i: {"bior1p5": t} for i, t in enumerate(sim.trains)},
                         np.arange(sim.n) + 11, 25000.0, duration_s=sim.duration_s)
    return sim


def fit_checks(tmp) -> None:
    from meanap.sim.fit import describe, detect_bursts, fit_to_file
    from meanap.sim.model import SimSpec, simulate

    print("Match my data")
    busy = simulate(SimSpec(graph="none", rate_hz=15.0, rate_spread=0.3, seed=2))
    check("no bursts found in independent firing at 15 Hz",
          detect_bursts(busy.trains, busy.duration_s).size == 0)
    truth = SimSpec(n_nodes=30, duration_s=300, rate_hz=1.5, rate_spread=0.7, burst_rate_hz=0.1,
                    burst_spikes=6, burst_participation=0.7, burst_width_ms=150,
                    state_amplitude=0.5, state_period_s=20, coupling=0.2, seed=11)
    path = os.path.join(tmp, "SIM_DIV21_spikes.npz")
    _write_sim(path, truth)
    fit = fit_to_file(path)
    check("reads every active node", fit.data.n_nodes == 30)
    rel = {k: getattr(fit.sim, k) / getattr(fit.data, k) - 1 for k in (
        "mean_rate", "burst_rate", "burst_spikes", "mean_sttc")}
    check("the fitted simulation matches rate, bursts and STTC within 20%",
          all(abs(v) < 0.2 for v in rel.values()), str({k: round(v, 2) for k, v in rel.items()}))
    check("…and recovers the bursts and coupling it was made with",
          abs(fit.spec.burst_rate_hz / truth.burst_rate_hz - 1) < 0.35
          and abs(fit.spec.coupling / truth.coupling - 1) < 0.35,
          f"bursts {fit.spec.burst_rate_hz:.3f}, coupling {fit.spec.coupling:.3f}")
    st = describe(busy.trains, busy.duration_s)
    check("independent firing has no slow state", st.state_amplitude < 0.1,
          f"{st.state_amplitude:.2f}")
    return path


def window_checks(spike_file: str | None = None) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("Window: skipped (no PyQt6)")
        return
    import time

    print("Window")
    app = QApplication.instance() or QApplication([])
    from meanap.gui.sim_window import PRESETS, SimWindow

    w = SimWindow()
    w.form.preset.setCurrentIndex(list(PRESETS).index("Bursty culture (network bursts)"))
    check("a preset sets the culture", w.form.spec().burst_rate_hz > 0)
    spec = w.form.spec().with_(n_nodes=12, duration_s=40.0)
    w.form.set_spec(spec)
    check("the form round-trips the culture", w.form.spec() == spec)
    w.form.view.setCurrentIndex(w.form.view.findData("coactivation"))
    check("choosing co-activation picks its methods",
          set(w.form.chosen_methods()) == {"raw", "circular", "pearson"})
    w.form.view.setCurrentIndex(w.form.view.findData("coupling"))
    check("…and beyond-bursts picks the others",
          set(w.form.chosen_methods()) == {"jitter", "excess", "partial", "popreg"})
    w.form.set_spec(spec)
    w.run_explore()
    t = time.time()
    while not w.ex_bar.run.isEnabled() and time.time() - t < 120:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    check("Explore simulates and shows a figure",
          w.explored is not None and w.ex_canvas.painter is not None)
    check("…and fills the metric table", w.ex_table.rowCount() > 10)
    if spike_file:
        w.set_spike_file(spike_file)
        check("Match reads the file's methods", w.m_method.currentText() == "bior1p5")
        w.run_match()
        t = time.time()
        while not w.m_bar.run.isEnabled() and time.time() - t < 120:
            app.processEvents()
            time.sleep(0.05)
        app.processEvents()
        check("Match fits and puts the fitted culture on the left",
              w.fit is not None and w.form.spec().n_nodes == w.fit.spec.n_nodes
              and abs(w.form.spec().coupling - w.fit.spec.coupling) < 0.01)
    about = w.tabs.widget(w.tabs.count() - 1)
    check("an About tab with the common-input schematic",
          "About" in w.tabs.tabText(w.tabs.count() - 1)
          and w.about_canvas.painter is not None and about is not None)
    w.close()


def main() -> int:
    model_checks()
    measure_checks()
    sweep_checks()
    pair_checks()
    inhibition_checks()
    view_checks()
    propagation_checks()
    estimator_checks()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = fit_checks(tmp)
        window_checks(path)
    print(f"\nFAILURES: {len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
