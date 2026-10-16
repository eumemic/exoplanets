"""Runs a TRICERATOPS batch of cloud.py on its instance and uploads each finished signal as soon as it is finished.

The kit, unpacked over the AMI's checkout (~/exo), holds the code of one commit (git archive) and batch/: plan.json (the
signals and their requests), urls.json (presigned upload URLs: one per signal, a heartbeat, the log and the end), the
snapshots the stages read (stars.parquet: TIC rows; gaia.csv: Gaia DR3 rows; manifest.parquet: the light-curve list),
MOLUSC's code, and in reuse/ the folds and MOLUSC files the store already has, which the stages below then skip.

Steps: check both environments against their lock files (a mismatch stops the batch, since the results would not be
what the requests say); download the light curves; MOLUSC (seeded from the star) while the folds, cutouts and target
setups are made (fpp_fleet.py); then the runs (fpp_pool.py), in chunks of signals so that each chunk's results are
uploaded when it ends: a spot interruption loses only the chunk in flight. Each signal's archive holds its fold, target
setup (with the field-star population and the trimmed cutouts), MOLUSC file, runs and result, and item.json with the
checks of fpp_check.gate, the commit and the environments. A heartbeat goes up every minute. At the end the instance
shuts down (and so terminates).

Usage (on the instance, from ~/exo): .venv/bin/python pipeline/cloud_worker.py batch
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request

HOME = os.path.expanduser("~")
EXO = os.path.join(HOME, "exo")
PIPE = os.path.join(EXO, "pipeline")
VENVS = {"requirements.txt": ".venv", "requirements-triceratops.txt": ".venv-trice"}
ENV = dict(os.environ, EXO_DATA_SOURCE="s3", OMP_NUM_THREADS="1", NUMBA_NUM_THREADS="1", MKL_NUM_THREADS="1",
           OPENBLAS_NUM_THREADS="1")
STATE = {"stage": "starting", "uploaded": [], "failed": [], "t0": time.time()}


def log(msg):
    line = f"{time.strftime('%H:%M:%S', time.gmtime())} {msg}"
    print(line, flush=True)
    with open(os.path.join(HOME, "worker.log"), "a") as fh:
        fh.write(line + "\n")


def put(url, data, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, method="PUT", headers={"Content-Type": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status in (200, 204):
                    return True
        except Exception as ex:
            log(f"upload failed ({ex!r}), attempt {i + 1}")
            time.sleep(5 * (i + 1))
    return False


def heartbeat(urls, stop):
    while not stop.wait(60):
        put(urls["heartbeat"], json.dumps(dict(STATE, now=time.time())).encode())


def _norm(n):
    return re.sub(r"[-_.]+", "-", n).lower()


def pins(text):
    """{normalised name: version} of the name==version lines of a lock file (other lines, such as a git URL, are
    left out)."""
    lines = (x.split(";")[0].strip() for x in text.splitlines())
    return {_norm(n): v.strip() for n, v in (a.split("==", 1) for a in lines if "==" in a and not a.startswith("#"))}


def check_env():
    """{lock file: its sha256 if every pin is installed at that version, else 'mismatch: ...'}."""
    out = {}
    for lock, venv in VENVS.items():
        text = open(os.path.join(EXO, lock)).read()
        pins_ = pins(text)
        got = json.loads(subprocess.run(
            [os.path.join(EXO, venv, "bin", "python"), "-c",
             "import importlib.metadata as m, json; print(json.dumps({d.metadata['Name']: d.version for d in m.distributions()}))"],
            capture_output=True, text=True, check=True).stdout)
        got = {_norm(k): v for k, v in got.items()}
        bad = [f"{k} {v} (installed {got.get(k)})" for k, v in pins_.items() if got.get(k) != v]
        out[lock] = hashlib.sha256(text.encode()).hexdigest() if not bad else "mismatch: " + ", ".join(bad[:10])
    return out


def run(cmd, logname, py=".venv", **kw):
    with open(os.path.join(HOME, logname), "a") as fh:
        return subprocess.run([os.path.join(EXO, py, "bin", "python")] + cmd, cwd=PIPE, env=ENV, stdout=fh,
                              stderr=subprocess.STDOUT, **kw).returncode


def _gate(fpp_path, runs, fold_npz, duration_h):
    import numpy as np
    import fpp_check
    f = np.load(fold_npz)
    problems, deg = fpp_check.gate(json.load(open(fpp_path)), runs, f["time"], int(f["cadence_s"]), duration_h)
    return dict(passed=not problems, problems=problems, degenerate=deg)


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _gz_sha(path):
    import gzip
    with gzip.open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def pack(item, R, jobs, info, urls, base=True, cc=()):
    """Check, pack and upload one signal: a small archive the ingest reads (fold, results, runs, item.json with the
    checks and the hashes of the large files) and a large one that stays in the bucket (target setup with its
    field-star population and trimmed cutouts, MOLUSC file). Returns True if both were uploaded."""
    sys.path.insert(0, PIPE)
    key, tic = item["key"], int(item["tic"])
    t2 = os.path.join(R, "t2")
    job = jobs.get(key)
    variants = ([("", key)] if base else []) + [(lab, f"{key}__{lab}") for lab in cc]
    done = [(lab, jk) for lab, jk in variants if os.path.exists(os.path.join(t2, f"{jk}_fpp.json"))]
    if not (done and job):
        return False
    d, big = os.path.join(R, "items", key), os.path.join(R, "items", key + ".big")
    for x in (d, big):
        shutil.rmtree(x, ignore_errors=True)
    os.makedirs(d)
    os.makedirs(os.path.join(big, "cuts"))
    shutil.copyfile(os.path.join(t2, "folds", f"{key}.npz"), os.path.join(d, "fold.npz"))
    shutil.copyfile(os.path.join(t2, "states", f"{tic}_{job['sectors'].replace(',', '-')}.pkl"), os.path.join(big, "state.pkl"))
    pops = sorted(glob.glob(os.path.join(t2, "cache", str(tic), "*gaia_background.csv")))
    if pops:
        shutil.copyfile(pops[0], os.path.join(big, "population.csv"))
    for c in sorted(glob.glob(os.path.join(t2, "cuts", f"tic{tic}", "*.fits"))):
        shutil.copyfile(c, os.path.join(big, "cuts", os.path.basename(c)))
    molusc = None
    if os.path.exists(os.path.join(R, "molusc", f"tic{tic}_kept.csv.gz")):
        shutil.copyfile(os.path.join(R, "molusc", f"tic{tic}_kept.csv.gz"), os.path.join(big, "molusc.csv.gz"))
        molusc = _gz_sha(os.path.join(big, "molusc.csv.gz"))
    if os.path.exists(os.path.join(R, "molusc", f"tic{tic}_molusc.json")):
        shutil.copyfile(os.path.join(R, "molusc", f"tic{tic}_molusc.json"), os.path.join(d, "molusc.json"))
    # the setup's content: the hashes of its files by name, as tri_store.ingest_item defines it
    sfiles = {"state.pkl": os.path.join(big, "state.pkl")}
    if pops:
        sfiles["population.csv"] = os.path.join(big, "population.csv")
    for c in sorted(glob.glob(os.path.join(big, "cuts", "*.fits"))):
        sfiles[f"cut_{os.path.basename(c)}"] = c
    files = {n: dict(sha256=_sha(p), size=os.path.getsize(p)) for n, p in sfiles.items()}
    from dag.hashing import sha256_json
    setup_content = sha256_json([files[n]["sha256"] for n in sorted(files)])
    lines = [json.loads(x) for x in open(os.path.join(t2, "runs.jsonl"))]
    checks = {}
    for lab, jk in done:
        out = os.path.join(d, "cc", lab) if lab else d
        os.makedirs(out, exist_ok=True)
        shutil.copyfile(os.path.join(t2, f"{jk}_fpp.json"), os.path.join(out, "fpp.json"))
        runs = [r for r in lines if r["key"] == jk]
        with open(os.path.join(out, "runs.jsonl"), "w") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in runs)
        checks[lab or "base"] = _gate(os.path.join(out, "fpp.json"), runs, os.path.join(d, "fold.npz"), item["duration_h"])
    json.dump(dict(info, key=key, tic=tic, sectors=job["sectors"], base=any(lab == "" for lab, _ in done),
                   cc=[lab for lab, _ in done if lab], check=checks, setup_files=files, setup_content=setup_content,
                   molusc_content=molusc, remote=True), open(os.path.join(d, "item.json"), "w"))
    ok = True
    for src, url in ((big, urls["big"][key]), (d, urls["items"][key])):      # the large archive first
        arc = src + ".tgz"
        with tarfile.open(arc, "w:gz") as tf:
            tf.add(src, arcname=".")
        ok = put(url, open(arc, "rb").read()) and ok
    bad = {k: v["problems"] for k, v in checks.items() if v["problems"]}
    log(f"{key}: {'uploaded' if ok else 'UPLOAD FAILED'} ({', '.join(lab or 'base' for lab, _ in done)})"
        + (f"; checks: {bad}" if bad else ""))
    return ok


def fetch_reused(B, R):
    """The stored target setups and MOLUSC files this batch reuses, from their archives in the bucket. A reused
    setup's population file is put where this machine keeps it, and the pickled target is pointed at it."""
    path = os.path.join(B, "reuse", "remote.json")
    items = json.load(open(path)) if os.path.exists(path) else []
    fix = []
    for i, x in enumerate(items):
        arc = os.path.join(R, f"reuse_{i}.tgz")
        with urllib.request.urlopen(x["url"], timeout=300) as r, open(arc, "wb") as fh:
            shutil.copyfileobj(r, fh)
        with tarfile.open(arc) as tf:
            for member, dest in x["members"].items():
                f = tf.extractfile("./" + member) if "./" + member in tf.getnames() else tf.extractfile(member)
                os.makedirs(os.path.dirname(os.path.join(R, dest)), exist_ok=True)
                with open(os.path.join(R, dest), "wb") as out:
                    shutil.copyfileobj(f, out)
        if x.get("state"):
            fix.append([os.path.join(R, x["state"]), os.path.join(R, x["population"]) if x.get("population") else ""])
    if fix:
        script = ("import json, sys; sys.path.insert(0, %r); import fpp_core as fc\n"
                  "for st, pop in json.loads(sys.argv[1]):\n"
                  "    t = fc.load_state(st); t.trilegal_fname = pop or None; fc.save_state(t, st)\n") % PIPE
        subprocess.run([os.path.join(EXO, ".venv-trice", "bin", "python"), "-c", script, json.dumps(fix)], check=True, env=ENV)
    log(f"reused from the bucket: {len(items)} archives ({len(fix)} target setups)")


