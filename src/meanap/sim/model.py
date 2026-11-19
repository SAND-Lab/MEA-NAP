"""Spike trains from a planted network, with each nuisance as its own dial.

The generative model is deliberately simple: a point process whose every
ingredient is one setting, so a line search can move exactly one thing.

1. **Background.** Each node fires as a Poisson process at its own rate.
   Rates are log-normal around ``rate_hz`` with spread ``rate_spread``
   (the SD of log rate), so some electrodes are much busier than others, as
   on a real array.
2. **Slow shared state.** Every node's background rate is multiplied by the
   same slow gain
   ``exp(a·x(t) − a²/2)``, where ``x`` is a smooth random signal (unit
   variance, correlation time ``state_period_s``) and ``a`` is
   ``state_amplitude``: the up and down states that make whole cultures fire
   together for tens of seconds. Its mean is 1, so it moves rates around
   without changing the average. Shared by all nodes, unrelated to the graph.
3. **Network bursts.** At ``burst_rate_hz`` a burst happens (at random
   times — the slow state leaves them alone, as on the recordings fitted so
   far, whose burst intervals have a CV near 1); each node joins it with probability ``burst_participation`` and
   fires Poisson(``burst_spikes`` × its own rate relative to the mean) spikes
   spread over ``burst_width_ms`` — busy electrodes are busy in bursts too.
   With ``burst_scope = "regions"`` each burst recruits one region (the
   planted modules, or ``n_modules`` blocks of the array if the graph has
   none): its nodes join with ``burst_participation``, the rest with that
   times ``burst_leak``. Which nodes joined which burst is kept
   (``SimResult.burst_joins``): it is the co-activation the bursts made.
   With ``burst_scope = "propagate"`` bursts come *from* the planted graph:
   each starts at one of ``burst_leaders`` leader nodes and spreads along
   the excitatory edges, each step taken with probability
   ``burst_participation`` after ``burst_hop_ms`` (±50%); nodes it cannot
   reach that way still join with probability ``burst_participation ×
   burst_leak``, standing for paths through neurons no electrode records.
   Each node's onset in each burst is kept (``SimResult.burst_onsets``).
   With ``burst_cluster_size`` above 1, bursts come in episodes (up-states)
   of on average that many bursts within ``burst_cluster_s``, at the same
   overall burst rate.
   Shared by everyone and unrelated to the graph: co-activation without
   coupling.
4. **Stimulation** (optional). Every ``stim_interval_s`` a stimulus makes a
   fixed ``stim_response_frac`` of nodes fire Poisson(``stim_spikes``)
   spikes ``stim_latency_ms`` after it, jittered by ``stim_jitter_ms``.
5. **Coupling — the planted graph.** For every edge, each spike of one node
   (from 1–4) makes the other fire one extra spike with probability
   ``coupling``, after an exponential delay with mean ``coupling_delay_ms``.
   Edges act both ways, as STTC is symmetric. Driven spikes do not drive
   further spikes, so turning coupling up cannot make the network run away.
6. **Inhibition** (optional). A share ``inhibitory_frac`` of the planted
   edges inhibit instead: after each spike of one node, each spike of the
   other in the next ``inhibition_ms`` is deleted with probability
   ``inhibition``. Shared bursts and stimulus responses are suppressed the
   same way, so strong shared activity can still swamp it — which is the
   point of being able to simulate it.

Only step 5 is "connectivity". Steps 2–4 are what a good edge method
should *not* report as edges; whether it does is what the sweeps measure.

The same seed gives the same graph and the same random draws whatever the
dials say, so a line search compares like with like (common random numbers).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace

import numpy as np

__all__ = [
    "GRAPHS", "SimSpec", "SimResult", "planted_graph", "simulate", "grid_coords",
]

#: Planted graph shapes.
GRAPHS = {
    "none": "No connections",
    "random": "Random",
    "modular": "Modules",
    "hub": "Hubs",
    "spatial": "Spatial (neighbours)",
}


@dataclass
class SimSpec:
    """Everything a simulation depends on."""

    # network
    n_nodes: int = 30
    graph: str = "modular"
    density: float = 0.15            # fraction of node pairs connected
    n_modules: int = 3
    within_module: float = 0.85      # share of edges inside modules ("modular")
    n_hubs: int = 3                  # "hub"
    spatial_scale_um: float = 300.0  # "spatial": connection length scale
    coupling: float = 0.15           # P(a spike drives a spike across an edge)
    coupling_delay_ms: float = 3.0
    inhibitory_frac: float = 0.0     # share of planted edges that inhibit
    inhibition: float = 0.6          # P(a partner's spike in the window is deleted)
    inhibition_ms: float = 20.0
    # activity
    duration_s: float = 120.0
    rate_hz: float = 2.0
    rate_spread: float = 0.5         # SD of log rate across nodes
    # shared nuisances
    burst_rate_hz: float = 0.0
    burst_participation: float = 0.8
    burst_spikes: float = 4.0
    burst_width_ms: float = 100.0
    burst_scope: str = "global"      # "global" | "regions" | "propagate"
    burst_leak: float = 0.1          # joining outside the region / off the planted paths
    burst_hop_ms: float = 10.0       # "propagate": delay per step along an edge
    burst_leaders: int = 3           # "propagate": nodes bursts can start at
    burst_cluster_size: float = 1.0  # mean bursts per episode (1 = independent bursts)
    burst_cluster_s: float = 5.0     # episode length
    state_amplitude: float = 0.0     # SD of the log gain
    state_period_s: float = 30.0     # correlation time of the slow state
    # stimulation
    stim_interval_s: float = 0.0     # 0 = no stimulation
    stim_response_frac: float = 0.5
    stim_spikes: float = 1.5
    stim_latency_ms: float = 10.0
    stim_jitter_ms: float = 3.0
    seed: int = 1

    def with_(self, **changes) -> "SimSpec":
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SimSpec":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class SimResult:
    """Simulated trains and the answer they were made from."""

    spec: SimSpec
    trains: list[np.ndarray]          # spike times (s), one sorted array per node
    adjacency: np.ndarray             # (n, n) bool, the planted graph (either sign)
    modules: np.ndarray               # (n,) module of each node (all 0 if none)
    hubs: np.ndarray                  # (n,) bool
    coords: np.ndarray                # (n, 2) µm, an MEA-like grid
    burst_times: np.ndarray = field(default_factory=lambda: np.empty(0))
    stim_times: np.ndarray = field(default_factory=lambda: np.empty(0))
    responders: np.ndarray = field(default_factory=lambda: np.empty(0, bool))
    #: (n, n_bursts) bool: which nodes joined each burst.
    burst_joins: np.ndarray | None = None
    #: (n_bursts,) the region each burst recruited (-1: the whole array).
    burst_region: np.ndarray | None = None
    #: (n, n_bursts) when each node joined each burst, relative to its start
    #: (s; NaN = did not join). Only for propagating bursts.
    burst_onsets: np.ndarray | None = None
    #: (n,) bool: the nodes propagating bursts start at.
    burst_leader_nodes: np.ndarray | None = None
    #: (n, n) +1 excitatory edge, −1 inhibitory, 0 none.
    signs: np.ndarray | None = None

    def __post_init__(self):
        if self.signs is None:
            self.signs = self.adjacency.astype(int)

    @property
    def excitatory(self) -> np.ndarray:
        return self.signs > 0

    @property
    def inhibitory(self) -> np.ndarray:
        return self.signs < 0

    @property
    def n(self) -> int:
        return len(self.trains)

    @property
    def duration_s(self) -> float:
        return float(self.spec.duration_s)

    def spike_counts(self) -> np.ndarray:
        return np.array([len(t) for t in self.trains], float)

    def rates_hz(self) -> np.ndarray:
        return self.spike_counts() / self.duration_s

    def spike_dict(self) -> dict[int, np.ndarray]:
        """In the form the pipeline's STTC takes (node index → times)."""
        return {i: t for i, t in enumerate(self.trains)}


