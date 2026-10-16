"""Batches of TRICERATOPS runs on an AWS spot instance, for the rows the build lists as pending or stale
(results_public/products/triceratops_plan.csv) or for named signal keys; every result goes into the store (store.py,
tri_store.py), and the build then takes it up.

  python cloud.py plan [--keys KEY,...] [--cc] [--no-base] [--type c8g.4xlarge]
        The batch: its signals, the requests of their stages (fold, MOLUSC; the setup and runs are requested from the
        fold's content when it arrives), the store entries it reuses, and the cost estimate. Writes
        results_cloud/batches/<id>/plan.json and the snapshots the instance reads. --cc adds runs with each contrast
        curve of high-resolution imaging found for the star in data/followup/exofop_cc (speckle at 832 nm, modelled in
        the TESS band; adaptive optics in K or Br-gamma, in K); --no-base leaves out the runs without a curve.
  python cloud.py plan --centroids [--keys KEY,...]
        Per-sector centroid measurements (centroid_sectors.py) of the counted full-sky candidates that have none or
        whose measurement used another ephemeris (the checks counted_measured_centroids and centroid_inputs_current),
        or of the named keys; the sectors are the twelve with the highest per-sector SNR in the signal's vetting file.
        A centroid batch has no TRICERATOPS signals.
  python cloud.py plan --fits [--keys KEY,...]
        Transit fits (fit_transit.py, seeded) of the full-sky rows held in tier C for want of a fit, or of named keys
        (a refit, after new light curves), starting from the catalog's ephemeris and masking the star's other signals.
  python cloud.py run ID --approve [--hours 3]
        Builds the kit (git archive of the plan's commit, the snapshots, the reused stage files and presigned upload
        URLs), uploads it to the bucket, launches one spot instance tagged with the batch (cloud_worker.py runs there),
        follows its heartbeat, ingests each signal as it arrives (checked again, then stored), and terminates the
        instance when every signal is in, when it stops sending heartbeats, or at the time limit.
  python cloud.py ingest ID
        Ingests what the batch has uploaded so far (run does this as it goes).

Nothing launches without --approve. Only the instance this command launched, checked by its ID and batch tag, is ever
terminated. AWS: profile jarvis-ec2 in us-east-1 (network and AMI as in the memory notes and results_cloud/glue/t2);
bucket eumemic-exoplanets-cache, private; the instance has no AWS credentials and uses the presigned URLs.
"""
import argparse
import glob
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

import centroid_store
import fit_store
import store as st
import tri_store

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PIPE = os.path.join(ROOT, "pipeline")
BATCHES = os.path.join(ROOT, "results_cloud", "batches")
PLAN_CSV = os.path.join(ROOT, "results_public", "products", "triceratops_plan.csv")
MOLUSC_CODE = os.path.join(ROOT, "results_cloud", "rescue", "exo_pix_20261015", "kitE2", "molusc", "code")
CC_DIR = os.path.join(ROOT, "data", "followup", "exofop_cc")
GAIA_CACHE = os.path.join(ROOT, "results_cloud", "glue", "build", "gaia_dr3.csv")
DR2_CACHE = os.path.join(ROOT, "results_cloud", "glue", "build", "dr2_to_dr3.csv")
AWS = dict(profile="jarvis-ec2", region="us-east-1", bucket="eumemic-exoplanets-cache", subnet="subnet-3172a550",
           zone="us-east-1c", sg="sg-0083a7488e9e73f14", key="exo-search-key",
           ami=open(os.path.join(ROOT, "results_cloud", "glue", "t2", "ami_id")).read().strip()
           if os.path.exists(os.path.join(ROOT, "results_cloud", "glue", "t2", "ami_id")) else "")
VCPUS = {"c8g.2xlarge": 8, "c8g.4xlarge": 16, "c8g.8xlarge": 32, "c8g.16xlarge": 64, "c7g.4xlarge": 16, "c7g.16xlarge": 64}
COLS = ["key", "tic", "period", "t0", "duration_h", "depth_ppm", "masks", "drop"]
STARS = [f"data/catalogs/shard{k}.parquet" for k in range(8)] + [f"data/catalogs/{n}.parquet" for n in
                                                                  ("targets", "toi_hosts", "tce_hosts", "faint_targets")]


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=True).stdout.strip()


def aws():
    import boto3
    return boto3.Session(profile_name=AWS["profile"], region_name=AWS["region"])


