"""Vetting (vet.py) and pixel follow-up (followup.py) results in the store (store.py), kinds vet and pixel, and
results_public/products/vetting.csv, the results each catalog row uses. Built by the rule vetting_table in rules.py;
the candidate folders take their vetting.json, vetting.png and followup.json from the entries it names (folders.py).

A vet request holds the signal as the search found it (TIC, rank, period, epoch, duration, the TOIs it masked), the
star's light-curve list (lcindex.py), the hash of its TIC row, the hash of the known-object catalogs it is matched
against (data/known), the code and the packages; a pixel request holds the signal, the sectors whose difference images
it fits (the vet result's best), the star's position and the galaxies and cores near it (ticfield.py), which are not
counted as neighbours, the code and the packages. The results made before the store are imported as legacy entries:
the files of the candidate folders where a row has one, else the files the folders are made from (the source index,
results_cloud/glue/build/folder_sources.csv). Each signal's entry with the highest seq is used, among those whose checks
passed. A vet result made from a light-curve list other than the star's list now (a legacy one was made from the
searched list), or either result made by other code, is out of date (check vetting_current); cloud.py plan --vet and
--pixel compute them again. The known-object matches in vetting.json are those of the catalogs at the time.

vetting.csv: table, TIC, P_d, candidate_id; vet_store, vet_batch, vet_legacy, vet_lightcurves, vet_code, depth_ppm, snr,
sector_chi2_dof, leo_fails (the number of LEO-Vetter tests failed); pixel_store, pixel_batch, pixel_legacy, pixel_code,
image (yes where a difference image was fitted), offset_arcsec (the offset of the best-quality image), close_capable
(the TIC entries within 15" bright enough to cause the dip, as the follow-up found them), close_stellar (those of them
that are not galaxies or cores).

Usage: python vet_store.py import
"""
import csv
import glob
import json
import os
import sys

import lcindex
import stage_code
import store as st

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SOURCES = os.path.join(ROOT, "results_cloud", "glue", "build", "folder_sources.csv")
COLUMNS = ["table", "TIC", "P_d", "candidate_id", "vet_store", "vet_batch", "vet_legacy", "vet_lightcurves", "vet_code",
           "search_rank", "search_period", "depth_ppm", "snr", "sector_chi2_dof", "leo_fails", "pixel_store", "pixel_batch",
           "pixel_legacy", "pixel_code", "image", "offset_arcsec", "close_capable", "close_stellar"]
SIGNAL_COLUMNS = ["table", "TIC", "P_d", "candidate_id", "file", "rank", "period", "t0", "duration_h", "rho", "n_sectors",
                  "masked_tois", "events"]
KNOWN = ("toi.csv", "ctoi.csv", "pscomppars.csv", "tce_all.parquet", "tce_tic.parquet", "literature.parquet")
STAGE_CODE = {"vet": [("vet", "vet_one"), ("vet", "main")], "pixel": [("followup", "one"), ("followup", "main")]}
PIXEL_SECTORS = 2                     # difference images per follow-up, as the search's follow-ups fitted


def _rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def signal_key(row):
    return f"tic{int(row['TIC'])}_P{float(row['P_d']):.4f}"


def _put_legacy(store, kind, table, row, files, source):
    main = files["vetting.json" if kind == "vet" else "followup.json"]
    req = dict(kind=kind, signal_key=signal_key(row), tic=int(row["TIC"]), table=table,
               legacy=["signal", "lightcurves", "star", "known", "code", "packages"], source=os.path.relpath(source, ROOT))
    res = dict(seq=0, batch="legacy", signal=dict(table=table, TIC=row["TIC"], P_d=row["P_d"]),
               content=st.file_content(main))
    return store.put(kind, req, res, files=files)


def import_legacy(store, root=ROOT):
    """Legacy entries for the vetting and follow-up files behind each catalog row. Returns {kind: count}."""
    n = dict(vet=0, pixel=0)
    sources = {r["candidate_id"]: r for r in _rows(SOURCES)}
    for table, path, base in (("candidates_allsky", "results_public/products/measurements_allsky.csv", "candidates/allsky"),
                              ("tiers_earlier_candidates", "results_public/products/measurements_earlier.csv", "candidates")):
        for r in _rows(os.path.join(root, path)):
            d = os.path.join(root, base, r["candidate_id"])
            if os.path.isdir(d):                    # a folder's files are what was published
                vet = {k: os.path.join(d, k) for k in ("vetting.json", "vetting.png") if os.path.exists(os.path.join(d, k))}
                pix = {k: os.path.join(d, k) for k in ("followup.json",) if os.path.exists(os.path.join(d, k))}
                src = d
            else:
                s = sources.get(r["candidate_id"], {})
                vet = {k: os.path.join(root, s[c]) for c, k in (("vetting_json", "vetting.json"), ("vetting_png", "vetting.png"))
                       if s.get(c) and os.path.exists(os.path.join(root, s[c]))}
                pix = {"followup.json": os.path.join(root, s["followup_json"])} if s.get("followup_json") and \
                    os.path.exists(os.path.join(root, s["followup_json"])) else {}
                src = os.path.dirname(vet.get("vetting.json") or next(iter(pix.values()), root))
            if "vetting.json" in vet:
                _put_legacy(store, "vet", table, r, vet, src)
                n["vet"] += 1
            if pix:
                _put_legacy(store, "pixel", table, r, pix, src)
                n["pixel"] += 1
    return n


