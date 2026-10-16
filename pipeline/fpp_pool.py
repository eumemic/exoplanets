"""TRICERATOPS for many signals on one machine (run with .venv-trice): each star's target is set up once and cached,
and every run of every signal is a separate task in one process pool, longest first.

Usage:
  python fpp_pool.py setup JOBS.csv --out DIR [--procs 63] [--nearby-max-arcsec 30]
  python fpp_pool.py run   JOBS.csv --out DIR [--procs 63] [--runs 10] [--draws 200000]
JOBS columns: key, tic, fold (npz from export_fold.py), depth_ppm, sectors (field geometry, "s1,s2,..."), cutouts
(directory of tess-sSSSS-*.fits), molusc (MOLUSC survivors, may be empty), drop (scenarios to drop in the MOLUSC runs),
and optionally cc and cc_filt: a contrast curve (CSV of separation in arcsec, delta-magnitude) and its band (TESS, Vis,
J, H, K), which limit unresolved companions in every run of that job.
setup writes each job's target to DIR/states/<tic>_<sectors>_d<depth_ppm>.pkl (fpp_core.save_state; a target depends
on the signal's depth, which sets the eclipse depth each neighbour would need), with its fpp_core.setup_digest in
<state>.digest, and copies it to DIR/states/<tic>_<sectors>.pkl, which run reads, where the jobs give that star and
sectors one depth (otherwise the caller copies each job's state there before running it: cloud_worker.py). An optional
column not_hosts lists TIC entries ("id,id") that keep their light but host no scenario. run evaluates `runs` default-prior runs per signal,
and as many with the MOLUSC companions where a survivors file is given; each finished run is appended to DIR/runs.jsonl
(so an interrupted run resumes), and at the end DIR/<key>_fpp.json is written in fpp.py's format with the mean scenario
probabilities added. Workers are spawned, not forked: PyTransit's kernels use GNU OpenMP, which terminates a forked
child of a process that has used it. Each task seeds NumPy from its key, mode and run number, so a rerun is
reproducible and no two runs share draws.
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
import traceback

import numpy as np
import pandas as pd

import fpp_core as fc


def state_path(out, tic, sectors):
    return os.path.join(out, "states", f"{int(tic)}_{sectors.replace(',', '-')}.pkl")


def depth_state_path(out, tic, sectors, depth_ppm):
    return os.path.join(out, "states", f"{int(tic)}_{sectors.replace(',', '-')}_d{float(depth_ppm):g}.pkl")


def _setup_one(args):
    tic, sectors, cutouts, depth_ppm, out, nearby, not_hosts = args
    p = depth_state_path(out, tic, sectors, depth_ppm)
    if os.path.exists(p) and os.path.exists(p + ".digest"):
        return tic, sectors, depth_ppm, "cached", 0.0
    t0 = time.time()
    cache = os.path.join(out, "cache", str(int(tic)))
    os.makedirs(cache, exist_ok=True)
    try:
        target = fc.setup_target(int(tic), [int(s) for s in sectors.split(",")], cache, float(depth_ppm), cutouts=cutouts,
                                 nearby_max_arcsec=nearby, not_hosts=[int(x) for x in not_hosts.split(",") if x],
                                 verbose=False)
        fc.save_state(target, p)
        with open(p + ".digest", "w") as fh:
            fh.write(fc.setup_digest(target))
        return tic, sectors, depth_ppm, "ok", time.time() - t0
    except Exception as ex:
        return tic, sectors, depth_ppm, f"failed: {ex!r}"[:300], time.time() - t0


def _init_setup():
    fc.use_local_cutouts()
    fc.use_vizier_gaia()


_STATES = {}


def _target(p):
    t = _STATES.get(p)
    if t is None:
        if len(_STATES) >= 4:
            _STATES.pop(next(iter(_STATES)))
        t = _STATES[p] = fc.load_state(p)
    return t


def _init_run():
    fc.use_molusc_reader()


def _run_one(task):
    key, mode, k, sp, fold, molusc, drop, draws, method, cc, cc_filt = task
    seed = int.from_bytes(hashlib.sha256(f"{key}|{mode}|{k}|{method[0]}".encode()).digest()[:4], "little")
    np.random.seed(seed)
    t0 = time.time()
    try:
        if method[0] == "fast":
            import fast_trice
            fast_trice.enable(n_pilot=method[1], n_final=method[2], seed=seed)
        elif "fast_trice" in sys.modules:
            sys.modules["fast_trice"].disable()
        target = _target(sp)
        d = np.load(fold)
        f, n = fc.run_once(target, d, N=draws, molusc_file=molusc if mode == "m" else None,
                           drop=[x for x in drop.split(",") if x] if mode == "m" else (), cc=cc or None, cc_filt=cc_filt or "TESS")
        pr = target.probs[["ID", "scenario", "prob"]]
        out = dict(key=key, mode=mode, k=k, FPP=f, NFPP=n, sec=time.time() - t0, seed=seed,
                   probs=[[int(i), s, float(v)] for i, s, v in pr.itertuples(index=False) if v > 1e-6],
                   lnZ=[float(z) if np.isfinite(z) else None for z in target.lnZ])
        if method[0] == "fast":
            import fast_trice
            out["diag"] = [[n_, h, round(e, 1)] for n_, h, e in fast_trice.S.diag]
        return out
    except Exception:
        return dict(key=key, mode=mode, k=k, error=traceback.format_exc()[-1500:], sec=time.time() - t0)


def setup(a, jobs):
    os.makedirs(os.path.join(a.out, "states"), exist_ok=True)
    nh = jobs["not_hosts"] if "not_hosts" in jobs else pd.Series([""] * len(jobs), index=jobs.index)
    todo = sorted({(int(r.tic), r.sectors, r.cutouts, float(r.depth_ppm), str(h or "")) for r, h in zip(jobs.itertuples(), nh)})
    args = [(t, s, c, dp, a.out, a.nearby_max_arcsec, h) for t, s, c, dp, h in todo]
    n_ok = 0
    with mp.get_context("spawn").Pool(a.procs, initializer=_init_setup) as pool:
        for i, (tic, sectors, depth, status, sec) in enumerate(pool.imap_unordered(_setup_one, args), 1):
            n_ok += status in ("ok", "cached")
            if status not in ("ok", "cached"):
                print(f"setup {tic} [{sectors}] {status}", flush=True)
            if i % 50 == 0 or i == len(args):
                print(f"setup {i}/{len(args)} targets, {n_ok} ready", flush=True)
    depths = {}
    for t, s, _, dp, _ in todo:
        depths.setdefault((t, s), set()).add(dp)
    for (t, s), ds in depths.items():               # the state run reads, where it is unambiguous
        src = depth_state_path(a.out, t, s, next(iter(ds)))
        if len(ds) == 1 and os.path.exists(src):
            for ext in ("", ".digest"):
                shutil.copyfile(src + ext, state_path(a.out, t, s) + ext)
    print("SETUP_DONE", flush=True)


def run(a, jobs):
    tag = "" if a.method == "stock" else f"_{a.method}"
    log = os.path.join(a.out, f"runs{tag}.jsonl")
    done = set()
    if os.path.exists(log):
        for line in open(log):
            r = json.loads(line)
            if "error" not in r:
                done.add((r["key"], r["mode"], r["k"]))
    tasks, meta = [], {}
    for r in jobs.itertuples():
        sp = state_path(a.out, r.tic, r.sectors)
        if not os.path.exists(sp):
            print(f"{r.key}: no target state, skipped", flush=True)
            continue
        target = fc.load_state(sp)
        d = np.load(r.fold)
        ex = fc.fold_exptime(d)
        cost = fc.n_scenarios(target) * (len(d["time"]) * fc.auto_nsamples(ex) + 200)
        molusc = r.molusc if isinstance(r.molusc, str) and r.molusc and os.path.exists(r.molusc) else ""
        drop = r.drop if isinstance(r.drop, str) else ""
        meta[r.key] = dict(tic=int(r.tic), exptime_min=ex * 1440, nsamples=fc.auto_nsamples(ex), n_points=int(len(d["time"])),
                           sectors=r.sectors, n_scenarios=fc.n_scenarios(target), molusc=molusc, drop=drop)
        # TRICERATOPS evaluates every transiting draw at once: about 2e4 of the 2e5 draws, each over points x sub-exposures
        mem = 0.5 + 8e-9 * 0.1 * a.draws * len(d["time"]) * fc.auto_nsamples(ex) * 1.2
        cc = getattr(r, "cc", "") if isinstance(getattr(r, "cc", ""), str) else ""
        cc_filt = getattr(r, "cc_filt", "") if isinstance(getattr(r, "cc_filt", ""), str) else ""
        meta[r.key].update(cc=os.path.basename(cc), cc_filt=cc_filt)
        meta[r.key]["task"] = (cost, sp, r.fold, molusc, drop, cc, cc_filt)
        meta[r.key]["mem"] = mem
    first = a.runs_min or a.runs

    def batch(want):
        """Tasks for the runs k < want[(key, mode)] that are not done, longest first."""
        out = []
        for key, m in meta.items():
            cost, sp, fold, molusc, drop, cc, cc_filt = m["task"]
            for mode in ("d", "m") if molusc else ("d",):
                for k in range(want.get((key, mode), first)):
                    if (key, mode, k) not in done:
                        out.append((cost, (key, mode, k, sp, fold, molusc, drop, a.draws, (a.method, a.n_pilot, a.n_final), cc,
                                           cc_filt)))
        return [t for _, t in sorted(out, key=lambda x: -x[0])]

    res_by = {}
    if os.path.exists(log):
        for line in open(log):
            r = json.loads(line)
            if "error" not in r:
                res_by.setdefault((r["key"], r["mode"]), {})[r["k"]] = r
    tasks = batch({})
    print(f"{len(tasks)} runs to do for {len(meta)} signals ({len(done)} already done)", flush=True)
    t0, n, rnd = time.time(), 0, 0
    with mp.get_context("spawn").Pool(a.procs, initializer=_init_run) as pool, open(log, "a") as fh:
        while tasks:
            rnd += 1
            for res in _dispatch(pool, tasks, {k: m["mem"] for k, m in meta.items()}, a.mem_gb, a.procs):
                fh.write(json.dumps(res) + "\n"); fh.flush()
                n += 1
                if "error" in res:
                    print(f"{res['key']} {res['mode']}{res['k']}: {res['error'].splitlines()[-1]}", flush=True)
                else:
                    done.add((res["key"], res["mode"], res["k"]))
                    res_by.setdefault((res["key"], res["mode"]), {})[res["k"]] = res
                if n % 200 == 0:
                    print(f"{n} runs, {time.time() - t0:.0f} s", flush=True)
            if not a.runs_min or rnd >= 2 + -(-a.runs // a.runs_min):     # rounds are capped: a run that keeps failing ends them
                break
            # adaptive: more runs, up to --runs, where a mean is within z standard errors of a threshold
            want = {}
            for km, rr in res_by.items():
                if km[0] in meta and len(rr) < a.runs and needs_more([x["FPP"] for x in rr.values()], [x["NFPP"] for x in rr.values()], a.z):
                    want[km] = min(a.runs, len(rr) + a.runs_min)
            tasks = batch({**{(k, md): len(res_by.get((k, md), {})) for k in meta for md in ("d", "m")}, **want})
            print(f"round {rnd} done ({n} runs, {time.time() - t0:.0f} s); {len(want)} signal-modes need more runs: {len(tasks)} runs", flush=True)
    merge(a, meta, tag)
    print("RUN_DONE", flush=True)


def _mem_total_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 2 ** 20
    except OSError:
        pass
    return 16.0


def _dispatch(pool, tasks, mem_of, budget_gb, procs):
    """Run tasks (longest first) keeping the estimated memory of the runs in flight under budget_gb, so that a few
    large folds cannot exhaust the machine (the kernel then kills workers and a Pool waits forever for their tasks)."""
    import queue
    budget = budget_gb or 0.8 * _mem_total_gb()
    done_q, in_flight, used = queue.Queue(), 0, 0.0
    pending = list(tasks)
    while pending or in_flight:
        j = 0
        while j < len(pending) and j < 500 and in_flight < procs:      # the largest that fit, not only the next
            t = pending[j]
            m = mem_of.get(t[0], 1.0)
            if in_flight and used + m > budget:
                j += 1
                continue
            used += m; in_flight += 1
            pool.apply_async(_run_one, (t,), callback=lambda r, m=m: done_q.put((r, m)),
                             error_callback=lambda e, m=m, t=t: done_q.put((dict(key=t[0], mode=t[1], k=t[2], error=repr(e), sec=0.0), m)))
            pending.pop(j)
        try:
            r, m = done_q.get(timeout=3600)
        except queue.Empty:
            print(f"no run finished in an hour; {in_flight} in flight given up", flush=True)
            return
        used -= m; in_flight -= 1
        yield r


def needs_more(fpps, nfpps, z):
    """True if the mean FPP is within z standard errors of 0.5 or 0.015, or the mean NFPP of 0.1 or 0.001."""
    k = len(fpps)
    if k < 2:
        return True
    for vals, thr in ((fpps, (0.5, 0.015)), (nfpps, (0.1, 0.001))):
        m, se = float(np.mean(vals)), float(np.std(vals, ddof=1)) / np.sqrt(k)
        if any(abs(m - t) < z * se for t in thr):
            return True
    return False


def merge(a, meta, tag=""):
    rows = [json.loads(line) for line in open(os.path.join(a.out, f"runs{tag}.jsonl"))]
    by = {}
    for r in rows:
        if "error" not in r:
            by.setdefault((r["key"], r["mode"]), {})[r["k"]] = r       # one result per run number
    for key, m in meta.items():
        d = [by.get((key, "d"), {})[k] for k in sorted(by.get((key, "d"), {}))]
        if not d:
            continue
        fpps, nfpps = [r["FPP"] for r in d], [r["NFPP"] for r in d]
        res = dict(tic=m["tic"], FPP_mean=float(np.mean(fpps)), FPP_sd=float(np.std(fpps, ddof=1)) if len(fpps) > 1 else None,
                   FPP_sem=float(np.std(fpps, ddof=1) / np.sqrt(len(fpps))) if len(fpps) > 1 else None,
                   FPP=fpps, NFPP=nfpps, NFPP_mean=float(np.mean(nfpps)), NFPP_max=float(np.max(nfpps)), runs=len(d), draws=a.draws,
                   exptime_min=m["exptime_min"], nsamples=m["nsamples"], n_points=m["n_points"], sectors=m["sectors"],
                   n_scenarios=m["n_scenarios"], cpu_s=float(sum(r["sec"] for r in d)), probs_mean=mean_probs(d))
        if m.get("cc"):
            res.update(cc=m["cc"], cc_filt=m["cc_filt"])
        mm = [by.get((key, "m"), {})[k] for k in sorted(by.get((key, "m"), {}))]
        if mm:
            kept = pd.read_csv(m["molusc"])
            fm, nm = [r["FPP"] for r in mm], [r["NFPP"] for r in mm]
            res.update(FPP_m_mean=float(np.mean(fm)), FPP_m_sem=float(np.std(fm, ddof=1) / np.sqrt(len(fm))) if len(fm) > 1 else None,
                       FPP_m=fm, NFPP_m=nm, NFPP_m_mean=float(np.mean(nm)), NFPP_m_max=float(np.max(nm)), molusc_survivors=len(kept),
                       molusc_used=int((kept["semi-major axis(AU)"] * (1 - kept["eccentricity"]) > 10).sum()),
                       drop=[x for x in m["drop"].split(",") if x], cpu_m_s=float(sum(r["sec"] for r in mm)), probs_m_mean=mean_probs(mm))
        with open(os.path.join(a.out, f"{key}_fpp{tag}.json"), "w") as fh:
            json.dump(res, fh)
    print(f"merged {len(meta)} signals", flush=True)


def mean_probs(runs):
    acc = {}
    for r in runs:
        for i, s, v in r["probs"]:
            acc[(i, s)] = acc.get((i, s), 0.0) + v / len(runs)
    return [[i, s, round(v, 8)] for (i, s), v in sorted(acc.items(), key=lambda x: -x[1])[:12]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["setup", "run"])
    ap.add_argument("jobs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--draws", type=int, default=200000)
    ap.add_argument("--nearby-max-arcsec", type=float, default=30.0)
    ap.add_argument("--method", choices=["stock", "fast"], default="stock",
                    help="fast: Sobol pilot + importance sampling in the uniform numbers (fast_trice.py); outputs tagged _fast")
    ap.add_argument("--runs-min", type=int, default=0,
                    help="adaptive: start with this many runs per signal and mode, add as many again (up to --runs) while a "
                         "mean is within --z standard errors of a threshold")
    ap.add_argument("--z", type=float, default=3.0)
    ap.add_argument("--mem-gb", type=float, default=0.0, help="memory budget for runs in flight (default 80%% of RAM)")
    ap.add_argument("--n-pilot", type=int, default=2 ** 14)
    ap.add_argument("--n-final", type=int, default=2 ** 15)
    a = ap.parse_args()
    jobs = pd.read_csv(a.jobs, dtype={"sectors": str, "molusc": str, "drop": str}, keep_default_na=False)
    (setup if a.cmd == "setup" else run)(a, jobs)


if __name__ == "__main__":
    sys.exit(main())
