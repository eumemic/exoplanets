"""Lower-variance TRICERATOPS marginal likelihoods (run in .venv-trice).

TRICERATOPS estimates each scenario's marginal likelihood as the mean likelihood over N draws from the scenario's prior,
and makes every draw by passing uniform random numbers (np.random.rand, np.random.randint) through the prior's inverse
CDF. Most draws do not transit, or transit with the wrong depth or duration, so the estimate rests on few draws and
scatters between runs. Here the same scenarios, priors and likelihood functions are used unchanged; only the uniform
numbers differ. For each scenario call:
  1. a pilot of n_pilot draws takes its uniform numbers from a scrambled Sobol sequence (a low-discrepancy set, so the
     draws cover the prior more evenly than random numbers);
  2. from the pilot's likelihoods, a proposal density g(u) is fitted in the space of the uniform numbers: for each
     uniform number, a piecewise-constant density with bins of equal pilot weight, mixed with the uniform density
     (fraction alpha) so that no region of the prior is missed;
  3. the final n_final draws take their uniform numbers from g (through a second Sobol set), and each draw's likelihood
     is weighted by 1/g(u). Since the prior in the space of the uniform numbers is uniform, the weighted mean is an
     unbiased estimate of the same integral (importance sampling).
If the pilot has too few draws with a likelihood (fewer than min_hits), the final draws stay uniform (Sobol). If the
pilot's estimate is negligible next to the largest found so far in the same calc_probs call (skip_below in ln units),
the pilot's estimate is returned without final draws; it is unbiased, only noisier, and cannot change the result.
With the MOLUSC companions (bound-companion scenarios with Gaia limits), TRICERATOPS pairs its draws with the file's
survivors and pads the rest with no companion, so the prior probability of a companion is (survivors used)/N. With
fewer draws than the file has companions, each companion is kept with probability N/N_ref (N_ref, the number MOLUSC
simulated), which keeps that probability unchanged in expectation.
Use: import fast_trice; fast_trice.enable(n_pilot=2**14, n_final=2**15, seed=...); then target.calc_probs(...) as usual
(its N argument is ignored); fast_trice.disable() restores stock TRICERATOPS.
"""
import inspect

import numpy as np
import pandas as pd
from scipy.stats import qmc

import triceratops.marginal_likelihoods as ml
import triceratops.triceratops as tt

_real_np = np
_real_lme = ml._log_mean_exp
_orig = {}


class _State:
    method = "stock"
    n_pilot = 2 ** 14
    n_final = 2 ** 15
    alpha = 0.2
    bins = 32
    min_hits = 8
    dims = 24
    n_ref = 200000
    rng = np.random.default_rng(0)
    # per call
    mode = None          # "sobol" or "prop"
    base = None          # Sobol points, n x dims
    col = 0
    cols = []            # uniform numbers handed out, one array per rand/randint call
    logw_sum = None      # log 1/g(u) per draw (prop mode)
    prop = None          # list of (edges, dens) per dimension
    captured = []        # logw arrays seen by _log_mean_exp
    diag = []            # (scenario, n_hits, ess_final)
    skip_below = 30.0    # skip the final draws when the pilot's lnZ is this far below the largest so far
    run_max = -np.inf    # largest pilot lnZ in this calc_probs call


S = _State()


def _next_uniform(n):
    """The next column of uniform numbers for the current scenario call."""
    j = S.col
    S.col += 1
    if S.mode is None or j >= S.dims:
        return _real_np.random.rand(n)
    v = S.base[:n, j]
    if S.mode == "prop" and S.prop is not None and j < len(S.prop) and S.prop[j] is not None:
        edges, dens = S.prop[j]
        cdf = _real_np.concatenate([[0.0], _real_np.cumsum(dens * _real_np.diff(edges))])
        k = _real_np.clip(_real_np.searchsorted(cdf, v, side="right") - 1, 0, len(dens) - 1)
        u = edges[k] + (v - cdf[k]) / dens[k]
        u = _real_np.clip(u, 0.0, _real_np.nextafter(1.0, 0.0))
        S.logw_sum -= _real_np.log(dens[k])
    else:
        u = v
    S.cols.append(u)
    return u


class _Random:
    def __getattr__(self, name):
        return getattr(_real_np.random, name)

    def rand(self, *shape):
        if len(shape) != 1:
            return _real_np.random.rand(*shape)
        return _next_uniform(int(shape[0])).copy()

    def randint(self, low, high=None, size=None):
        if high is None or size is None or _real_np.ndim(size) != 0:
            return _real_np.random.randint(low, high, size)
        u = _next_uniform(int(size))
        return _real_np.minimum(low + _real_np.floor(u * (high - low)).astype(int), high - 1)


class _NP:
    random = _Random()

    def __getattr__(self, name):
        return getattr(_real_np, name)


def _lme(logw, *, N_total):
    logw = _real_np.asarray(logw, dtype=float)
    if S.mode is not None:
        if S.mode == "prop" and S.logw_sum is not None and len(S.logw_sum) == len(logw):
            logw = logw + S.logw_sum
        S.captured.append(logw)
    return _real_lme(logw, N_total=N_total)