def grid_coords(n: int, pitch_um: float = 200.0) -> np.ndarray:
    """*n* electrode positions filling a square grid row by row, like an MEA."""
    side = int(np.ceil(np.sqrt(max(n, 1))))
    idx = np.arange(n)
    return np.column_stack([(idx % side) * pitch_um, (idx // side) * pitch_um]).astype(float)


def _pairs(n: int) -> tuple[np.ndarray, np.ndarray]:
    return np.triu_indices(n, k=1)


def planted_graph(spec: SimSpec, rng: np.random.Generator, coords: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The planted graph: ``(adjacency, modules, hubs)``.

    Every shape keeps the expected density at ``spec.density``, so changing
    the shape changes only where the edges are, not how many there are.
    """
    n = spec.n_nodes
    iu, ju = _pairs(n)
    density = float(np.clip(spec.density, 0.0, 1.0))
    modules = np.zeros(n, int)
    hubs = np.zeros(n, bool)
    prob = np.full(iu.size, density)

    if spec.graph == "none" or n < 2:
        prob[:] = 0.0
    elif spec.graph == "modular":
        k = int(np.clip(spec.n_modules, 1, n))
        modules = np.arange(n) * k // n
        same = modules[iu] == modules[ju]
        n_edges = density * iu.size
        w = float(np.clip(spec.within_module, 0.0, 1.0))
        p_in = min(1.0, w * n_edges / max(same.sum(), 1))
        p_out = min(1.0, (n_edges - p_in * same.sum()) / max((~same).sum(), 1))
        prob = np.where(same, p_in, max(p_out, 0.0))
    elif spec.graph == "hub":
        h = int(np.clip(spec.n_hubs, 0, n))
        hubs[rng.permutation(n)[:h]] = True
        touches = hubs[iu] | hubs[ju]
        n_edges = density * iu.size
        p_hub = min(1.0, 0.7 * n_edges / max(touches.sum(), 1), 0.8)
        p_rest = max(0.0, (n_edges - p_hub * touches.sum()) / max((~touches).sum(), 1))
        prob = np.where(touches, p_hub, min(p_rest, 1.0))
    elif spec.graph == "spatial":
        d = np.hypot(*(coords[iu] - coords[ju]).T)
        shape = np.exp(-d / max(spec.spatial_scale_um, 1e-6))
        lo, hi = 0.0, 1e6      # scale so the mean probability is the density
        for _ in range(60):
            c = 0.5 * (lo + hi)
            if np.minimum(1.0, c * shape).mean() < density:
                lo = c
            else:
                hi = c
        prob = np.minimum(1.0, 0.5 * (lo + hi) * shape)
    elif spec.graph != "random":
        raise ValueError(f"Unknown graph {spec.graph!r}; expected one of {list(GRAPHS)}")

    edges = rng.random(iu.size) < prob
    adj = np.zeros((n, n), bool)
    adj[iu[edges], ju[edges]] = True
    adj |= adj.T
    return adj, modules, hubs


def _propagate(spec: SimSpec, signs: np.ndarray, nb: int) -> tuple[np.ndarray, np.ndarray]:
    """Onsets ``(n, nb)`` of bursts spreading from leader nodes along excitatory
    edges (earliest arrival wins), and the leader mask."""
    import heapq

    n = signs.shape[0]
    rng = np.random.default_rng([int(spec.seed), 0xB7])
    k = int(np.clip(spec.burst_leaders, 1, max(n, 1)))
    leaders = rng.permutation(n)[:k]
    nbrs = [np.nonzero(signs[i] > 0)[0] for i in range(n)]
    hop = max(spec.burst_hop_ms, 0.0) / 1000.0
    p = float(np.clip(spec.burst_participation, 0.0, 1.0))
    leak = p * float(np.clip(spec.burst_leak, 0.0, 1.0))
    onsets = np.full((n, nb), np.nan)
    for b in range(nb):
        start = int(leaders[rng.integers(k)])
        best = np.full(n, np.inf)
        best[start] = 0.0
        heap = [(0.0, start)]
        done = np.zeros(n, bool)
        while heap:
            t, u = heapq.heappop(heap)
            if done[u]:
                continue
            done[u] = True
            for v in nbrs[u]:
                if done[v] or rng.random() >= p:
                    continue
                tv = t + hop * rng.uniform(0.5, 1.5)
                if tv < best[v]:
                    best[v] = tv
                    heapq.heappush(heap, (tv, int(v)))
        # Off the planted paths: through neurons no electrode records.
        off = ~done & (rng.random(n) < leak)
        best[off] = hop * rng.uniform(1.0, 4.0, off.sum())
        reached = done | off
        onsets[reached, b] = best[reached]
    mask = np.zeros(n, bool)
    mask[leaders] = True
    return onsets, mask


def burst_regions(spec: SimSpec, modules: np.ndarray) -> np.ndarray:
    """The region of each node for regional bursts: the planted modules, or
    ``n_modules`` blocks of consecutive electrodes when the graph has none."""
    n = len(modules)
    if spec.graph == "modular" and modules.max() > 0:
        return modules
    k = int(np.clip(spec.n_modules, 1, max(n, 1)))
    return np.arange(n) * k // max(n, 1)


def _background(rate: float, duration: float, gain, peak_gain: float, rng) -> np.ndarray:
    """Poisson spikes at ``rate × gain(t)``, by thinning a ``rate × peak_gain`` process."""
    peak = rate * peak_gain
    if peak <= 0 or duration <= 0:
        return np.empty(0)
    t = rng.uniform(0.0, duration, rng.poisson(peak * duration))
    if peak_gain != 1.0:
        t = t[rng.random(t.size) < gain(t) / peak_gain]
    return t


def slow_gain(amplitude: float, timescale_s: float, duration_s: float, rng,
              step_s: float = 0.25):
    """The slow shared gain as ``(gain(t), its maximum)``.

    ``x`` is an Ornstein–Uhlenbeck (AR(1)) signal on a ``step_s`` grid with
    correlation time ``timescale_s``, scaled to unit variance; the gain
    ``exp(a·x − a²/2)`` is log-normal with mean 1 and log-SD ``a``.
    """
    a = max(float(amplitude), 0.0)
    if a == 0.0 or duration_s <= 0:
        return (lambda t: np.ones(np.shape(t))), 1.0
    grid = np.arange(0.0, duration_s + 2 * step_s, step_s)
    rho = np.exp(-step_s / max(float(timescale_s), step_s))
    noise = rng.standard_normal(grid.size)
    x = np.empty(grid.size)
    x[0] = noise[0]
    scale = np.sqrt(1.0 - rho ** 2)
    for k in range(1, grid.size):
        x[k] = rho * x[k - 1] + scale * noise[k]
    g = np.exp(a * x - 0.5 * a * a)

    def gain(t):
        return np.interp(t, grid, g)
    return gain, float(g.max())


def simulate(spec: SimSpec) -> SimResult:
    """Simulate one recording from *spec* (see the module docstring)."""
    n, T = int(spec.n_nodes), float(spec.duration_s)
    ss = np.random.SeedSequence([int(spec.seed), 0x5EED])
    # One stream per ingredient, so turning one dial leaves the others' draws alone.
    g_rng, r_rng, bg_rng, st_rng, bu_rng, sm_rng, sign_rng = (
        np.random.default_rng(s) for s in ss.spawn(7))

    coords = grid_coords(n)
    adj, modules, hubs = planted_graph(spec, g_rng, coords)
    # Which edges inhibit: one uniform draw per possible pair, so the share
    # can be swept without moving the graph or reshuffling the other edges.
    iu, ju = _pairs(n)
    u = sign_rng.random(iu.size)
    inhib_pair = adj[iu, ju] & (u < np.clip(spec.inhibitory_frac, 0.0, 1.0))
    signs = adj.astype(int)
    signs[iu[inhib_pair], ju[inhib_pair]] = -1
    signs[ju[inhib_pair], iu[inhib_pair]] = -1

    z = r_rng.standard_normal(n)
    sigma = max(float(spec.rate_spread), 0.0)
    # Log-normal with mean rate_hz whatever the spread.
    rates = spec.rate_hz * np.exp(sigma * z - 0.5 * sigma ** 2)

    gain, peak_gain = slow_gain(spec.state_amplitude, spec.state_period_s, T, st_rng)

    parents: list[list[np.ndarray]] = [[] for _ in range(n)]
    node_rngs = [np.random.default_rng(s) for s in np.random.SeedSequence(
        bg_rng.integers(2 ** 63)).spawn(n)]
    for i in range(n):
        parents[i].append(_background(float(rates[i]), T, gain, peak_gain, node_rngs[i]))

    burst_times = np.empty(0)
    burst_joins = np.zeros((n, 0), bool)
    burst_region = np.empty(0, int)
    burst_onsets = None
    burst_leader_nodes = None
    if spec.burst_rate_hz > 0:
        k = max(float(spec.burst_cluster_size), 1.0)
        if k > 1.0:
            episodes = _background(spec.burst_rate_hz / k, T, None, 1.0, bu_rng)
            per = 1 + bu_rng.poisson(k - 1.0, episodes.size)
            starts = np.repeat(episodes, per)
            burst_times = starts + bu_rng.uniform(0, max(spec.burst_cluster_s, 0.0), starts.size)
            burst_times = np.sort(burst_times[burst_times < T])
        else:
            burst_times = np.sort(_background(spec.burst_rate_hz, T, None, 1.0, bu_rng))
        sd = spec.burst_width_ms / 1000.0 / 4.0
        rel = rates / spec.rate_hz if spec.rate_hz > 0 else np.ones(n)
        nb = burst_times.size
        regions = burst_regions(spec, modules)
        if spec.burst_scope == "regions" and regions.max() > 0:
            r_rng = np.random.default_rng([int(spec.seed), 0xB6])
            burst_region = r_rng.integers(0, regions.max() + 1, nb)
        else:
            burst_region = np.full(nb, -1)
        burst_joins = np.zeros((n, nb), bool)
        if spec.burst_scope == "propagate":
            burst_onsets, burst_leader_nodes = _propagate(spec, signs, nb)
            burst_joins = np.isfinite(burst_onsets)
            for i in range(n):
                counts = bu_rng.poisson(spec.burst_spikes * rel[i], nb) * burst_joins[i]
                starts = np.repeat(burst_times + np.nan_to_num(burst_onsets[i]), counts)
                parents[i].append(starts + np.abs(bu_rng.normal(0.0, sd, starts.size)))
        for i in range(n if spec.burst_scope != "propagate" else 0):
            p = np.where((burst_region < 0) | (burst_region == regions[i]),
                         spec.burst_participation,
                         spec.burst_participation * np.clip(spec.burst_leak, 0.0, 1.0))
            joins = bu_rng.random(nb) < p
            burst_joins[i] = joins
            counts = bu_rng.poisson(spec.burst_spikes * rel[i], nb) * joins
            centres = np.repeat(burst_times, counts)
            parents[i].append(centres + bu_rng.normal(0.0, sd, centres.size))

    stim_times = np.empty(0)
    responders = np.zeros(n, bool)
    if spec.stim_interval_s > 0:
        first = min(spec.stim_interval_s, max(T - 1.0, 0.0)) / 2.0
        stim_times = np.arange(first, T, spec.stim_interval_s)
        responders[sm_rng.permutation(n)[:int(round(spec.stim_response_frac * n))]] = True
        lat, jit = spec.stim_latency_ms / 1000.0, spec.stim_jitter_ms / 1000.0
        for i in np.nonzero(responders)[0]:
            counts = sm_rng.poisson(spec.stim_spikes, stim_times.size)
            on = np.repeat(stim_times, counts)
            parents[i].append(on + lat + np.abs(sm_rng.normal(0.0, jit, on.size)))

    parent = [np.concatenate(p) if p else np.empty(0) for p in parents]
    trains = [list([p]) for p in parent]
    if spec.coupling > 0 and (signs > 0).any():
        delay = max(spec.coupling_delay_ms, 0.0) / 1000.0
        # One generator per directed edge, keyed by the pair: the draws for an
        # edge do not depend on which other edges exist.
        for i, j in zip(*np.nonzero(signs > 0)):
            e_rng = np.random.default_rng([int(spec.seed), 0xC0, int(i), int(j)])
            src = parent[i]
            hit = e_rng.random(src.size) < spec.coupling
            trains[j].append(src[hit] + 0.0005 + e_rng.exponential(delay or 1e-9, hit.sum()))

    out = []
    for parts in trains:
        t = np.concatenate(parts)
        t = np.sort(t[(t >= 0.0) & (t < T)])
        out.append(t)

    if spec.inhibition > 0 and (signs < 0).any():
        # Every inhibitory edge reads the trains as they were before any
        # inhibition, so the result does not depend on the order edges run in.
        before = [t.copy() for t in out]
        keep = [np.ones(t.size, bool) for t in out]
        window = max(spec.inhibition_ms, 0.0) / 1000.0
        for i, j in zip(*np.nonzero(signs < 0)):
            src, tgt = before[i], before[j]
            if src.size == 0 or tgt.size == 0:
                continue
            # Time since i's last spike before each of j's spikes.
            k = np.searchsorted(src, tgt, "left") - 1
            ok = k >= 0
            since = np.full(tgt.size, np.inf)
            since[ok] = tgt[ok] - src[k[ok]]
            e_rng = np.random.default_rng([int(spec.seed), 0x1B, int(i), int(j)])
            hit = (since <= window) & (e_rng.random(tgt.size) < spec.inhibition)
            keep[j] &= ~hit
        out = [t[k] for t, k in zip(out, keep)]
    return SimResult(spec=spec, trains=out, adjacency=adj, modules=modules, hubs=hubs,
                     coords=coords, burst_times=burst_times, stim_times=stim_times,
                     responders=responders, signs=signs, burst_joins=burst_joins,
                     burst_region=burst_region, burst_onsets=burst_onsets,
                     burst_leader_nodes=burst_leader_nodes)