def s3client():
    """S3 with SigV4 presigned URLs, which sign only the host: a SigV2 URL also signs the Content-Type, and an upload
    whose client sets another one (urllib sends application/x-www-form-urlencoded) is refused."""
    from botocore.config import Config
    return aws().client("s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))


# snapshots ----------------------------------------------------------------------------------------------------------
def star_rows(tics):
    ids = set(tics)
    parts = [pd.read_parquet(os.path.join(ROOT, f)).query("ID in @ids", local_dict={"ids": ids}) for f in STARS]
    s = pd.concat(parts).drop_duplicates("ID")
    s = s[[c for c in s.columns if not c.startswith("__")]]
    missing = ids - set(s.ID)
    if missing:
        raise ValueError(f"no TIC row for {sorted(missing)}")
    s["GAIA"] = [int(x) if str(x).strip().isdigit() else -1 for x in s["GAIA"]]
    return s


def gaia_rows(dr2_ids):
    """Gaia DR3 rows for TIC Gaia (DR2) ids, from the caches of earlier batches, querying the ARI mirror for the rest
    (the answers are added to the cache). Returns (rows, {dr2: dr3})."""
    caches = sorted(glob.glob(os.path.join(ROOT, "results_cloud", "glue", "t2", "gaia_dr3_t*.csv"))) + \
        ([GAIA_CACHE] if os.path.exists(GAIA_CACHE) else [])
    maps = sorted(glob.glob(os.path.join(ROOT, "results_cloud", "glue", "t2", "dr2_to_dr3_t*.csv"))) + \
        ([DR2_CACHE] if os.path.exists(DR2_CACHE) else [])
    g = pd.concat([pd.read_csv(f) for f in caches]).drop_duplicates("source_id") if caches else pd.DataFrame()
    mp = pd.concat([pd.read_csv(f) for f in maps]).drop_duplicates("dr2_source_id") if maps else pd.DataFrame(
        columns=["dr2_source_id", "dr3_source_id"])
    m = dict(zip(mp.dr2_source_id, mp.dr3_source_id))
    want = {int(x) for x in dr2_ids if x > 0}
    have = set(g.source_id) if len(g) else set()
    todo = sorted(x for x in want if x not in have and m.get(x) not in have)
    if todo:
        from astroquery.utils.tap.core import TapPlus
        tap = TapPlus(url="https://gaia.ari.uni-heidelberg.de/tap", verbose=False)
        cols = ("source_id, ra, dec, parallax, parallax_error, phot_g_mean_mag, bp_rp, ruwe, astrometric_params_solved, "
                "astrometric_n_good_obs_al, astrometric_chi2_al, non_single_star, radial_velocity, radial_velocity_error, "
                "rv_method_used, rv_nb_transits, rv_amplitude_robust, rv_chisq_pvalue, rv_renormalised_gof, grvs_mag")
        new = tap.launch_job(f"SELECT {cols} FROM gaiadr3.gaia_source WHERE source_id IN ({','.join(map(str, todo))})").get_results().to_pandas()
        miss = sorted(set(todo) - set(new.source_id))
        if miss:
            n = tap.launch_job("SELECT dr2_source_id, dr3_source_id, angular_distance, magnitude_difference FROM "
                               f"gaiadr3.dr2_neighbourhood WHERE dr2_source_id IN ({','.join(map(str, miss))})").get_results().to_pandas()
            n["score"] = n.angular_distance.abs() + 100 * n.magnitude_difference.abs()
            best = n.sort_values("score").groupby("dr2_source_id").first().reset_index()
            more = tap.launch_job(f"SELECT {cols} FROM gaiadr3.gaia_source WHERE source_id IN "
                                  f"({','.join(map(str, best.dr3_source_id))})").get_results().to_pandas()
            new = pd.concat([new, more])
            old = pd.read_csv(DR2_CACHE) if os.path.exists(DR2_CACHE) else pd.DataFrame()
            pd.concat([old, best[["dr2_source_id", "dr3_source_id"]]]).drop_duplicates("dr2_source_id").to_csv(DR2_CACHE, index=False)
            m.update(dict(zip(best.dr2_source_id, best.dr3_source_id)))
        old = pd.read_csv(GAIA_CACHE) if os.path.exists(GAIA_CACHE) else pd.DataFrame()
        pd.concat([old, new]).drop_duplicates("source_id").to_csv(GAIA_CACHE, index=False)
        g = pd.concat([g, new]).drop_duplicates("source_id")
    keep = {m.get(x, x) for x in want}
    return g[g.source_id.isin(keep)].copy(), m


def manifest_rows(tics):
    """The light-curve list of each star (lcindex.lists): the re-search manifests (fixed QLP reader) where they have the
    star, else the full-sky and earlier ones, as every batch since 15 October, with the redeliveries and withdrawals of
    the MAST snapshot (results_public/products/lightcurves_current.csv) applied."""
    import lcindex
    return lcindex.lists(tics, lcindex.CURRENT, ROOT)


def curves(tic):
    """The contrast curves on ExoFOP for a star: [{label, file, filt, content}], labelled by band and observation."""
    out = []
    for f in sorted(glob.glob(os.path.join(CC_DIR, f"{tic}__*.csv"))):
        name = os.path.basename(f)
        obs = name.split("__", 1)[1].split("-")
        if name.endswith("-832_sensitivity.csv"):
            band, filt = "832", "TESS"
        elif name.endswith(("Kcont_plot.csv", "Brgamma_plot.csv")):
            band, filt = "K", "K"
        else:
            continue
        out.append(dict(label=f"cc{band}-{obs[1]}", file=name, filt=filt, content=st.file_content(f)))
    return out


def dir_content(d):
    return st.sha256_json([[os.path.relpath(p, d), st.file_content(p)] for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True))
                           if os.path.isfile(p)])


# plan ---------------------------------------------------------------------------------------------------------------
def spot_price(itype):
    r = aws().client("ec2").describe_spot_price_history(
        InstanceTypes=[itype], ProductDescriptions=["Linux/UNIX"], AvailabilityZone=AWS["zone"],
        StartTime=datetime.now(timezone.utc) - timedelta(hours=1))
    p = [float(x["SpotPrice"]) for x in r["SpotPriceHistory"]]
    return max(p) if p else None


def vet_json(tic, period):
    """The vetting file of a full-sky signal (the full-sky search's or the QLP re-search's): (json, path)."""
    fs = glob.glob(os.path.join(ROOT, "results_cloud", "*", "vet_allsky", f"tic{tic}_*.json")) + \
        glob.glob(os.path.join(ROOT, "results_cloud", "qfull", "*", "results", "vet_q*", f"tic{tic}_*.json"))
    best = None
    for f in fs:
        v = json.load(open(f))
        if abs(v["period"] / period - 1) < 2e-3 and (best is None or abs(v["period"] / period - 1) < abs(best[0]["period"] / period - 1)):
            best = (v, f)
    return best


def centroid_rows(keys=None):
    """centroid_sectors.py list rows: the counted full-sky candidates without a per-sector measurement or with one made
    on another ephemeris, or the named keys."""
    import catalog_checks as cc
    import dag.params as P_
    P = P_.load(os.path.join(PIPE, "params.toml"))
    a = pd.read_csv(os.path.join(ROOT, "results_public", "candidates_allsky.csv"))
    a["key"] = [f"tic{t}_P{p:.4f}" for t, p in zip(a.TIC, a.P_d)]
    if keys:
        sel = a[a.key.isin(keys)]
        if set(sel.key) != set(keys):
            raise SystemExit(f"not full-sky catalog keys: {sorted(set(keys) - set(sel.key))}")
    else:
        tol = {k.split(".")[1]: v for k, v in P.items() if k.startswith("freshness.")}
        with open(os.path.join(ROOT, "results_public", "products", "stage_code.json")) as fh:
            code_now = json.load(fh)
        stale = {(int(x.split()[1]), x.split()[3]) for x in cc.centroid_inputs_current(
            os.path.join(ROOT, "results_public", "products", "centroids.csv"),
            os.path.join(ROOT, "results_public", "products", "measurements_allsky.csv"), tol, code_now)}
        need = a.tier.isin(P["catalog.counted_allsky"]) & a.cs_sectors.isna()
        sel = a[need | pd.Series([(t, f"{p}") in stale for t, p in zip(a.TIC, a.P_d)], index=a.index)]
    stars = star_rows(sorted(set(sel.TIC))).set_index("ID")
    rows = []
    for r in sel.itertuples():
        v = vet_json(r.TIC, r.P_d)
        if v is None:
            raise SystemExit(f"{r.key}: no vetting file to choose the sectors from")
        ps = sorted(((p["depth_ppm"] / p["err_ppm"], int(p["sector"])) for p in v[0].get("per_sector") or [] if p["err_ppm"] > 0),
                    reverse=True)
        rows.append(dict(set="cloud", tier=r.tier, tic=int(r.TIC), P_d=r.P_d, period=r.P_d, t0=r.T0_BJD - 2457000,
                         duration_h=r.T14_h, depth_ppm=r.depth_ppm, sectors=",".join(str(x) for x in sorted(x for _, x in ps[:12])),
                         MES=r.MES, source_tic="", ra=float(stars.loc[r.TIC, "ra"]), dec=float(stars.loc[r.TIC, "dec"]), key=r.key))
    return rows


def star_hash(row):
    """The hash of a star's TIC row as the batch's snapshot has it."""
    return st.sha256_json({k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()})