def _fit_proposal(n):
    """Per uniform number, bins of equal pilot weight (mixed 10% with uniform before taking quantiles, so the edges stay
    well defined), as a density mixed with the uniform density with weight alpha."""
    lw = _real_np.full(n, -_real_np.inf)
    for c in S.captured:
        if len(c) == n:
            lw = _real_np.logaddexp(lw, _real_np.where(_real_np.isfinite(c), c, -_real_np.inf))
    hits = int(_real_np.isfinite(lw).sum())
    if hits < S.min_hits:
        return None, hits
    w = _real_np.exp(lw - lw.max())
    w[~_real_np.isfinite(w)] = 0.0
    w /= w.sum()
    prop = []
    for u in S.cols:
        if len(u) != n:
            prop.append(None)
            continue
        o = _real_np.argsort(u)
        cw = 0.9 * _real_np.cumsum(w[o]) + 0.1 * u[o]          # CDF of the mixture at the sorted pilot points
        q = _real_np.linspace(0, 1, S.bins + 1)[1:-1]
        inner = _real_np.interp(q, cw, u[o])
        edges = _real_np.unique(_real_np.concatenate([[0.0], inner, [1.0]]))
        edges = edges[_real_np.concatenate([[True], _real_np.diff(edges) > 1e-6])]
        edges[-1] = 1.0
        width = _real_np.diff(edges)
        # mixture CDF increments per bin -> density of the quantile-bin proposal: equal mass per bin
        dq = _real_np.full(len(width), 1.0 / len(width))
        dens = S.alpha + (1 - S.alpha) * dq / width
        dens /= _real_np.sum(dens * width)
        prop.append((edges, dens))
    return prop, hits


def _begin(mode, n, prop=None):
    S.mode = mode
    S.base = qmc.Sobol(d=S.dims, scramble=True, seed=S.rng).random(n)
    S.col = 0
    S.cols = []
    S.captured = []
    S.prop = prop
    S.logw_sum = _real_np.zeros(n) if mode == "prop" else None


def _end():
    S.mode = None


def _wrap(name, F):
    sig = inspect.signature(F)

    def W(*args, **kw):
        if S.method == "stock":
            return F(*args, **kw)
        ba = sig.bind(*args, **kw)
        ba.apply_defaults()
        ba.arguments["N"] = S.n_pilot
        _begin("sobol", S.n_pilot)
        try:
            pilot = F(*ba.args, **ba.kwargs)
        finally:
            prop, hits = _fit_proposal(S.n_pilot)
            lz = max([_real_lme(c, N_total=S.n_pilot) for c in S.captured if len(c) == S.n_pilot] or [-_real_np.inf])
            _end()
        if _real_np.isfinite(lz) and lz < S.run_max - S.skip_below:
            # negligible next to a scenario already computed: the pilot's (unbiased) estimate is enough
            S.diag.append((name, hits, -1.0))
            return pilot
        S.run_max = max(S.run_max, lz)
        ba.arguments["N"] = S.n_final
        _begin("prop" if prop is not None else "sobol", S.n_final, prop)
        try:
            res = F(*ba.args, **ba.kwargs)
            ess = 0.0
            for c in S.captured:
                if len(c) == S.n_final and _real_np.isfinite(c).any():
                    w = _real_np.exp(c - _real_np.nanmax(c[_real_np.isfinite(c)]))
                    w = w[_real_np.isfinite(w)]
                    ess = max(ess, float(w.sum() ** 2 / (w ** 2).sum()))
            S.diag.append((name, hits, ess))
        finally:
            _end()
        return res
    return W


_molusc_cache = {}


def _read_molusc(f, *args, **kw):
    """MOLUSC survivors for TRICERATOPS (writable copies, as fpp_core.use_molusc_reader), subsampled to the call's N."""
    import types
    if f not in _molusc_cache:
        df = pd.read_csv(f, *args, **kw)
        _molusc_cache[f] = {c: df[c].to_numpy(copy=True) for c in df.columns}
    cols = _molusc_cache[f]
    n_call = len(S.base) if S.base is not None and S.mode is not None else S.n_ref
    keep = S.rng.random(len(next(iter(cols.values())))) < min(1.0, n_call / S.n_ref)

    class _Columns:
        def __init__(self, c):
            self.c = c

        def __getitem__(self, key):
            if isinstance(key, str):
                return types.SimpleNamespace(values=self.c[key].copy())
            return _Columns({k: v[_real_np.asarray(key)] for k, v in self.c.items()})
    return _Columns({k: v[keep] for k, v in cols.items()})


def enable(n_pilot=2 ** 14, n_final=2 ** 15, alpha=0.2, bins=32, seed=0, n_ref=200000):
    """Switch calc_probs to the pilot + importance-sampling estimates. Reseed per run for independent runs."""
    S.method, S.n_pilot, S.n_final, S.alpha, S.bins, S.n_ref = "fast", n_pilot, n_final, alpha, bins, n_ref
    S.rng = np.random.default_rng(seed)
    S.diag = []
    S.run_max = -np.inf
    if not _orig:
        for name in dir(ml):
            if name.startswith("lnZ_") and callable(getattr(ml, name)):
                _orig[name] = getattr(ml, name)
        for name, F in _orig.items():
            setattr(tt, name, _wrap(name, F)) if hasattr(tt, name) else None
        ml.np = _NP()
        ml._log_mean_exp = _lme
        ml.read_csv = _read_molusc
        _real_np.random.seed(seed % 2 ** 32)


def disable():
    S.method = "stock"