def run_fits(plan, B, R, info, urls, procs):
    """The batch's transit fits (fit_transit.py, seeded from the request), several at a time, each uploaded when done."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(os.path.join(R, "fits"), exist_ok=True)

    def one(x):
        it, req = x["item"], x["request"]
        out = os.path.join(R, "fits", f"{it['key']}.json")
        masks = [m for m in str(it.get("masks") or "").split(";") if m]
        rc = run(["fit_transit.py", str(it["tic"]), str(it["period"]), str(it["t0"]), str(it["duration_h"]), "--steps",
                  str(req["steps"]), "--seed", str(req["seed"]), "--stars", os.path.join(B, "stars.parquet"), "--out", out]
                 + (["--mask", *masks] if masks else []), "fits.log")
        key = it["key"]
        if rc != 0 or not os.path.exists(out):
            STATE["failed"].append(f"fit:{key}")
            log(f"fit {key}: failed (exit {rc})")
            return
        d = os.path.join(R, "fit_items", key)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(out, os.path.join(d, "fit.json"))
        json.dump(dict(info, key=key), open(os.path.join(d, "item.json"), "w"))
        arc = d + ".tgz"
        with tarfile.open(arc, "w:gz") as tf:
            tf.add(d, arcname=".")
        ok = put(urls["fit"][key], open(arc, "rb").read())
        (STATE["uploaded"] if ok else STATE["failed"]).append(f"fit:{key}")
        log(f"fit {key}: {'uploaded' if ok else 'UPLOAD FAILED'}")

    with ThreadPoolExecutor(max(1, procs)) as ex:
        list(ex.map(one, plan["fits"]))


def return_after_centroids(proc, plan, R, info, urls):
    """Waits for the centroid measurements and uploads each signal's file."""
    if proc is None:
        return
    proc.wait()
    log(f"centroids exit {proc.returncode}")
    for x in plan["centroids"]:
        key = x["item"]["key"]
        f = os.path.join(R, "cs", f"{key}.json")
        if not os.path.exists(f):
            STATE["failed"].append(f"cs:{key}")
            continue
        d = os.path.join(R, "cs_items", key)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(f, os.path.join(d, f"{key}.json"))
        json.dump(dict(info, key=key), open(os.path.join(d, "item.json"), "w"))
        arc = d + ".tgz"
        with tarfile.open(arc, "w:gz") as tf:
            tf.add(d, arcname=".")
        ok = put(urls["cs"][key], open(arc, "rb").read())
        (STATE["uploaded"] if ok else STATE["failed"]).append(f"cs:{key}")
        log(f"cs {key}: {'uploaded' if ok else 'UPLOAD FAILED'}")


