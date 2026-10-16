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
    state = _state(t2, job)
    shutil.copyfile(state, os.path.join(big, "state.pkl"))
    pops = _population(t2, tic)
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
    contents = [molusc]                                     # the star's further MOLUSC samples
    for i in range(1, len([x for x in (job.get("molusc") or "").split(";") if x])):
        src = os.path.join(R, f"molusc_s{i}", f"tic{tic}_kept.csv.gz")
        shutil.copyfile(src, os.path.join(big, f"molusc_s{i}.csv.gz"))
        contents.append(_gz_sha(os.path.join(big, f"molusc_s{i}.csv.gz")))
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
                   setup_digest=_read(state + ".digest"), molusc_content=molusc, molusc_contents=contents, remote=True),
              open(os.path.join(d, "item.json"), "w"))
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


def _state(t2, job):
    """The target state of a job: its own depth's (fpp_pool.depth_state_path)."""
    return os.path.join(t2, "states", f"{int(job['tic'])}_{job['sectors'].replace(',', '-')}_d{float(job['depth_ppm']):g}.pkl")


def _population(t2, tic):
    """The field-star population file of a star's setups: as TRICERATOPS wrote it, or as a reused setup brought it."""
    c = os.path.join(t2, "cache", str(tic))
    return sorted(glob.glob(os.path.join(c, "*gaia_background.csv"))) or sorted(glob.glob(os.path.join(c, "population.csv")))


def _read(path):
    return open(path).read().strip() if os.path.exists(path) else None


def pack_reused(x, R, jobs, info, urls):
    """Upload an item whose new target setup has the digest of the setup its result in use ran on: the runs are not
    repeated; the new setup's files go up (a later batch can reuse them) with item.json naming the result kept."""
    it = x["item"]
    key, tic, job = it["key"], int(it["tic"]), jobs[it["key"]]
    t2 = os.path.join(R, "t2")
    d, big = os.path.join(R, "items", key), os.path.join(R, "items", key + ".big")
    for y in (d, big):
        shutil.rmtree(y, ignore_errors=True)
    os.makedirs(d)
    os.makedirs(os.path.join(big, "cuts"))
    state = _state(t2, job)
    shutil.copyfile(state, os.path.join(big, "state.pkl"))
    sfiles = {"state.pkl": os.path.join(big, "state.pkl")}
    pops = _population(t2, tic)
    if pops:
        shutil.copyfile(pops[0], os.path.join(big, "population.csv"))
        sfiles["population.csv"] = os.path.join(big, "population.csv")
    for c in sorted(glob.glob(os.path.join(t2, "cuts", f"tic{tic}", "*.fits"))):
        shutil.copyfile(c, os.path.join(big, "cuts", os.path.basename(c)))
        sfiles[f"cut_{os.path.basename(c)}"] = os.path.join(big, "cuts", os.path.basename(c))
    files = {n: dict(sha256=_sha(q), size=os.path.getsize(q)) for n, q in sfiles.items()}
    json.dump(dict(info, key=key, tic=tic, sectors=job["sectors"], reused=x["prior"]["tri"], setup_files=files,
                   setup_digest=_read(state + ".digest"), prior_digest=_read(os.path.join(R, "prior", key, "digest")),
                   remote=True), open(os.path.join(d, "item.json"), "w"))
    ok = True
    for src, url in ((big, urls["big"][key]), (d, urls["items"][key])):
        arc = src + ".tgz"
        with tarfile.open(arc, "w:gz") as tf:
            tf.add(src, arcname=".")
        ok = put(url, open(arc, "rb").read()) and ok
    log(f"{key}: {'kept' if ok else 'UPLOAD FAILED'} (target setup unchanged; result {x['prior']['tri'][:12]} kept)")
    return ok