def latest(store, kind):
    """{(table, signal key): (store key, request, result)}: each signal's entry with the highest seq whose checks passed."""
    out = {}
    for k, (req, res, chk) in store.entries(kind).items():
        if chk is not None and not chk.get("passed"):
            continue
        sk = (req["table"], req["signal_key"])
        if sk not in out or res["seq"] > out[sk][2]["seq"]:
            out[sk] = (k, req, res)
    return out


def _json(store, kind, key, name):
    p = os.path.join(store.path(kind, key), name)
    with open(p) as fh:
        return json.load(fh)


def table(store_root, rows, nonstellar, out_csv):
    """rows: [(table, TIC, P_d, candidate_id)] of the measurement tables; nonstellar: {tic: [galaxy and core ids]}
    (ticfield.by_star)."""
    store = st.Store(store_root)
    vets, pixs = latest(store, "vet"), latest(store, "pixel")
    out = []
    for t, tic, p, cid in rows:
        sk = (t, signal_key(dict(TIC=tic, P_d=p)))
        row = dict(table=t, TIC=tic, P_d=p, candidate_id=cid)
        if sk in vets:
            k, req, res = vets[sk]
            v = _json(store, "vet", k, "vetting.json")
            row.update(vet_store=k, vet_batch=res["batch"], vet_legacy="yes" if req.get("legacy") else "",
                       vet_lightcurves=lcindex.list_hash(req["lightcurves"]) if req.get("lightcurves") else "",
                       vet_code=stage_code.of_requests({"vet": req}), search_rank=v.get("rank", ""),
                       search_period=repr(float(v["period"])) if v.get("period") is not None else "",
                       depth_ppm=_r(v.get("depth_ppm"), 1), snr=_r(v.get("snr"), 2),
                       sector_chi2_dof=_r(v.get("sector_chi2_dof"), 2),
                       leo_fails=len(v.get("leo_fails") or []) if "leo_fails" in v else "")
        if sk in pixs:
            k, req, res = pixs[sk]
            f = _json(store, "pixel", k, "followup.json")
            close = [int(x[0]) for x in f.get("capable_within_15arcsec") or []]
            bad = set(nonstellar.get(int(tic), []))
            row.update(pixel_store=k, pixel_batch=res["batch"], pixel_legacy="yes" if req.get("legacy") else "",
                       pixel_code=stage_code.of_requests({"pixel": req}),
                       image="yes" if f.get("offset_qual") is not None else "",
                       offset_arcsec=_r(f.get("offset_qual"), 2), close_capable=" ".join(map(str, close)),
                       close_stellar=" ".join(str(c) for c in close if c not in bad))
        out.append(row)
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


def search_signals(vetting_csv, cands_files, out_csv):
    """Each row's signal as the search found it (the search's candidate row with the rank and period of the row's
    vetting), which a new vetting starts from (results_cloud/glue/build/search_signals.csv, a private rule's output)."""
    import pandas as pd
    want = {}
    for r in _rows(vetting_csv):
        if r["search_rank"] and r["search_period"]:
            want.setdefault((int(r["TIC"]), int(r["search_rank"])), []).append(r)
    tics = {t for t, _ in want}
    cols = ["tic", "rank", "period", "t0", "duration_h", "rho", "n_sectors", "masked_tois", "events"]
    best = {}
    for f in cands_files:
        head = pd.read_csv(f, nrows=0).columns
        use = [c for c in cols if c in head]
        for chunk in pd.read_csv(f, usecols=use, chunksize=500000):
            chunk = chunk[chunk.tic.isin(tics)]
            for c in chunk.itertuples(index=False):
                c = c._asdict()
                for r in want.get((int(c["tic"]), int(c["rank"])), []):
                    d = abs(float(c["period"]) / float(r["search_period"]) - 1)
                    k = (r["table"], r["TIC"], r["P_d"])
                    if d < 1e-6 and (k not in best or d < best[k][0]):
                        best[k] = (d, dict(c, file=os.path.relpath(f, ROOT)))
    out = []
    for r in _rows(vetting_csv):
        hit = best.get((r["table"], r["TIC"], r["P_d"]))
        if hit:
            c = hit[1]
            out.append(dict(table=r["table"], TIC=r["TIC"], P_d=r["P_d"], candidate_id=r["candidate_id"], file=c["file"],
                            **{k: ("" if c.get(k) is None or (isinstance(c.get(k), float) and c[k] != c[k]) else c[k])
                               for k in SIGNAL_COLUMNS[5:]}))
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, SIGNAL_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