def main():
    B = os.path.join(EXO, sys.argv[1])
    plan, urls = json.load(open(os.path.join(B, "plan.json"))), json.load(open(os.path.join(B, "urls.json")))
    R = os.path.join(EXO, "results", plan["id"])
    os.makedirs(os.path.join(R, "t2", "folds"), exist_ok=True)
    os.makedirs(os.path.join(R, "molusc"), exist_ok=True)
    stop = threading.Event()
    threading.Thread(target=heartbeat, args=(urls, stop), daemon=True).start()
    try:
        STATE["stage"] = "environment"
        env = check_env()
        log(f"environments: {env}")
        if any(v.startswith("mismatch") for v in env.values()):
            raise RuntimeError("an environment does not match its lock file")
        info = dict(batch=plan["id"], commit=plan["commit"], env=env)
        cs_proc = None
        if plan.get("centroids"):                   # per-sector centroids, alongside the TRICERATOPS stages
            os.makedirs(os.path.join(R, "cs"), exist_ok=True)
            cs_proc = subprocess.Popen([os.path.join(EXO, ".venv", "bin", "python"), "centroid_sectors.py",
                                        os.path.join(B, "cs_list.csv"), "--out", os.path.join(R, "cs"), "--procs", "6"],
                                       cwd=PIPE, env=ENV, stdout=open(os.path.join(HOME, "centroids.log"), "a"),
                                       stderr=subprocess.STDOUT)
        import csv
        items = [p["item"] for p in plan["items"]]
        cols = ["key", "tic", "period", "t0", "duration_h", "depth_ppm", "masks", "drop"]
        with open(os.path.join(R, "list.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(items)
        fetch_reused(B, R)
        for f in glob.glob(os.path.join(B, "reuse", "folds", "*.npz")):
            shutil.copyfile(f, os.path.join(R, "t2", "folds", os.path.basename(f)))
        for f in glob.glob(os.path.join(B, "reuse", "molusc", "*")):
            shutil.copyfile(f, os.path.join(R, "molusc", os.path.basename(f)))
        nproc = max(1, (os.cpu_count() or 2) - (7 if cs_proc else 1))
        if items or plan.get("fits"):
            STATE["stage"] = "download"
            run(["download.py", os.path.join(B, "tics.txt"), "--manifest", os.path.join(B, "manifest.parquet"), "--workers",
                 "32"], "download.log")
        if plan.get("fits"):
            STATE["stage"] = "fits"
            run_fits(plan, B, R, info, urls, nproc)
        if not items:
            STATE["stage"] = "centroids"
            return_after_centroids(cs_proc, plan, R, info, urls)
            STATE["stage"] = "done"
            return
        STATE["stage"] = "folds, setups and MOLUSC"
        mol = subprocess.Popen([os.path.join(EXO, ".venv", "bin", "python"), "molusc_batch.py", os.path.join(B, "stars.parquet"),
                                "--gaia", os.path.join(B, "gaia.csv"), "--molusc", os.path.join(B, "molusc_code"),
                                "--out", os.path.join(R, "molusc"), "--n", "200000", "--procs",
                                str(min(40, max(2, len({it["tic"] for it in items}))))],
                               cwd=PIPE, env=ENV, stdout=open(os.path.join(HOME, "molusc.log"), "a"), stderr=subprocess.STDOUT)
        rc = run(["fpp_fleet.py", os.path.join(R, "list.csv"), "--stars", os.path.join(B, "stars.parquet"), "--out",
                  os.path.join(R, "t2"), "--procs", str(nproc), "--molusc", os.path.join(R, "molusc")], "fleet.log")
        mol.wait()
        log(f"fleet prep exit {rc}; MOLUSC exit {mol.returncode}")
        jobs = {r["key"]: r for r in csv.DictReader(open(os.path.join(R, "t2", "jobs.csv")))}
        STATE["stage"] = "runs"
        # several signals per fpp_pool call (about three runs per process), each uploaded when its call ends
        per = max(1, (3 * nproc) // (2 * plan["runs"]))
        todo = [x for x in plan["items"] if x["item"]["key"] in jobs]
        for i in range(0, len(todo), per):
            chunk, rows = todo[i:i + per], []
            for x in chunk:
                key, base, cc = x["item"]["key"], x.get("base_runs", True), x.get("cc") or []
                rows += ([dict(jobs[key], cc="", cc_filt="")] if base else []) + [
                    dict(jobs[key], key=f"{key}__{c['label']}", cc=os.path.join(B, "cc", c["file"]), cc_filt=c["filt"])
                    for c in cc]
            if not rows:
                continue
            cj = os.path.join(R, "t2", f"jobs_{i}.csv")
            with open(cj, "w", newline="") as fh:
                w = csv.DictWriter(fh, list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            run(["fpp_pool.py", "run", cj, "--out", os.path.join(R, "t2"), "--procs", str(nproc), "--runs",
                 str(plan["runs"])], "runs.log", py=".venv-trice")
            for x in chunk:
                ok = pack(x["item"], R, jobs, info, urls, base=x.get("base_runs", True),
                          cc=[c["label"] for c in x.get("cc") or []])
                (STATE["uploaded"] if ok else STATE["failed"]).append(x["item"]["key"])
        STATE["failed"] += [it["key"] for it in items if it["key"] not in jobs]
        STATE["stage"] = "centroids"
        return_after_centroids(cs_proc, plan, R, info, urls)
        STATE["stage"] = "done"
    except Exception as ex:
        STATE["stage"] = f"error: {ex!r}"
        log(f"ERROR {ex!r}")
    finally:
        stop.set()
        for name in ("worker.log", "download.log", "fleet.log", "molusc.log", "runs.log", "centroids.log", "fits.log"):
            p = os.path.join(HOME, name)
            if os.path.exists(p) and name in urls.get("logs", {}):
                put(urls["logs"][name], open(p, "rb").read()[-2_000_000:])
        put(urls["done"], json.dumps(dict(STATE, now=time.time())).encode())
        subprocess.run(["sudo", "shutdown", "-h", "now"])


if __name__ == "__main__":
    main()