def tri_items(keys, cc, base, rerun_legacy=False, runs=10, molusc_sample=0):
    """The TRICERATOPS signals of a batch with the requests of their fold and MOLUSC stages, and the snapshots the
    instance reads: (items, stars, gaia, manifest, reuse)."""
    rows = list(pd.read_csv(PLAN_CSV, dtype=str, keep_default_na=False).to_dict("records"))
    if keys:
        sel = [r for r in rows if r["key"] in keys]
        rest = set(keys) - {r["key"] for r in sel}
        if rest:                                    # signals the plan does not list (the tiers do not need them)
            import tri_plan
            more = tri_plan.items(rest, *(os.path.join(ROOT, f) for f in (
                "results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv",
                "candidates/ephemerides.csv", "data/known/toi.csv")), 0.002)
            if set(more) != rest:
                raise SystemExit(f"no catalog row has the key: {sorted(rest - set(more))}")
            sel += list(more.values())
    elif rerun_legacy:                              # every result in use that is legacy, to be computed again
        sel = [r for r in rows if r["status"] == "legacy"]
    else:
        sel = [r for r in rows if r["status"] in ("pending", "stale")]
    if not sel:
        return [], None, None, None, {}
    items = [{c: r[c] for c in COLS} for r in sel]
    tics = sorted({int(it["tic"]) for it in items})
    stars = star_rows(tics)
    gaia, m = gaia_rows(stars.GAIA)
    stars["GAIA_DR3"] = [int(m.get(x, x)) if x > 0 else -1 for x in stars.GAIA]
    man = manifest_rows(tics)
    from dag.codehash import CodeIndex
    index = CodeIndex([PIPE])
    code = {k: tri_store.code_hash(k, index) for k in tri_store.STAGE_CODE}
    env = {k: tri_store.env_hash(k) for k in tri_store.STAGE_CODE}
    mcode = dir_content(MOLUSC_CODE)
    s = st.Store()
    out, reuse = [], {"fold": [], "molusc": []}
    gaia_by = gaia.set_index("source_id")
    import ticfield
    nonhost = ticfield.by_star(ticfield.NONSTELLAR, ticfield.NEARBY_ARCSEC)
    in_use = tri_store.latest(s)
    import dag.params as params_
    n_samples = int(params_.load(os.path.join(PIPE, "params.toml"))["triceratops.molusc_samples"])
    for it in items:
        tic = int(it["tic"])
        lcs = [[int(r.sector), str(r.prov), float(r.exptime), str(r.uri)] for r in man[man.tic == tic].itertuples()]
        freq = tri_store.fold_request(it, lcs, code["fold"], env["fold"])
        star = stars[stars.ID == tic].iloc[0]
        mreq, more = None, []
        if star.GAIA_DR3 in gaia_by.index and float(star["mass"]) > 0:
            row = {k: (v.item() if hasattr(v, "item") else v) for k, v in gaia_by.loc[star.GAIA_DR3].to_dict().items()}
            mreq = tri_store.molusc_request(tic, dict(row, source_id=int(star.GAIA_DR3)), float(star["mass"]), mcode,
                                           code["molusc"], env["molusc"])
            import molusc_sample as ms
            if molusc_sample:                       # another sample of simulated companions (molusc_sample.py)
                mreq = dict(mreq, sample=int(molusc_sample), seed=ms.sample_seed(tic, molusc_sample),
                            code=code["molusc_sample"], env=env["molusc_sample"])
            else:                                   # the catalog's further samples (triceratops.molusc_samples)
                more = [dict(mreq, sample=k, seed=ms.sample_seed(tic, k), code=code["molusc_sample"], env=env["molusc_sample"])
                        for k in range(1, n_samples)]
        if s.has("fold", st.key_of(freq)):
            reuse["fold"].append(it["key"])
        if mreq and s.has("molusc", st.key_of(mreq)):
            reuse["molusc"].append(tic)
        cs = curves(tic) if cc else []
        if not base and not cs:
            raise SystemExit(f"{it['key']}: --no-base, and no contrast curve for TIC {tic}")
        x = dict(item=it, fold_request=freq, molusc_request=mreq, molusc_samples=more, base_runs=base, cc=cs,
                 star=star_hash(star.drop(labels=["GAIA_DR3"]).to_dict()), not_hosts=nonhost.get(tic, []))
        x["prior"] = None if molusc_sample else prior_result(s, in_use.get(it["key"]), x, code, env, runs)
        out.append(x)
    return out, stars, gaia, man, dict(reuse, code=code, env=env, molusc_sample=int(molusc_sample),
                                       molusc_samples=1 if molusc_sample else n_samples)


def prior_result(s, used, x, code, env, runs):
    """The result in use that the instance may keep (cloud_worker.py): one whose fold, MOLUSC file, runs, code of the runs
    and packages are those the new request would have, so that only its target setup can differ; the instance keeps it
    if the new setup's digest equals that of the setup it ran on (fpp_core.setup_digest). None if there is none."""
    if used is None or x["cc"] or not x["base_runs"]:
        return None
    key, req, res = used
    if req.get("legacy") or not res.get("setup_key") or not res.get("fold_key"):
        return None
    mk = st.key_of(x["molusc_request"]) if x["molusc_request"] else None
    same = (res["fold_key"] == st.key_of(x["fold_request"]) and res.get("molusc_key") == mk and req.get("runs") == runs
            and req.get("code") == code["tri"] and req.get("env") == env["tri"]
            and str(req.get("depth_ppm")) == str(x["item"]["depth_ppm"]) and str(req.get("drop") or "") == str(x["item"]["drop"] or ""))
    sent = s.get("tri_setup", res["setup_key"])
    if not same or sent is None or not sent[1].get("remote"):
        return None
    return dict(tri=key, setup=res["setup_key"])


def split(out, parts):
    """Signals in parts of about equal cost, every star's signals in one part (its target setup and MOLUSC are made
    once): the cost of a signal is its legacy result's points times scenarios where there is one."""
    cost = {}
    for r in pd.read_csv(os.path.join(ROOT, "results_public", "products", "triceratops.csv")).itertuples():
        cost[r.key] = float(r.n_points) * float(r.n_scenarios)
    stars = {}
    for x in out:
        stars.setdefault(int(x["item"]["tic"]), []).append(x)
    load = [[0.0, []] for _ in range(parts)]
    for tic, xs in sorted(stars.items(), key=lambda kv: -sum(cost.get(x["item"]["key"], 5000.0) for x in kv[1])):
        part = min(load, key=lambda p: p[0])
        part[0] += sum(cost.get(x["item"]["key"], 5000.0) * (1 + len(x["cc"])) for x in xs)
        part[1] += xs
    return [p[1] for p in load if p[1]]