def prior_digests(R, priors):
    """The digests of the setups the results in use ran on (fetched by fetch_reused into R/prior/<key>/), written to
    R/prior/<key>/digest; their population files also go where this machine's new setups find them."""
    todo = []
    for key, tic in priors:
        pd_ = os.path.join(R, "prior", key)
        pop = os.path.join(pd_, "population.csv")
        cache = os.path.join(R, "t2", "cache", str(tic))
        if os.path.exists(pop) and not _population(os.path.join(R, "t2"), tic):
            os.makedirs(cache, exist_ok=True)
            shutil.copyfile(pop, os.path.join(cache, f"{tic}_gaia_background.csv"))
        if os.path.exists(os.path.join(pd_, "state.pkl")):
            todo.append([os.path.join(pd_, "state.pkl"), pop if os.path.exists(pop) else "", os.path.join(pd_, "digest")])
    if todo:
        lst = os.path.join(R, "prior", "todo.json")
        with open(lst, "w") as fh:
            json.dump(todo, fh)
        script = ("import json, sys; sys.path.insert(0, %r); import fpp_core as fc\n"
                  "for st, pop, out in json.load(open(sys.argv[1])):\n"
                  "    t = fc.load_state(st); t.trilegal_fname = pop or None\n"
                  "    open(out, 'w').write(fc.setup_digest(t))\n") % PIPE
        subprocess.run([os.path.join(EXO, ".venv-trice", "bin", "python"), "-c", script, lst], check=True, env=ENV)
    log(f"digests of {len(todo)} setups that results in use ran on")


def fetch_reused(B, R):
    """The stored target setups and MOLUSC files this batch reuses, from their archives in the bucket. A reused
    setup's population file is put where this machine keeps it, and the pickled target is pointed at it."""
    path = os.path.join(B, "reuse", "remote.json")
    items = json.load(open(path)) if os.path.exists(path) else []
    fix = []

    def one(ix):
        i, x = ix
        arc = os.path.join(R, f"reuse_{i}.tgz")
        for attempt in range(4):
            try:
                with urllib.request.urlopen(x["url"], timeout=300) as r, open(arc, "wb") as fh:
                    shutil.copyfileobj(r, fh)
                break
            except Exception as ex:
                if attempt == 3:
                    raise
                log(f"retrying a download: {ex!r}")
                time.sleep(5 * (attempt + 1))
        with tarfile.open(arc) as tf:
            names = set(tf.getnames())
            for member, dest in x["members"].items():
                f = tf.extractfile("./" + member) if "./" + member in names else tf.extractfile(member)
                os.makedirs(os.path.dirname(os.path.join(R, dest)), exist_ok=True)
                with open(os.path.join(R, dest), "wb") as out:
                    shutil.copyfileobj(f, out)
        os.remove(arc)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(one, enumerate(items)))
    for x in items:
        if x.get("state"):
            fix.append([os.path.join(R, x["state"]), os.path.join(R, x["population"]) if x.get("population") else ""])
            if x.get("digest"):
                with open(os.path.join(R, x["state"]) + ".digest", "w") as fh:
                    fh.write(x["digest"])
    if fix:
        lst = os.path.join(R, "reuse_fix.json")
        with open(lst, "w") as fh:
            json.dump(fix, fh)
        script = ("import json, sys; sys.path.insert(0, %r); import fpp_core as fc\n"
                  "for st, pop in json.load(open(sys.argv[1])):\n"
                  "    t = fc.load_state(st); t.trilegal_fname = pop or None; fc.save_state(t, st)\n") % PIPE
        subprocess.run([os.path.join(EXO, ".venv-trice", "bin", "python"), "-c", script, lst], check=True, env=ENV)
    log(f"reused from the bucket: {len(items)} archives ({len(fix)} target setups)")
    prior_digests(R, [(x["prior"], int(x["tic"])) for x in items if x.get("prior")])


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


def _upload_dir(d, url):
    arc = d + ".tgz"
    with tarfile.open(arc, "w:gz") as tf:
        tf.add(d, arcname=".")
    return put(url, open(arc, "rb").read())


