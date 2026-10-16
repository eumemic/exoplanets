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
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

import centroid_store
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
    """The light-curve list of each star: the re-search manifests (fixed QLP reader) where they have the star, else
    the full-sky and earlier ones, as every batch since 15 October."""
    ids = list(set(tics))
    rd = lambda f: pd.read_parquet(f, filters=[("tic", "in", ids)])
    new = pd.concat([rd(f) for f in sorted(glob.glob(os.path.join(ROOT, "results_cloud", "qfull_kits", "manifest_shard*.parquet")))])
    old = pd.concat([rd(f) for f in sorted(glob.glob(os.path.join(ROOT, "results_cloud", "manifests_allsky", "manifest_shard*.parquet")))]
                    + [rd(os.path.join(ROOT, "data", "catalogs", f"{n}.parquet")) for n in
                       ("manifest_prelim", "manifest_toi", "manifest_tce", "manifest_faint_t1", "manifest_faint_t2")])
    new = new[[c for c in new.columns if not c.startswith("__")]]
    old = old[[c for c in old.columns if not c.startswith("__")]]
    return pd.concat([new, old[~old.tic.isin(set(new.tic))]]).drop_duplicates(["tic", "sector", "prov"])


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
        stale = {(int(x.split()[1]), x.split()[3]) for x in cc.centroid_inputs_current(
            os.path.join(ROOT, "results_public", "products", "centroids.csv"),
            os.path.join(ROOT, "results_public", "products", "measurements_allsky.csv"), tol)}
        need = a.tier.isin(P["catalog.counted_allsky"]) & a.cs_sectors.isna()
        sel = a[need | [(t, f"{p}") in stale for t, p in zip(a.TIC, a.P_d)]]
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


def tri_items(keys, cc, base):
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
    for it in items:
        tic = int(it["tic"])
        lcs = [[int(r.sector), str(r.prov), float(r.exptime), str(r.uri)] for r in man[man.tic == tic].itertuples()]
        freq = tri_store.fold_request(it, lcs, code["fold"], env["fold"])
        star = stars[stars.ID == tic].iloc[0]
        mreq = None
        if star.GAIA_DR3 in gaia_by.index and float(star["mass"]) > 0:
            row = {k: (v.item() if hasattr(v, "item") else v) for k, v in gaia_by.loc[star.GAIA_DR3].to_dict().items()}
            mreq = tri_store.molusc_request(tic, dict(row, source_id=int(star.GAIA_DR3)), float(star["mass"]), mcode,
                                           code["molusc"], env["molusc"])
        if s.has("fold", st.key_of(freq)):
            reuse["fold"].append(it["key"])
        if mreq and s.has("molusc", st.key_of(mreq)):
            reuse["molusc"].append(tic)
        cs = curves(tic) if cc else []
        if not base and not cs:
            raise SystemExit(f"{it['key']}: --no-base, and no contrast curve for TIC {tic}")
        out.append(dict(item=it, fold_request=freq, molusc_request=mreq, base_runs=base, cc=cs))
    return out, stars, gaia, man, dict(reuse, code=code, env=env)