def vet_items(kind, keys=None):
    """The vetting (kind vet) or pixel follow-up (kind pixel) of a batch: the rows with folders whose result is out of
    date (vet_store.stale), or the named keys; each starts from the signal its vetting in use was made for (the search's
    rank, period, epoch and duration; the search's density, masked TOIs and events where its candidate table has them:
    search_signals.csv). Returns (items, stars, manifest)."""
    import followup
    import lcindex
    import ticfield
    import vet_store as vs
    prod = os.path.join(ROOT, "results_public", "products")
    vet = {(r["table"], vs.signal_key(r)): r for r in vs._rows(os.path.join(prod, "vetting.csv"))}
    sig = {(r["table"], vs.signal_key(r)): r for r in vs._rows(os.path.join(ROOT, "results_cloud", "glue", "build",
                                                                             "search_signals.csv"))}
    if keys:
        want = [k for k in vet if k[1] in set(keys)]
        if {k[1] for k in want} != set(keys):
            raise SystemExit(f"no catalog row has the key: {sorted(set(keys) - {k[1] for k in want})}")
    else:
        tiers = __import__("dag.params", fromlist=["load"]).load(os.path.join(PIPE, "params.toml"))["catalog.folder_tiers_allsky"]
        folders = {r["candidate_id"] for r in vs._rows(os.path.join(ROOT, "results_public", "candidates_allsky.csv"))
                   if r["tier"] in tiers} | {r["candidate_id"] for r in vs._rows(os.path.join(ROOT, "results_public",
                                                                                          "tiers_earlier_candidates.csv"))}
        bad = vs.stale(os.path.join(prod, "vetting.csv"), os.path.join(prod, "lightcurves_searched.csv"),
                       os.path.join(prod, "lightcurves.csv"), os.path.join(prod, "stage_code.json"), folders)
        word = "vetting" if kind == "vet" else "pixel follow-up"
        want = [(t, vs.signal_key(dict(TIC=tic, P_d=p))) for t, tic, p, why in bad if word in why]
    want = [k for k in want if vet[k]["vet_store"]]
    if not want:
        return [], None, None
    store = st.Store()
    tics = sorted({int(vet[k]["TIC"]) for k in want})
    stars, man = star_rows(tics), manifest_rows(tics)
    code, env = vs.code_hash(kind), tri_store.env_hash("fold")
    known = vs.known_hash() if kind == "vet" else None
    nonstellar = ticfield.by_star(ticfield.NONSTELLAR)
    out = []
    for k in sorted(want):
        v = vet[k]
        vj = json.load(open(os.path.join(store.path("vet", v["vet_store"]), "vetting.json")))
        tic = int(v["TIC"])
        s = dict(key=k[1], tic=tic, rank=int(vj["rank"]), period=repr(float(vj["period"])), t0=repr(float(vj["t0"])),
                 duration_h=repr(float(vj["duration_h"])), depth_ppm=repr(float(vj["depth_ppm"])))
        x = sig.get(k, {})
        for c in ("rho", "masked_tois", "events"):
            if x.get(c) not in (None, ""):
                s[c] = x[c]
        if kind == "vet":
            lcs = [[int(r.sector), str(r.prov), float(r.exptime), str(r.uri)] for r in man[man.tic == tic].itertuples()]
            star = star_hash(stars[stars.ID == tic].iloc[0].to_dict())
            req = vs.vet_request(k[0], s, lcs, star, known, code, env)
        else:
            ps = [(int(p["sector"]), p["depth_ppm"] / p["err_ppm"]) for p in vj.get("per_sector") or [] if p["err_ppm"] > 0]
            top = max((snr for _, snr in ps), default=0)
            secs = [sec for _, _, sec in sorted((followup.cutout_mb(sec), -snr, sec) for sec, snr in ps if snr >= 0.6 * top)]
            secs = secs[:vs.PIXEL_SECTORS]
            row = stars[stars.ID == tic].iloc[0]
            s.update(sectors=secs, not_sources=nonstellar.get(tic, []))
            req = vs.pixel_request(k[0], s, secs, (row["ra"], row["dec"]), s["not_sources"], code, env)
        out.append(dict(item=dict(s, table=k[0]), request=req, row_P_d=v["P_d"], vet_store=v["vet_store"]))
    return out, stars, man


def fit_items(keys=None):
    """The fits of a batch: rows held in tier C for want of a fit and rows whose fit is stale (made from light curves
    that have changed: redo.csv), or the named keys; with their requests and the snapshots (stars, light-curve list) the
    instance reads."""
    import catalog
    import tri_plan
    rows = {"candidates_allsky": pd.read_csv(os.path.join(ROOT, "results_public", "candidates_allsky.csv"), dtype=str,
                                             keep_default_na=False).to_dict("records")}
    if keys:
        want = set(keys)
    else:
        want = {f"tic{r['TIC']}_P{float(r['P_d']):.4f}" for r in rows["candidates_allsky"] if r["c_reason"] == catalog.NO_FIT}
        prod = os.path.join(ROOT, "results_public", "products")
        want |= {f"tic{t}_P{float(p):.4f}" for _, t, p, _ in fit_store.stale(
            os.path.join(prod, "fits.csv"), os.path.join(prod, "redo.csv"), os.path.join(prod, "stage_code.json"))}
    items = tri_plan.items(want, *(os.path.join(ROOT, f) for f in (
        "results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv", "candidates/ephemerides.csv",
        "data/known/toi.csv")), 0.002)
    if set(items) != want:
        raise SystemExit(f"no catalog row has the key: {sorted(want - set(items))}")
    if not items:
        return [], None, None
    table_of = {f"tic{r['TIC']}_P{float(r['P_d']):.4f}": "candidates_allsky" for r in rows["candidates_allsky"]}
    measured = {f"tic{r['TIC']}_P{float(r['P_d']):.4f}": r for f in ("measurements_allsky.csv", "measurements_earlier.csv")
                for r in pd.read_csv(os.path.join(ROOT, "results_public", "products", f), dtype=str,
                                     keep_default_na=False).to_dict("records")}
    for key, it in items.items():              # a row whose fit failed has no fitted epoch: start from the measured one
        if not all(math.isfinite(float(it[c])) for c in ("t0", "duration_h")):
            m = measured.get(key) or {}
            if not (m.get("T0_BJD") and m.get("T14_h")):
                raise SystemExit(f"{key}: no epoch and duration to start the fit from")
            it.update(t0=repr(float(m["T0_BJD"]) - 2457000), duration_h=repr(float(m["T14_h"])))
    tics = sorted({int(it["tic"]) for it in items.values()})
    stars, man = star_rows(tics), manifest_rows(tics)
    code, env = fit_store.code_hash(), tri_store.env_hash("fold")
    out = []
    for key, it in sorted(items.items()):
        tic = int(it["tic"])
        lcs = [[int(r.sector), str(r.prov), float(r.exptime), str(r.uri)] for r in man[man.tic == tic].itertuples()]
        star = star_hash(stars[stars.ID == tic].iloc[0].to_dict())
        table = table_of.get(key, "tiers_earlier_candidates")
        out.append(dict(item=it, request=fit_store.request(table, it, lcs, star, code, env), row_P_d=str(it["period"])))
    return out, stars, man