def run_vet(plan, B, R, info, urls, procs):
    """The batch's vettings (vet.vet_one, its plot always drawn), each uploaded when the pool returns it."""
    known = os.path.join(EXO, "data", "known")          # vet.py matches against data/known: the kit's snapshot
    os.makedirs(known, exist_ok=True)
    for f in glob.glob(os.path.join(B, "known", "*")):
        shutil.copyfile(f, os.path.join(known, os.path.basename(f)))
    out = os.path.join(R, "vet_out")
    os.makedirs(out, exist_ok=True)
    jobs = os.path.join(R, "vet_jobs.json")
    with open(jobs, "w") as fh:
        json.dump([x["item"] for x in plan["vet"]], fh)
    script = ("import json, sys; sys.path.insert(0, %r)\n"
              "from multiprocessing import Pool\n"
              "import pandas as pd, vet\n"
              "stars = pd.read_parquet(sys.argv[2]).drop_duplicates('ID').set_index('ID')\n"
              "jobs = [(dict(s), stars.loc[int(s['tic'])].to_dict(), sys.argv[3]) for s in json.load(open(sys.argv[1]))]\n"
              "with Pool(int(sys.argv[4]), initializer=vet._set_plot_max_fails, initargs=(-1,)) as pool:\n"
              "    for i in pool.imap_unordered(vet.vet_one, jobs):\n"
              "        print(i.get('tic'), i.get('rank'), i.get('error', 'ok'), flush=True)\n") % PIPE
    with open(os.path.join(HOME, "vet.log"), "a") as lg:
        subprocess.run([os.path.join(EXO, ".venv", "bin", "python"), "-c", script, jobs, os.path.join(B, "stars.parquet"),
                        out, str(max(1, procs))], cwd=PIPE, env=ENV, stdout=lg, stderr=subprocess.STDOUT)
    for x in plan["vet"]:
        it = x["item"]
        key, src = it["key"], os.path.join(out, f"tic{it['tic']}_{it['rank']}")
        if not os.path.exists(src + ".json"):
            STATE["failed"].append(f"vet:{key}")
            log(f"vet {key}: no result")
            continue
        d = os.path.join(R, "vet_items", key)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(src + ".json", os.path.join(d, "vetting.json"))
        if os.path.exists(src + ".png"):
            shutil.copyfile(src + ".png", os.path.join(d, "vetting.png"))
        json.dump(dict(info, key=key), open(os.path.join(d, "item.json"), "w"))
        ok = _upload_dir(d, urls["vet"][key])
        (STATE["uploaded"] if ok else STATE["failed"]).append(f"vet:{key}")
        log(f"vet {key}: {'uploaded' if ok else 'UPLOAD FAILED'}")