def plan(keys=None, itype="c8g.4xlarge", runs=10, cc=False, base=True, centroids=False):
    """A batch: TRICERATOPS signals, or (centroids) per-sector centroid measurements. Writes its plan.json."""
    if git("status", "--porcelain", "--", "pipeline", "requirements.txt", "requirements-triceratops.txt"):
        raise SystemExit("pipeline/ or a lock file has uncommitted changes: the kit ships a commit, so commit first")
    commit = git("rev-parse", "HEAD")
    out, cs_out, stars, gaia, man, extra = [], [], None, None, None, {}
    if centroids:
        ccode, cenv = centroid_store.code_hash(), tri_store.env_hash("fold")
        cs_out = [dict(item=r, request=centroid_store.request(r, ccode, cenv)) for r in centroid_rows(keys)]
        if not cs_out:
            print("nothing to measure: every counted candidate has a current per-sector centroid measurement")
            return None
    else:
        out, stars, gaia, man, extra = tri_items(keys, cc, base)
        if not out:
            print("nothing to run: no row of triceratops_plan.csv is pending or stale")
            return None
    bid = "b" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    d = os.path.join(BATCHES, bid)
    os.makedirs(d)
    if out:
        stars.to_parquet(os.path.join(d, "stars.parquet"))
        gaia.to_csv(os.path.join(d, "gaia.csv"), index=False)
        man.to_parquet(os.path.join(d, "manifest.parquet"))
    price, vc = spot_price(itype), VCPUS.get(itype, 16)
    # measured: two TRICERATOPS signals in ~5 min on 16 vCPUs, nine contrast-curve variants in ~10 min; a run takes 20-90 s
    # of one core; a centroid measurement ~1-3 min per signal on one core (t10: 12 signals in ~4 min with 6 processes)
    variants = sum(int(x["base_runs"]) + len(x["cc"]) for x in out)
    hours = (15 + variants * 2 * runs * 1.0 / max(1, vc - 1) + len(cs_out) * 2.0 / 6) / 60
    est = dict(instance=itype, spot_usd_per_h=price, hours=round(hours, 2), usd=round(price * hours, 2) if price else None,
               limit_hours=round(max(1.0, 3 * hours), 1))
    p = dict(id=bid, commit=commit, created=datetime.now(timezone.utc).isoformat(timespec="seconds"), runs=runs,
             code=extra.get("code", {}), env=extra.get("env", {}), items=out, centroids=cs_out,
             centroid_env=tri_store.env_hash("fold"), reuse={k: extra.get(k, []) for k in ("fold", "molusc")}, estimate=est)
    with open(os.path.join(d, "plan.json"), "w") as fh:
        json.dump(p, fh, indent=1)
    print(f"batch {bid}: {len(out)} TRICERATOPS signals, {len(cs_out)} centroid measurements, commit {commit[:7]}")
    for x in out:
        it = x["item"]
        print(f"  {it['key']}: P {it['period']} d, T14 {it['duration_h']} h, depth {it['depth_ppm']} ppm"
              + (f", drop {it['drop']}" if it['drop'] else "") + ("" if x["base_runs"] else "; no runs without a curve")
              + "".join(f"; {c['label']} ({c['filt']})" for c in x["cc"]))
    for x in cs_out:
        r = x["item"]
        print(f"  {r['key']} (tier {r['tier']}): centroids in sectors {r['sectors']}")
    if out:
        print(f"reused from the store: {len(p['reuse']['fold'])} folds, {len(p['reuse']['molusc'])} MOLUSC files")
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
                cs={x["item"]["key"]: _presign(s3, "put_object", f"{prefix}cs/{x['item']['key']}.tgz", hours)
                    for x in p.get("centroids", [])},
                heartbeat=_presign(s3, "put_object", f"{prefix}heartbeat.json", hours),
                done=_presign(s3, "put_object", f"{prefix}done.json", hours),
                logs={n: _presign(s3, "put_object", f"{prefix}logs/{n}", hours)
                      for n in ("worker.log", "download.log", "fleet.log", "molusc.log", "runs.log", "centroids.log")})
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
        fh.write("\n".join(sorted({str(x["item"]["tic"]) for x in p["items"]})) + "\n")
    shutil.copytree(MOLUSC_CODE, os.path.join(b, "molusc_code"))
    os.makedirs(os.path.join(b, "cc"), exist_ok=True)
    for x in p["items"]:
        for c in x.get("cc") or []:
            src = os.path.join(CC_DIR, c["file"])
            if st.file_content(src) != c["content"]:
                raise SystemExit(f"{c['file']} changed since the plan was made")
            shutil.copyfile(src, os.path.join(b, "cc", c["file"]))
    s = st.Store()
    for x in p["items"]:
        fk = st.key_of(x["fold_request"])
        if s.has("fold", fk):
            shutil.copyfile(os.path.join(s.path("fold", fk), "fold.npz"), os.path.join(b, "reuse", "folds", f"{x['item']['key']}.npz"))
        if x["molusc_request"] and s.has("molusc", st.key_of(x["molusc_request"])):
            md = s.path("molusc", st.key_of(x["molusc_request"]))
            tic = x["item"]["tic"]
            shutil.copyfile(os.path.join(md, "molusc.csv.gz"), os.path.join(b, "reuse", "molusc", f"tic{tic}_kept.csv.gz"))
            info = s.get("molusc", st.key_of(x["molusc_request"]))[1].get("info") or {}
            with open(os.path.join(b, "reuse", "molusc", f"tic{tic}_molusc.json"), "w") as fh:
                json.dump(info, fh)
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
    store = st.Store(store_root)
    objs = s3.list_objects_v2(Bucket=AWS["bucket"], Prefix=prefix).get("Contents", []) + \
        s3.list_objects_v2(Bucket=AWS["bucket"], Prefix=f"batches/{bid}/cs/").get("Contents", [])
    for o in objs:
        cs = "/cs/" in o["Key"]
        key = os.path.basename(o["Key"])[:-4]
        rec = f"cs:{key}" if cs else key
        if rec in done or key not in (by_cs if cs else by_key):
            continue
        idir = os.path.join(d, "cs" if cs else "items", key)
        shutil.rmtree(idir, ignore_errors=True)
        os.makedirs(idir)
        arc = idir + ".tgz"
        s3.download_file(AWS["bucket"], o["Key"], arc)
        with tarfile.open(arc) as tf:
            tf.extractall(idir, filter="data")
        if cs:
            item = dict(by_cs[key], env=p["centroid_env"], commit=p["commit"])
            tkey, problems = centroid_store.ingest_item(store, idir, item, bid, int(time.time()))
        else:
            item = dict(by_key[key], code=p["code"], env=p["env"], commit=p["commit"])
            tkey, problems = tri_store.ingest_item(store, idir, item, bid, int(time.time()), n_runs=p["runs"])
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
    t0 = time.time()
    from zoneinfo import ZoneInfo
    pt = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%H:%M %Z")
    print(f"batch {bid}: launched {iid} ({itype}) at {pt}; limit {limit_h} h", flush=True)
    keys = {x["item"]["key"] for x in p["items"]} | {f"cs:{x['item']['key']}" for x in p.get("centroids", [])}
    last_beat, status = t0, "running"
    try:
        while True:
            time.sleep(30)
            done = ingest(bid, store_root)
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
        done = ingest(bid, store_root)
        state = terminate(bid, iid)
        os.makedirs(os.path.join(d, "logs"), exist_ok=True)
        for o in s3.list_objects_v2(Bucket=AWS["bucket"], Prefix=f"batches/{bid}/").get("Contents", []):
            if "/logs/" in o["Key"] or o["Key"].endswith("done.json"):
                s3.download_file(AWS["bucket"], o["Key"], os.path.join(d, "logs", os.path.basename(o["Key"])))
        bad = {k: v["problems"] for k, v in done.items() if v["problems"]}
        print(f"batch {bid}: {status}; instance {iid} was {state}, terminated; {len(done)} of {len(keys)} stored"
              + (f"; failed checks: {bad}" if bad else "") + f"; {(time.time() - t0) / 60:.1f} min")
        print("next: cd pipeline && ../.venv/bin/python -m dag run")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["plan", "run", "ingest"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--keys", default="")
    ap.add_argument("--type", default="c8g.4xlarge")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--cc", action="store_true", help="add runs with each contrast curve of the star")
    ap.add_argument("--no-base", action="store_true", help="only the runs with contrast curves")
    ap.add_argument("--centroids", action="store_true", help="a batch of per-sector centroid measurements")
    ap.add_argument("--hours", type=float)
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--store", default=st.ROOT, help="store to ingest into (a trial can use its own)")
    a = ap.parse_args()
    if a.cmd == "plan":
        plan([k for k in a.keys.split(",") if k] or None, a.type, a.runs, a.cc, not a.no_base, a.centroids)
    elif a.cmd == "run":
        if not a.approve:
            p = json.load(open(os.path.join(BATCHES, a.id, "plan.json")))
            sys.exit(f"batch {a.id}: {len(p['items'])} signals, estimate {p['estimate']}. Nothing launched: add --approve.")
        run(a.id, a.hours, a.store)
    else:
        print(f"{len(ingest(a.id, a.store))} items ingested")


if __name__ == "__main__":
    main()