def _r(x, nd):
    try:
        return repr(round(float(x), nd))
    except (TypeError, ValueError):
        return ""


def stale(vetting_csv, searched_csv, lists_csv, code_json, folders):
    """The rows with folders whose vet result was made from a light-curve list other than the star's now, or whose vet
    or pixel result was made by other code: [(table, TIC, P_d, reason)]. folders: the candidate_ids with folders."""
    was, now = lcindex.star_hashes(searched_csv), lcindex.star_hashes(lists_csv)
    with open(code_json) as fh:
        code = json.load(fh)
    out = []
    for r in _rows(vetting_csv):
        if r["candidate_id"] not in folders:
            continue
        why = []
        if r["vet_store"] and (r["vet_lightcurves"] or was.get(int(r["TIC"]))) != now.get(int(r["TIC"])):
            why.append("vetting: the star's light curves have changed")
        for kind in ("vet", "pixel"):
            if stage_code.changed(r[f"{kind}_code"], code):
                why.append(f"{'vetting' if kind == 'vet' else 'pixel follow-up'}: the code or its packages changed")
        if why:
            out.append((r["table"], r["TIC"], r["P_d"], "; ".join(why)))
    return out


def code_hash(kind, index=None):
    from dag.codehash import CodeIndex
    idx = index or CodeIndex([os.path.dirname(os.path.abspath(__file__))])
    parts, effects = {}, {}
    for m, f in STAGE_CODE[kind]:
        p, e, _ = idx.closure(m, f)
        parts.update(p)
        effects.update(e)
    return st.sha256_json({"parts": parts, "effects": effects})


def known_hash(root=ROOT):
    """The hash of the known-object catalogs vet.py matches signals against (data/known)."""
    return st.sha256_json([[n, st.file_content(os.path.join(root, "data", "known", n))] for n in KNOWN])


def vet_request(table, sig, lightcurves, star, known, code, env):
    """sig: the signal as the search found it (tic, rank, period, t0, duration_h, masked_tois)."""
    return dict(kind="vet", signal_key=sig["key"], tic=int(sig["tic"]), table=table,
                signal={k: str(sig.get(k, "")) for k in ("rank", "period", "t0", "duration_h", "masked_tois")},
                lightcurves=sorted(lightcurves), star=star, known=known, code=code, env=env)


def pixel_request(table, sig, sectors, position, not_sources, code, env):
    return dict(kind="pixel", signal_key=sig["key"], tic=int(sig["tic"]), table=table,
                signal={k: str(sig.get(k, "")) for k in ("rank", "period", "t0", "duration_h", "depth_ppm")},
                sectors=sorted(int(s) for s in sectors), position=[str(position[0]), str(position[1])],
                not_sources=sorted(int(x) for x in not_sources), code=code, env=env)


def ingest_item(store, d, plan_item, kind, batch, seq, env_lock="requirements.txt"):
    """Store one vet or pixel result of a cloud batch: d holds its files and item.json (cloud_worker.py)."""
    info = json.load(open(os.path.join(d, "item.json")))
    found = []
    if info["env"].get(env_lock) != plan_item["env"]:
        found.append(f"the instance's packages do not match {env_lock}")
    if info.get("commit") != plan_item["commit"]:
        found.append(f"code: the instance ran commit {info.get('commit')}, the plan {plan_item['commit']}")
    main = "vetting.json" if kind == "vet" else "followup.json"
    j = json.load(open(os.path.join(d, main)))
    if "error" in j or "pixel_error" in j and kind == "pixel" and not j.get("centroids"):
        found.append(f"{kind}: {j.get('error') or j.get('pixel_error')}")
    files = {n: os.path.join(d, n) for n in (("vetting.json", "vetting.png") if kind == "vet" else ("followup.json",))
             if os.path.exists(os.path.join(d, n))}
    req = plan_item["request"]
    res = dict(seq=seq, batch=batch, signal=dict(table=req["table"], TIC=str(req["tic"]), P_d=plan_item["row_P_d"]),
               content=st.file_content(os.path.join(d, main)))
    key = store.put(kind, req, res, check=dict(passed=not found, problems=found), files=files)
    return key, found


def main():
    if sys.argv[1:] != ["import"]:
        sys.exit(__doc__)
    print(import_legacy(st.Store()))


if __name__ == "__main__":
    main()
