"""The candidate folders, built by the rules folders and earlier_folders in rules.py. A folder is never removed, so a
published link keeps working when a signal changes tier or leaves a table.

candidates/allsky/: one folder per full-sky signal in tiers A, B, C, N, L1 or L, named by its candidate_id, and every
folder ever published. A folder holds vetting.json and vetting.png (the vetting metrics and plot), followup.json (pixel
and neighbour checks), transit_fit.json, the fit the catalog uses (from the store; a refit replaces it), and
triceratops_gaia.json, the TRICERATOPS result the catalog uses (ten runs with the default priors and ten with the Gaia
limits; absent where there is none). The other files are kept as published. A folder that does not exist yet is made from the source index
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


def build(root, catalog_csv, sources_csv, triceratops_csv, store_root, folder_tiers, fits_csv=None, vetting_csv=None):
    base = os.path.join(root, "candidates", "allsky")
    existing = set(os.listdir(base))
    sources = {r["candidate_id"]: r for r in _rows(sources_csv)}
    tri = {(r["TIC"], r["P_d"]): r for r in _rows(triceratops_csv) if r["table"] == "candidates_allsky"}
    fits = _fits(fits_csv, "candidates_allsky")
    vet = _vetting(vetting_csv, "candidates_allsky")
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
        _sync(d, tri.get((r["TIC"], r["P_d"])), store_root, n)
        _sync_fit(d, fits.get(r["candidate_id"]), store_root, n)
        _sync_vet(d, vet.get(r["candidate_id"]), store_root, n)
    return n


def _vetting(vetting_csv, table):
    """{candidate_id: vetting.csv row} of a table's rows."""
    return {r["candidate_id"]: r for r in _rows(vetting_csv) if r["table"] == table} if vetting_csv else {}


def _sync_vet(d, v, store_root, n):
    """vetting.json and vetting.png are the vetting result the catalog uses, followup.json its pixel follow-up (the
    entries vetting.csv names; the legacy ones are the files the folders were made with)."""
    if v is None:
        return
    for kind, key, names in (("vet", v["vet_store"], ("vetting.json", "vetting.png")), ("pixel", v["pixel_store"], ("followup.json",))):
        for name in names if key else ():
            src = os.path.join(store_root, kind, key[:2], key, name)
            target = os.path.join(d, name)
            if os.path.exists(src) and not _same(src, target):
                shutil.copyfile(src, target)
                n["updated"] += 1


def _fits(fits_csv, table):
    """{candidate_id: fits.csv row} of a table's rows whose fit passed its checks."""
    if not fits_csv:
        return {}
    return {r["candidate_id"]: r for r in _rows(fits_csv) if r["table"] == table and r["check"] == "passed"}


def _sync_fit(d, f, store_root, n):
    """transit_fit.json is the fit the catalog uses (a refit replaces it)."""
    if f is None:
        return
    src = os.path.join(store_root, "fit", f["store"][:2], f["store"], "transit_fit.json")
    target = os.path.join(d, "transit_fit.json")
    if os.path.exists(src) and not _same(src, target):
        shutil.copyfile(src, target)
        n["updated"] += 1


def _sync(d, t, store_root, n):
    """triceratops_gaia.json is the result the catalog uses (t, a row of triceratops.csv, or None; its file is in the
    store entry the row names), and the results of earlier methods are removed."""
    target = os.path.join(d, "triceratops_gaia.json")
    if t and t["degenerate"] != "yes":
        src = os.path.join(store_root, "tri", t["store"][:2], t["store"], "fpp.json")
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


def build_earlier(root, catalog_csv, triceratops_csv, store_root, fits_csv=None, vetting_csv=None):
    base = os.path.join(root, "candidates")
    tri = {(r["TIC"], r["P_d"]): r for r in _rows(triceratops_csv) if r["table"] == "tiers_earlier_candidates"}
    fits = _fits(fits_csv, "tiers_earlier_candidates")
    vet = _vetting(vetting_csv, "tiers_earlier_candidates")
    n = dict(created=0, updated=0, removed=0)
    for r in _rows(catalog_csv):
        d = os.path.join(base, r["candidate_id"])
        if not os.path.isdir(d):
            raise ValueError(f"{r['candidate_id']} has no folder; the earlier searches' folders are made by "
                             "package_candidates.py, and a new row needs one before the build can keep it")
        _sync(d, tri.get((r["TIC"], r["P_d"])), store_root, n)
        _sync_fit(d, fits.get(r["candidate_id"]), store_root, n)
        _sync_vet(d, vet.get(r["candidate_id"]), store_root, n)
    return n