def run_pixel(plan, B, R, info, urls, procs):
    """The batch's pixel follow-ups (followup.one: TIC neighbours bright enough to cause the dip, galaxies and their cores
    left out, and difference-image centroids in the sectors the vetting in use ranks best)."""
    out = os.path.join(R, "pixel_out")
    os.makedirs(out, exist_ok=True)
    jobs = os.path.join(R, "pixel_jobs.json")
    with open(jobs, "w") as fh:
        json.dump([x["item"] for x in plan["pixel"]], fh)
    script = ("import json, sys; sys.path.insert(0, %r)\n"
              "from multiprocessing import Pool\n"
              "import pandas as pd, followup\n"
              "followup.PIX.mkdir(parents=True, exist_ok=True)\n"
              "stars = pd.read_parquet(sys.argv[2]).drop_duplicates('ID').set_index('ID')\n"
              "jobs = [(dict(s), stars.loc[int(s['tic'])].to_dict(), len(s['sectors']) or 2, sys.argv[5], sys.argv[3])\n"
              "        for s in json.load(open(sys.argv[1]))]\n"
              "with Pool(int(sys.argv[4])) as pool:\n"
              "    for r in pool.imap_unordered(followup.one, jobs):\n"
              "        print(r.get('tic'), r.get('rank'), r.get('flags'), flush=True)\n") % PIPE
    with open(os.path.join(HOME, "pixel.log"), "a") as lg:
        subprocess.run([os.path.join(EXO, ".venv", "bin", "python"), "-c", script, jobs, os.path.join(B, "stars.parquet"),
                        out, str(max(1, min(8, procs))), os.path.join(B, "vet_dir")], cwd=PIPE, env=ENV, stdout=lg,
                       stderr=subprocess.STDOUT)
    for x in plan["pixel"]:
        it = x["item"]
        key, src = it["key"], os.path.join(out, f"tic{it['tic']}_{it['rank']}.json")
        if not os.path.exists(src):
            STATE["failed"].append(f"pixel:{key}")
            log(f"pixel {key}: no result")
            continue
        d = os.path.join(R, "pixel_items", key)
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(src, os.path.join(d, "followup.json"))
        json.dump(dict(info, key=key), open(os.path.join(d, "item.json"), "w"))
        ok = _upload_dir(d, urls["pixel"][key])
        (STATE["uploaded"] if ok else STATE["failed"]).append(f"pixel:{key}")
        log(f"pixel {key}: {'uploaded' if ok else 'UPLOAD FAILED'}")


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
        items = [dict(p["item"], not_hosts=",".join(str(v) for v in p.get("not_hosts") or [])) for p in plan["items"]]
        cols = ["key", "tic", "period", "t0", "duration_h", "depth_ppm", "masks", "drop", "not_hosts"]
        with open(os.path.join(R, "list.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(items)
        fetch_reused(B, R)
        for f in glob.glob(os.path.join(B, "reuse", "folds", "*.npz")):
            shutil.copyfile(f, os.path.join(R, "t2", "folds", os.path.basename(f)))
        for f in glob.glob(os.path.join(B, "reuse", "molusc", "*")):
            shutil.copyfile(f, os.path.join(R, "molusc", os.path.basename(f)))
        n_samples = int(plan.get("molusc_samples") or 1)    # the star's MOLUSC samples: R/molusc, then R/molusc_s<i>
        for i in range(1, n_samples):
            os.makedirs(os.path.join(R, f"molusc_s{i}"), exist_ok=True)
            for f in glob.glob(os.path.join(B, "reuse", f"molusc_s{i}", "*")):
                shutil.copyfile(f, os.path.join(R, f"molusc_s{i}", os.path.basename(f)))
        nproc = max(1, (os.cpu_count() or 2) - (7 if cs_proc else 1))
        if items or plan.get("fits") or plan.get("vet"):
            STATE["stage"] = "download"
            run(["download.py", os.path.join(B, "tics.txt"), "--manifest", os.path.join(B, "manifest.parquet"), "--workers",
                 "32"], "download.log")
        if plan.get("fits"):
            STATE["stage"] = "fits"
            run_fits(plan, B, R, info, urls, nproc)
        if plan.get("vet"):
            STATE["stage"] = "vetting"
            run_vet(plan, B, R, info, urls, nproc)
        if plan.get("pixel"):
            STATE["stage"] = "pixel follow-up"
            run_pixel(plan, B, R, info, urls, nproc)
        if not items:
            STATE["stage"] = "centroids"
            return_after_centroids(cs_proc, plan, R, info, urls)
            STATE["stage"] = "done"
            return
        STATE["stage"] = "folds, setups and MOLUSC"
        k = int(plan.get("molusc_sample") or 0)     # another sample of simulated companions than the catalog's

        def molusc_all():
            """The star's MOLUSC samples one after another: the first (the catalog's, or sample k of an experiment), then
            the catalog's further samples 1, 2, ... (molusc_sample.py)."""
            for i, (script, sample, out) in enumerate([("molusc_sample.py" if k else "molusc_batch.py", k, "molusc")]
                                                      + [("molusc_sample.py", s_, f"molusc_s{s_}") for s_ in range(1, n_samples)]):
                subprocess.run([os.path.join(EXO, ".venv", "bin", "python"), script, os.path.join(B, "stars.parquet"),
                                "--gaia", os.path.join(B, "gaia.csv"), "--molusc", os.path.join(B, "molusc_code"),
                                "--out", os.path.join(R, out), "--n", "200000", "--procs",
                                str(min(max(2, (os.cpu_count() or 4) - 2), max(2, len({it["tic"] for it in items}))))],
                               cwd=PIPE, env=dict(ENV, EXO_MOLUSC_SAMPLE=str(sample)),
                               stdout=open(os.path.join(HOME, "molusc.log"), "a"), stderr=subprocess.STDOUT)
        mol = threading.Thread(target=molusc_all)
        mol.start()
        rc = run(["fpp_fleet.py", os.path.join(R, "list.csv"), "--stars", os.path.join(B, "stars.parquet"), "--out",
                  os.path.join(R, "t2"), "--procs", str(nproc), "--molusc", os.path.join(R, "molusc")], "fleet.log")
        mol.join()
        log(f"fleet prep exit {rc}; MOLUSC done ({n_samples} sample{'s' if n_samples > 1 else ''})")
        jobs = {r["key"]: r for r in csv.DictReader(open(os.path.join(R, "t2", "jobs.csv")))}
        STATE["stage"] = "results kept"
        todo, keep = [], []
        for x in plan["items"]:
            key = x["item"]["key"]
            if key not in jobs:
                continue
            new = _read(_state(os.path.join(R, "t2"), jobs[key]) + ".digest")
            (keep if x.get("prior") and new and new == _read(os.path.join(R, "prior", key, "digest")) else todo).append(x)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(16) as ex:
            for x, ok in zip(keep, ex.map(lambda y: pack_reused(y, R, jobs, info, urls), keep)):
                (STATE["uploaded"] if ok else STATE["failed"]).append(x["item"]["key"])
        log(f"{len(keep)} results kept (target setup unchanged), {len(todo)} to run")
        STATE["stage"] = "runs"
        # several signals per fpp_pool call (about three runs per process), each uploaded when its call ends; fpp_pool
        # run reads a star's target from one file per star and sectors, so a call holds one depth of each
        per = max(1, (3 * nproc) // (2 * plan["runs"]))
        chunks, cur, seen = [], [], {}
        for x in todo:
            j = jobs[x["item"]["key"]]
            sk = (j["tic"], j["sectors"])
            if len(cur) >= per or (sk in seen and seen[sk] != j["depth_ppm"]):
                chunks.append(cur)
                cur, seen = [], {}
            cur.append(x)
            seen[sk] = j["depth_ppm"]
        chunks += [cur] if cur else []
        for i, chunk in enumerate(chunks):
            rows = []
            for x in chunk:
                j = jobs[x["item"]["key"]]
                plain = os.path.join(R, "t2", "states", f"{int(j['tic'])}_{j['sectors'].replace(',', '-')}.pkl")
                if os.path.exists(_state(os.path.join(R, "t2"), j)):
                    shutil.copyfile(_state(os.path.join(R, "t2"), j), plain)
            for x in chunk:
                key, base, cc = x["item"]["key"], x.get("base_runs", True), x.get("cc") or []
                if n_samples > 1 and jobs[key].get("molusc"):          # every sample, or no Gaia-limited runs at all
                    tic = int(x["item"]["tic"])
                    files = [os.path.join(R, "molusc", f"tic{tic}_kept.csv.gz")] + [
                        os.path.join(R, f"molusc_s{i}", f"tic{tic}_kept.csv.gz") for i in range(1, n_samples)]
                    if not all(os.path.exists(f) for f in files):
                        log(f"{key}: {sum(map(os.path.exists, files))} of {n_samples} MOLUSC samples; not run")
                        continue
                    jobs[key] = dict(jobs[key], molusc=";".join(files))
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
        for name in ("worker.log", "download.log", "fleet.log", "molusc.log", "runs.log", "centroids.log", "fits.log", "vet.log",
                     "pixel.log"):
            p = os.path.join(HOME, name)
            if os.path.exists(p) and name in urls.get("logs", {}):
                put(urls["logs"][name], open(p, "rb").read()[-2_000_000:])
        put(urls["done"], json.dumps(dict(STATE, now=time.time())).encode())
        subprocess.run(["sudo", "shutdown", "-h", "now"])


if __name__ == "__main__":
    main()