def plan(keys=None, itype="c8g.4xlarge", runs=10, cc=False, base=True, centroids=False, rerun_legacy=False, parts=1,
         fits=False, molusc_sample=0, vet=False, pixel=False):
    """A batch: TRICERATOPS signals, or (centroids) per-sector centroid measurements; with parts > 1, that many
    batches (one instance each). Writes plan.json for each."""
    if git("status", "--porcelain", "--", "pipeline", "requirements.txt", "requirements-triceratops.txt"):
        raise SystemExit("pipeline/ or a lock file has uncommitted changes: the kit ships a commit, so commit first")
    commit = git("rev-parse", "HEAD")
    out, cs_out, stars, gaia, man, extra = [], [], None, None, None, {}
    if vet or pixel:
        kind = "vet" if vet else "pixel"
        v_out, stars, man = vet_items(kind, keys)
        if not v_out:
            print(f"nothing to {'vet' if vet else 'follow up'}: every row with a folder has a current result")
            return None
        return _write_plan("b" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"), commit, itype, runs, [], [], stars,
                           None, man, {kind: v_out})
    if fits:
        fit_out, stars, man = fit_items(keys)
        if not fit_out:
            print("nothing to fit: no row is held in tier C for want of a fit")
            return None
        return _write_plan("b" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"), commit, itype, runs, [], [], stars,
                           None, man, {}, fit_out)
    if centroids:
        ccode, cenv = centroid_store.code_hash(), tri_store.env_hash("fold")
        cs_out = [dict(item=r, request=centroid_store.request(r, ccode, cenv)) for r in centroid_rows(keys)]
        if not cs_out:
            print("nothing to measure: every counted candidate has a current per-sector centroid measurement")
            return None
    else:
        out, stars, gaia, man, extra = tri_items(keys, cc, base, rerun_legacy, runs, molusc_sample)
        if not out:
            print("nothing to run: no row of triceratops_plan.csv is pending or stale")
            return None
        if parts > 1:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            plans = []
            for k, part in enumerate(split(out, parts)):
                tics = {int(x["item"]["tic"]) for x in part}
                plans.append(_write_plan(f"b{stamp}p{k}", commit, itype, runs, part, [], stars[stars.ID.isin(tics)],
                                         gaia, man[man.tic.isin(tics)], extra))
            total = sum(p["estimate"]["usd"] or 0 for p in plans)
            print(f"{len(plans)} batches, about ${total:.2f} in all; launch each with: python cloud.py run ID --approve")
            return plans
    return _write_plan("b" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"), commit, itype, runs, out, cs_out, stars,
                       gaia, man, extra)


def _write_plan(bid, commit, itype, runs, out, cs_out, stars, gaia, man, extra, fit_out=()):
    d = os.path.join(BATCHES, bid)
    os.makedirs(d)
    if out or fit_out or extra.get("vet") or extra.get("pixel"):
        stars.to_parquet(os.path.join(d, "stars.parquet"))
        man.to_parquet(os.path.join(d, "manifest.parquet"))
    if gaia is not None:
        gaia.to_csv(os.path.join(d, "gaia.csv"), index=False)
    price, vc = spot_price(itype), VCPUS.get(itype, 16)
    # measured: 270 signals (5,400 runs) took 34 min on 64 vCPUs on 15 October (about 0.4 core-minutes a run, with
    # MOLUSC and the setups alongside); a centroid measurement ~1-3 min per signal on one core (12 in ~4 min with 6)
    # a signal with a result in use that it may keep runs only if its new target setup differs (assumed for 1 in 10)
    variants = sum((0.1 if x.get("prior") else 1) * (int(x["base_runs"]) + len(x["cc"])) for x in out)
    # a fit: 3,000 steps of 32 walkers, ~2-5 min on one core
    # a vetting ~1-2 min on one core, a pixel follow-up ~3-5 min (difference images of two sectors)
    n_vet, n_pix = len(extra.get("vet", [])), len(extra.get("pixel", []))
    hours = (15 + variants * 2 * runs * 0.4 / max(1, vc - 1) + len(cs_out) * 2.0 / 6 + len(fit_out) * 5.0 / max(1, vc - 1)
             + n_vet * 2.0 / max(1, vc - 1) + n_pix * 5.0 / max(1, min(16, vc - 1))) / 60
    est = dict(instance=itype, spot_usd_per_h=price, hours=round(hours, 2), usd=round(price * hours, 2) if price else None,
               limit_hours=round(max(1.0, 3 * hours), 1))
    p = dict(id=bid, commit=commit, created=datetime.now(timezone.utc).isoformat(timespec="seconds"), runs=runs,
             code=extra.get("code", {}), env=extra.get("env", {}), items=out, centroids=cs_out, fits=list(fit_out),
             fit_env=tri_store.env_hash("fold"),
             centroid_env=tri_store.env_hash("fold"), reuse={k: extra.get(k, []) for k in ("fold", "molusc")}, estimate=est,
             molusc_sample=extra.get("molusc_sample", 0), molusc_samples=extra.get("molusc_samples", 1),
             vet=extra.get("vet", []), pixel=extra.get("pixel", []))
    with open(os.path.join(d, "plan.json"), "w") as fh:
        json.dump(p, fh, indent=1)
    print(f"batch {bid}: {len(out)} TRICERATOPS signals, {len(cs_out)} centroid measurements, {len(fit_out)} fits, "
          f"{n_vet} vettings, {n_pix} pixel follow-ups, commit {commit[:7]}")
    for x in list(fit_out)[:10]:
        print(f"  fit {x['item']['key']}: from P {x['item']['period']} d, T14 {x['item']['duration_h']} h")
    for x in out[:10]:
        it = x["item"]
        print(f"  {it['key']}: P {it['period']} d, T14 {it['duration_h']} h, depth {it['depth_ppm']} ppm"
              + (f", drop {it['drop']}" if it['drop'] else "") + ("" if x["base_runs"] else "; no runs without a curve")
              + "".join(f"; {c['label']} ({c['filt']})" for c in x["cc"]))
    if len(out) > 10:
        print(f"  ... and {len(out) - 10} more signals on {len({x['item']['tic'] for x in out})} stars in all")
    for x in cs_out:
        r = x["item"]
        print(f"  {r['key']} (tier {r['tier']}): centroids in sectors {r['sectors']}")
    if out:
        print(f"reused from the store: {len(p['reuse']['fold'])} folds, {len(p['reuse']['molusc'])} MOLUSC files; "
              f"{sum(bool(x.get('prior')) for x in out)} signals keep their result if their target setup comes out the same")
    print(f"estimate: {itype} spot at ${price}/h, about {est['hours']} h, about ${est['usd']}; limit {est['limit_hours']} h")
    print(f"launch with: python cloud.py run {bid} --approve")
    return p


# run ----------------------------------------------------------------------------------------------------------------
def _presign(s3, method, key, hours):
    return s3.generate_presigned_url(method, Params=dict(Bucket=AWS["bucket"], Key=key), ExpiresIn=int(hours * 3600))


