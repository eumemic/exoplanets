"""The candidate folders, built by the rules folders and earlier_folders in rules.py. A folder is never removed, so a
published link keeps working when a signal changes tier or leaves a table.

candidates/allsky/: one folder per full-sky signal in tiers A, B, C, N, L1 or L, named by its candidate_id, and every
folder ever published. A folder holds vetting.json and vetting.png (the vetting metrics and plot), followup.json (pixel
and neighbour checks), transit_fit.json where the signal has a fit, and triceratops_gaia.json, the TRICERATOPS result
the catalog uses (ten runs with the default priors and ten with the Gaia limits; absent where there is none). Files
other than triceratops_gaia.json are kept as published. A folder that does not exist yet is made from the source index
(a private file listing, for each signal, its vetting, follow-up and fit files with their SHA-256), and a source whose
content no longer matches the index is refused. The TRICERATOPS results of earlier methods (triceratops.json,
triceratops_fpp.json) are removed, since they no longer describe the catalog's values.

candidates/TIC*_P*/: the earlier searches' signals (tiers_earlier_candidates.csv), made by package_candidates.py when
each was first published; every row has one. triceratops_gaia.json is kept in step with the catalog as above, and the
results of earlier methods are removed. Six folders belong to signals that left the table because others reported them
first; they are kept as published, with the first release's TRICERATOPS result (triceratops_fpp.json) where they have
one, since no table gives them other values.
"""
import csv
import hashlib
import os
import shutil

FILES = (("vetting_json", "vetting.json"), ("vetting_png", "vetting.png"), ("followup_json", "followup.json"),
         ("transit_fit", "transit_fit.json"))
OBSOLETE = ("triceratops.json", "triceratops_fpp.json")


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _same(a, b):
    return os.path.exists(b) and os.path.getsize(a) == os.path.getsize(b) and _sha(a) == _sha(b)


def build(root, catalog_csv, sources_csv, triceratops_csv, results_root, folder_tiers):
    base = os.path.join(root, "candidates", "allsky")
    existing = set(os.listdir(base))
    sources = {r["candidate_id"]: r for r in _rows(sources_csv)}
    tri = {(r["TIC"], r["P_d"]): r for r in _rows(triceratops_csv) if r["table"] == "candidates_allsky"}
    n = dict(created=0, updated=0, removed=0)
    for r in _rows(catalog_csv):
        cid = r["candidate_id"]
        if r["tier"] not in folder_tiers and cid not in existing:
            continue
        d = os.path.join(base, cid)
        if cid not in existing:
            s = sources[cid]
            os.makedirs(d)
            for col, name in FILES:
                if s[col]:
                    src = os.path.join(root, s[col])
                    if _sha(src) != s[col + "_sha256"]:
                        raise ValueError(f"{src} no longer matches the source index")
                    shutil.copyfile(src, os.path.join(d, name))
            n["created"] += 1
        _sync(d, tri.get((r["TIC"], r["P_d"])), results_root, n)
    return n


def _sync(d, t, results_root, n):
    """triceratops_gaia.json is the result the catalog uses (t, a row of triceratops.csv, or None), and the results of
    earlier methods are removed."""
    target = os.path.join(d, "triceratops_gaia.json")
    if t and t["degenerate"] != "yes":
        src = os.path.join(results_root, t["batch"], f"{t['key']}_fpp.json")
        if not _same(src, target):
            shutil.copyfile(src, target)
            n["updated"] += 1
    elif os.path.exists(target):
        os.remove(target)
        n["removed"] += 1
    for f in OBSOLETE:
        if os.path.exists(os.path.join(d, f)):
            os.remove(os.path.join(d, f))
            n["removed"] += 1


def build_earlier(root, catalog_csv, triceratops_csv, results_root):
    base = os.path.join(root, "candidates")
    tri = {(r["TIC"], r["P_d"]): r for r in _rows(triceratops_csv) if r["table"] == "tiers_earlier_candidates"}
    n = dict(created=0, updated=0, removed=0)
    for r in _rows(catalog_csv):
        d = os.path.join(base, r["candidate_id"])
        if not os.path.isdir(d):
            raise ValueError(f"{r['candidate_id']} has no folder; the earlier searches' folders are made by "
                             "package_candidates.py, and a new row needs one before the build can keep it")
        _sync(d, tri.get((r["TIC"], r["P_d"])), results_root, n)
    return n