def kit(p, d, s3, hours):
    prefix = f"batches/{p['id']}/"
    urls = dict(items={x["item"]["key"]: _presign(s3, "put_object", f"{prefix}items/{x['item']['key']}.tgz", hours)
                       for x in p["items"]},
                big={x["item"]["key"]: _presign(s3, "put_object", f"{prefix}items/{x['item']['key']}.big.tgz", hours)
                     for x in p["items"]},
                cs={x["item"]["key"]: _presign(s3, "put_object", f"{prefix}cs/{x['item']['key']}.tgz", hours)
                    for x in p.get("centroids", [])},
                fit={x["item"]["key"]: _presign(s3, "put_object", f"{prefix}fit/{x['item']['key']}.tgz", hours)
                     for x in p.get("fits", [])},
                vet={x["item"]["key"]: _presign(s3, "put_object", f"{prefix}vet/{x['item']['key']}.tgz", hours)
                     for x in p.get("vet", [])},
                pixel={x["item"]["key"]: _presign(s3, "put_object", f"{prefix}pixel/{x['item']['key']}.tgz", hours)
                       for x in p.get("pixel", [])},
                heartbeat=_presign(s3, "put_object", f"{prefix}heartbeat.json", hours),
                done=_presign(s3, "put_object", f"{prefix}done.json", hours),
                logs={n: _presign(s3, "put_object", f"{prefix}logs/{n}", hours)
                      for n in ("worker.log", "download.log", "fleet.log", "molusc.log", "runs.log", "centroids.log",
                                "fits.log", "vet.log", "pixel.log")})
    k = os.path.join(d, "kit")
    shutil.rmtree(k, ignore_errors=True)
    os.makedirs(os.path.join(k, "batch", "reuse", "folds"))
    os.makedirs(os.path.join(k, "batch", "reuse", "molusc"))
    arc = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", p["commit"], "pipeline", "requirements.txt",
                          "requirements-triceratops.txt"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "xf", "-", "-C", k], input=arc, check=True)
    b = os.path.join(k, "batch")
    for f in ("plan.json", "stars.parquet", "gaia.csv", "manifest.parquet"):
        if os.path.exists(os.path.join(d, f)):
            shutil.copyfile(os.path.join(d, f), os.path.join(b, f))
    if p.get("centroids"):
        pd.DataFrame([x["item"] for x in p["centroids"]], columns=centroid_store.LIST_COLUMNS).to_csv(
            os.path.join(b, "cs_list.csv"), index=False)
    with open(os.path.join(b, "urls.json"), "w") as fh:
        json.dump(urls, fh)
    with open(os.path.join(b, "tics.txt"), "w") as fh:
        fh.write("\n".join(sorted({str(x["item"]["tic"]) for x in p["items"] + p.get("fits", []) + p.get("vet", [])})) + "\n")
    if p.get("vet"):                                # the known-object catalogs vet.py matches against
        os.makedirs(os.path.join(b, "known"))
        import vet_store as vs
        for n in vs.KNOWN:
            shutil.copyfile(os.path.join(ROOT, "data", "known", n), os.path.join(b, "known", n))
    if p.get("pixel"):                              # the vetting each follow-up chooses its sectors from
        os.makedirs(os.path.join(b, "vet_dir"))
        s_ = st.Store()
        for x in p["pixel"]:
            it = x["item"]
            shutil.copyfile(os.path.join(s_.path("vet", x["vet_store"]), "vetting.json"),
                            os.path.join(b, "vet_dir", f"tic{it['tic']}_{it['rank']}.json"))
    shutil.copytree(MOLUSC_CODE, os.path.join(b, "molusc_code"))
    os.makedirs(os.path.join(b, "cc"), exist_ok=True)
    for x in p["items"]:
        for c in x.get("cc") or []:
            src = os.path.join(CC_DIR, c["file"])
            if st.file_content(src) != c["content"]:
                raise SystemExit(f"{c['file']} changed since the plan was made")
            shutil.copyfile(src, os.path.join(b, "cc", c["file"]))
    s = st.Store()
    remote = []                                     # large files to fetch from the bucket: archive URL, members, destinations
    for x in p["items"]:
        tic, key = int(x["item"]["tic"]), x["item"]["key"]
        fk = st.key_of(x["fold_request"])
        if s.has("fold", fk):
            shutil.copyfile(os.path.join(s.path("fold", fk), "fold.npz"), os.path.join(b, "reuse", "folds", f"{key}.npz"))
            # the target setup the fold implies (its three most informative sectors), if it is stored
            ranked = s.get("fold", fk)[1].get("sectors_ranked") or []
            secs = ",".join(str(v) for v in sorted(ranked[:3]))
            sk = st.key_of(tri_store.setup_request(tic, secs, x["item"]["depth_ppm"], x.get("star"), p["code"]["tri_setup"],
                                                   p["env"]["tri_setup"], x.get("not_hosts")))
            ent = s.get("tri_setup", sk) if ranked else None
            if ent and ent[1].get("remote"):
                files = ent[1]["remote"]["files"]
                dest = {"state.pkl": f"t2/states/{tic}_{secs.replace(',', '-')}_d{float(x['item']['depth_ppm']):g}.pkl"}
                if "population.csv" in files:
                    dest["population.csv"] = f"t2/cache/{tic}/population.csv"
                dest.update({f"cuts/{n[4:]}": f"t2/cuts/tic{tic}/{n[4:]}" for n in files if n.startswith("cut_")})
                remote.append(dict(url=_presign(s3, "get_object", ent[1]["remote"]["archive"].split("/", 3)[3], hours),
                                   members=dest, state=dest["state.pkl"], population=dest.get("population.csv"),
                                   digest=ent[1]["content"]))
        prior = x.get("prior")
        pent = s.get("tri_setup", prior["setup"]) if prior else None
        if pent and pent[1].get("remote"):          # the setup the result in use ran on: its digest, cutouts and population
            files = pent[1]["remote"]["files"]
            dest = {"state.pkl": f"prior/{key}/state.pkl"}
            if "population.csv" in files:
                dest["population.csv"] = f"prior/{key}/population.csv"
            dest.update({f"cuts/{n[4:]}": f"t2/cuts/tic{tic}/{n[4:]}" for n in files if n.startswith("cut_")})
            remote.append(dict(url=_presign(s3, "get_object", pent[1]["remote"]["archive"].split("/", 3)[3], hours),
                               members=dest, prior=key, tic=tic))
        mk = st.key_of(x["molusc_request"]) if x["molusc_request"] else None
        if mk and s.has("molusc", mk):
            res = s.get("molusc", mk)[1]
            if os.path.exists(os.path.join(s.path("molusc", mk), "molusc.csv.gz")):
                shutil.copyfile(os.path.join(s.path("molusc", mk), "molusc.csv.gz"),
                                os.path.join(b, "reuse", "molusc", f"tic{tic}_kept.csv.gz"))
            elif res.get("remote"):
                remote.append(dict(url=_presign(s3, "get_object", res["remote"]["archive"].split("/", 3)[3], hours),
                                   members={res["remote"].get("member", "molusc.csv.gz"): f"molusc/tic{tic}_kept.csv.gz"}))
            with open(os.path.join(b, "reuse", "molusc", f"tic{tic}_molusc.json"), "w") as fh:
                json.dump(res.get("info") or {}, fh)
        for i, sreq in enumerate(x.get("molusc_samples") or [], start=1):     # the star's further MOLUSC samples
            sk = st.key_of(sreq)
            if not s.has("molusc", sk):
                continue
            res = s.get("molusc", sk)[1]
            os.makedirs(os.path.join(b, "reuse", f"molusc_s{i}"), exist_ok=True)
            if os.path.exists(os.path.join(s.path("molusc", sk), "molusc.csv.gz")):
                shutil.copyfile(os.path.join(s.path("molusc", sk), "molusc.csv.gz"),
                                os.path.join(b, "reuse", f"molusc_s{i}", f"tic{tic}_kept.csv.gz"))
            elif res.get("remote"):
                remote.append(dict(url=_presign(s3, "get_object", res["remote"]["archive"].split("/", 3)[3], hours),
                                   members={res["remote"].get("member", "molusc.csv.gz"): f"molusc_s{i}/tic{tic}_kept.csv.gz"}))
    with open(os.path.join(b, "reuse", "remote.json"), "w") as fh:
        json.dump(remote, fh)
    tgz = os.path.join(d, "kit.tgz")
    with tarfile.open(tgz, "w:gz") as tf:
        for name in sorted(os.listdir(k)):
            tf.add(os.path.join(k, name), arcname=name)
    return tgz


def user_data(kit_url, boot_url, limit_min):
    """The instance's start: a hard stop at the time limit, the kit, the worker as a systemd unit of its own (a process
    left behind by cloud-init's last stage can be stopped with it), and the boot log uploaded for diagnosis."""
    return f"""#!/bin/bash
exec > /var/log/exo-batch-boot.log 2>&1
set -x
shutdown -h +{limit_min}
sudo -u ec2-user curl -fsS --retry 5 -o /home/ec2-user/kit.tgz "{kit_url}"
sudo -u ec2-user bash -c 'cd ~/exo && rm -rf pipeline batch && tar xzf ~/kit.tgz'
systemd-run --unit=exo-batch --uid=ec2-user --gid=ec2-user --working-directory=/home/ec2-user/exo \\
  --setenv=HOME=/home/ec2-user /home/ec2-user/exo/.venv/bin/python pipeline/cloud_worker.py batch
sleep 20
systemctl status exo-batch --no-pager
curl -sS -X PUT -T /var/log/exo-batch-boot.log "{boot_url}"
"""


def launch(p, d, kit_url, boot_url, limit_min, itype):
    ec2 = aws().client("ec2")
    r = ec2.run_instances(
        ImageId=AWS["ami"], InstanceType=itype, KeyName=AWS["key"], MinCount=1, MaxCount=1,
        NetworkInterfaces=[dict(DeviceIndex=0, SubnetId=AWS["subnet"], Groups=[AWS["sg"]], AssociatePublicIpAddress=True)],
        InstanceMarketOptions=dict(MarketType="spot", SpotOptions=dict(SpotInstanceType="one-time",
                                                                       InstanceInterruptionBehavior="terminate")),
        InstanceInitiatedShutdownBehavior="terminate",
        BlockDeviceMappings=[dict(DeviceName="/dev/xvda", Ebs=dict(VolumeSize=60, VolumeType="gp3", DeleteOnTermination=True))],
        UserData=user_data(kit_url, boot_url, limit_min),
        TagSpecifications=[dict(ResourceType="instance", Tags=[dict(Key="project", Value="exoplanets"),
                                                               dict(Key="batch", Value=p["id"]),
                                                               dict(Key="Name", Value=f"exo-{p['id']}")])])
    iid = r["Instances"][0]["InstanceId"]
    with open(os.path.join(d, "instance.json"), "w") as fh:
        json.dump(dict(instance_id=iid, type=itype, launched=time.time()), fh)
    return iid


def terminate(bid, iid):
    """Terminates the batch's own instance: its ID as launched, and its batch tag checked first."""
    ec2 = aws().client("ec2")
    r = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
    tags = {t["Key"]: t["Value"] for t in r.get("Tags", [])}
    if tags.get("batch") != bid:
        raise RuntimeError(f"{iid} is not tagged batch={bid}; not terminating it")
    if r["State"]["Name"] not in ("terminated", "shutting-down"):
        ec2.terminate_instances(InstanceIds=[iid])
    return r["State"]["Name"]


def ingest(bid, store_root=st.ROOT, quiet=False):
    """Downloads and stores (in store_root) the items the batch has uploaded that are not yet ingested. Returns
    {key: {store, problems}}."""
    d = os.path.join(BATCHES, bid)
    p = json.load(open(os.path.join(d, "plan.json")))
    s3 = s3client()
    prefix = f"batches/{bid}/items/"
    # what has gone into which store: a batch can be ingested into a trial store first and the main one later
    done_path = os.path.join(d, "ingested.json")
    ledger = json.load(open(done_path)) if os.path.exists(done_path) else {}
    root = os.path.abspath(store_root)
    done = ledger.setdefault(root, {})
    by_key = {x["item"]["key"]: x for x in p["items"]}
    by_cs = {x["item"]["key"]: x for x in p.get("centroids", [])}
    by_fit = {x["item"]["key"]: x for x in p.get("fits", [])}
    by_vet = {x["item"]["key"]: x for x in p.get("vet", [])}
    by_pix = {x["item"]["key"]: x for x in p.get("pixel", [])}
    store = st.Store(store_root)
    pages = s3.get_paginator("list_objects_v2")     # a listing holds at most 1,000 keys
    objs = [o for sub in ("items/", "cs/", "fit/", "vet/", "pixel/") for page in pages.paginate(
            Bucket=AWS["bucket"], Prefix=f"batches/{bid}/{sub}") for o in page.get("Contents", [])]
    for o in objs:
        if o["Key"].endswith(".big.tgz"):           # the large files stay in the bucket
            continue
        kind = next((k for k in ("cs", "fit", "vet", "pixel") if f"/{k}/" in o["Key"]), "tri")
        key = os.path.basename(o["Key"])[:-4]
        rec = key if kind == "tri" else f"{kind}:{key}"
        if rec in done or key not in {"cs": by_cs, "fit": by_fit, "vet": by_vet, "pixel": by_pix, "tri": by_key}[kind]:
            continue
        cs = kind == "cs"
        idir = os.path.join(d, {"cs": "cs", "fit": "fits", "vet": "vet", "pixel": "pixel", "tri": "items"}[kind], key)
        shutil.rmtree(idir, ignore_errors=True)
        os.makedirs(idir)
        arc = idir + ".tgz"
        s3.download_file(AWS["bucket"], o["Key"], arc)
        with tarfile.open(arc) as tf:
            tf.extractall(idir, filter="data")
        try:
            if kind == "fit":
                item = dict(by_fit[key], env=p["fit_env"], commit=p["commit"])
                tkey, problems = fit_store.ingest_item(store, idir, item, bid, int(time.time()))
            elif kind in ("vet", "pixel"):
                import vet_store
                item = dict((by_vet if kind == "vet" else by_pix)[key], env=p["fit_env"], commit=p["commit"])
                tkey, problems = vet_store.ingest_item(store, idir, item, kind, bid, int(time.time()))
            elif cs:
                item = dict(by_cs[key], env=p["centroid_env"], commit=p["commit"])
                tkey, problems = centroid_store.ingest_item(store, idir, item, bid, int(time.time()))
            else:
                item = dict(by_key[key], code=p["code"], env=p["env"], commit=p["commit"])
                tkey, problems = tri_store.ingest_item(store, idir, item, bid, int(time.time()), n_runs=p["runs"],
                                                       remote_archive=f"s3://{AWS['bucket']}/{o['Key'][:-4]}.big.tgz")
        except Exception as ex:                     # recorded, not retried: remove it from ingested.json to try again
            tkey, problems = None, [f"ingest failed: {ex!r}"]
        key = rec
        done[key] = dict(store=tkey, problems=problems)
        with open(done_path, "w") as fh:
            json.dump(ledger, fh, indent=1)
        if not quiet:
            print(f"  {key}: stored {tkey[:12]}" + (f"; FAILED CHECKS: {problems}" if problems else ""), flush=True)
    return done


def run(bid, hours=None, store_root=st.ROOT):
    d = os.path.join(BATCHES, bid)
    p = json.load(open(os.path.join(d, "plan.json")))
    if os.path.exists(os.path.join(d, "instance.json")):
        raise SystemExit(f"batch {bid} was launched already (instance.json); use ingest")
    itype = p["estimate"]["instance"]
    limit_h = hours or p["estimate"]["limit_hours"]
    s3 = s3client()
    tgz = kit(p, d, s3, limit_h + 2)
    s3.upload_file(tgz, AWS["bucket"], f"batches/{bid}/kit.tgz")
    kit_url = _presign(s3, "get_object", f"batches/{bid}/kit.tgz", 1)
    boot_url = _presign(s3, "put_object", f"batches/{bid}/logs/boot.log", 1)
    iid = launch(p, d, kit_url, boot_url, int(limit_h * 60), itype)
    follow(bid, store_root, limit_h)


def follow(bid, store_root=st.ROOT, limit_h=None):
    """Follows a launched batch: ingests each item as it arrives, and terminates the instance when every item is in,
    when it stops sending heartbeats, or at the time limit. Also resumes a batch whose follower stopped."""
    d = os.path.join(BATCHES, bid)
    p = json.load(open(os.path.join(d, "plan.json")))
    inst = json.load(open(os.path.join(d, "instance.json")))
    iid = inst["instance_id"]
    limit_h = limit_h or p["estimate"]["limit_hours"]
    s3 = s3client()
    t0 = inst["launched"]
    now = datetime.now().astimezone().strftime("%H:%M %Z")     # the local time of the machine following
    print(f"batch {bid}: following {iid} ({inst['type']}) from {now}; limit {limit_h} h", flush=True)
    keys = ({x["item"]["key"] for x in p["items"]} | {f"cs:{x['item']['key']}" for x in p.get("centroids", [])}
            | {f"fit:{x['item']['key']}" for x in p.get("fits", [])} | {f"vet:{x['item']['key']}" for x in p.get("vet", [])}
            | {f"pixel:{x['item']['key']}" for x in p.get("pixel", [])})
    last_beat, status = t0, "running"
    try:
        while True:
            time.sleep(30)
            try:
                done = ingest(bid, store_root)
            except Exception as ex:                 # a network error: try again on the next round
                print(f"ingest round failed: {ex!r}", flush=True)
                continue
            try:
                hb = s3.get_object(Bucket=AWS["bucket"], Key=f"batches/{bid}/heartbeat.json")
                beat = json.loads(hb["Body"].read())
                last_beat = hb["LastModified"].timestamp()
                stage = beat.get("stage")
            except s3.exceptions.NoSuchKey:
                stage = "no heartbeat yet"
            ended = s3.list_objects_v2(Bucket=AWS["bucket"], Prefix=f"batches/{bid}/done.json").get("KeyCount", 0)
            el = (time.time() - t0) / 60
            print(f"{el:5.1f} min: {stage}; {len(done)} of {len(keys)} stored", flush=True)
            if ended or keys <= set(done):
                status = "finished"
                break
            if time.time() - last_beat > 20 * 60 and el > 25:
                status = "no heartbeat for 20 minutes"
                break
            if el > limit_h * 60:
                status = "time limit"
                break
    finally:
        time.sleep(5)
        try:
            done = ingest(bid, store_root)
        except Exception as ex:
            print(f"last ingest failed: {ex!r}; run `cloud.py ingest {bid}` later", flush=True)
            done = {}
        state = terminate(bid, iid)
        fetch_logs(s3, bid, d)
        bad = {k: v["problems"] for k, v in done.items() if v["problems"]}
        print(f"batch {bid}: {status}; instance {iid} was {state}, terminated; {len(done)} of {len(keys)} stored"
              + (f"; failed checks: {bad}" if bad else "") + f"; {(time.time() - t0) / 60:.1f} min")
        print("next: cd pipeline && ../.venv/bin/python -m dag run")


def fetch_logs(s3, bid, d):
    """The instance's logs and its last state (done.json) into the batch's logs/."""
    os.makedirs(os.path.join(d, "logs"), exist_ok=True)
    keys = [o["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket=AWS["bucket"], Prefix=f"batches/{bid}/logs/")
            for o in page.get("Contents", [])] + [f"batches/{bid}/done.json"]
    for k in keys:
        try:
            s3.download_file(AWS["bucket"], k, os.path.join(d, "logs", os.path.basename(k)))
        except Exception as ex:
            print(f"no {k}: {ex!r}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "run", "follow", "ingest"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--keys", default="")
    ap.add_argument("--type", default="c8g.4xlarge")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--cc", action="store_true", help="add runs with each contrast curve of the star")
    ap.add_argument("--no-base", action="store_true", help="only the runs with contrast curves")
    ap.add_argument("--centroids", action="store_true", help="a batch of per-sector centroid measurements")
    ap.add_argument("--rerun-legacy", action="store_true", help="every legacy result in use, computed again")
    ap.add_argument("--parts", type=int, default=1, help="split into this many batches (one instance each)")
    ap.add_argument("--fits", action="store_true", help="a batch of transit fits")
    ap.add_argument("--vet", action="store_true", help="a batch of vettings (vet.py) of rows with out-of-date ones")
    ap.add_argument("--pixel", action="store_true", help="a batch of pixel follow-ups (followup.py)")
    ap.add_argument("--molusc-sample", type=int, default=0,
                    help="k > 0: the runs with MOLUSC sample k instead of the catalog's (molusc_sample.py); run such a batch "
                         "into a store of its own (--store)")
    ap.add_argument("--hours", type=float)
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--store", default=st.ROOT, help="store to ingest into (a trial can use its own)")
    a = ap.parse_args()
    if a.cmd == "plan":
        plan([k for k in a.keys.split(",") if k] or None, a.type, a.runs, a.cc, not a.no_base, a.centroids, a.rerun_legacy,
             a.parts, a.fits, a.molusc_sample, a.vet, a.pixel)
    elif a.cmd == "run":
        if not a.approve:
            p = json.load(open(os.path.join(BATCHES, a.id, "plan.json")))
            sys.exit(f"batch {a.id}: {len(p['items'])} signals, estimate {p['estimate']}. Nothing launched: add --approve.")
        run(a.id, a.hours, a.store)
    elif a.cmd == "follow":
        follow(a.id, a.store, a.hours)
    else:
        print(f"{len(ingest(a.id, a.store))} items ingested")


if __name__ == "__main__":
    main()
