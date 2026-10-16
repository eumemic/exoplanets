"""The build's rules: each published file, the inputs and parameters it is made from, and the function that makes it.
Run from pipeline/ with `../.venv/bin/python -m dag status|run|check` (see dag/__main__.py)."""
import allsky_figure as af
import catalog as cat
import catalog_checks as cc
import centroid_table as ct
import doc_numbers
import findability as fb
import fit_store
import folders as fo
import lcindex as lc
import predict
import tri_plan as tp
import triceratops_table as tt
from dag import check, rule


@rule(inputs=["results_public/candidates_allsky.csv"], outputs=["figures/allsky.png"], params=["catalog.counted_allsky"])
def allsky_figure(ctx):
    af.draw(ctx.input("results_public/candidates_allsky.csv"), ctx.output("figures/allsky.png"),
            ctx.param("catalog.counted_allsky"))


STORE = "results_cloud/store"


@rule(inputs=[f"{STORE}/tri/*/*/request.json", f"{STORE}/tri/*/*/result.json", f"{STORE}/tri/*/*/check.json",
              f"{STORE}/fold/*/*/fold.npz",
              "results_public/products/measurements_allsky.csv", "results_public/products/measurements_earlier.csv"],
      outputs=["results_public/products/triceratops.csv"], params=["triceratops.*"])
def triceratops_table(ctx):
    """The TRICERATOPS result each catalog row uses, from the store (triceratops_table.py, tri_store.py)."""
    rows = [(t, r["TIC"], r["P_d"]) for t, f in (("candidates_allsky", "measurements_allsky.csv"),
                                                 ("tiers_earlier_candidates", "measurements_earlier.csv"))
            for r in cat.read_rows(ctx.input(f"results_public/products/{f}"))]
    tt.build(ctx.root / STORE, rows, ctx.output("results_public/products/triceratops.csv"), runs=ctx.param("triceratops.runs"),
             min_survivors=ctx.param("triceratops.min_survivors"), phase_bin_min=ctx.param("triceratops.phase_bin_min"),
             match_rel=ctx.param("triceratops.match_period_rel"))


@rule(inputs=[f"{STORE}/centroid/*/*/request.json", f"{STORE}/centroid/*/*/result.json", f"{STORE}/centroid/*/*/*.json",
              "results_public/products/measurements_allsky.csv", "results_public/products/measurements_earlier.csv"],
      outputs=["results_public/products/centroids.csv"], params=["triceratops.match_period_rel"])
def centroid_table(ctx):
    """The per-sector centroid measurement each catalog row uses, from the store (centroid_table.py, centroid_store.py)."""
    rows = [(t, r["TIC"], r["P_d"]) for t, f in (("candidates_allsky", "measurements_allsky.csv"),
                                                 ("tiers_earlier_candidates", "measurements_earlier.csv"))
            for r in cat.read_rows(ctx.input(f"results_public/products/{f}"))]
    ct.build(ctx.root / STORE, rows, ctx.output("results_public/products/centroids.csv"),
             match_rel=ctx.param("triceratops.match_period_rel"))


@rule(inputs=[f"{STORE}/fit/*/*/request.json", f"{STORE}/fit/*/*/result.json", f"{STORE}/fit/*/*/check.json",
              "results_public/products/measurements_allsky.csv", "results_public/products/measurements_earlier.csv"],
      outputs=["results_public/products/fits.csv"])
def fit_table(ctx):
    """The transit fit each catalog row uses, from the store (fit_store.py)."""
    rows = [(t, r["TIC"], r["P_d"], r["candidate_id"]) for t, f in (("candidates_allsky", "measurements_allsky.csv"),
                                                                    ("tiers_earlier_candidates", "measurements_earlier.csv"))
            for r in cat.read_rows(ctx.input(f"results_public/products/{f}"))]
    fit_store.table(ctx.root / STORE, rows, ctx.output("results_public/products/fits.csv"))


@rule(inputs=["results_public/products/measurements_allsky.csv", "results_public/products/measurements_earlier.csv",
              "results_public/products/triceratops.csv", "results_public/products/centroids.csv",
              "results_public/products/fits.csv", "results_public/overrides.csv"],
      outputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv"],
      params=["catalog.counted_allsky", "tiers.*", "flags.*"])
def catalog(ctx):
    P = ctx.params()
    cat.build(ctx.input("results_public/products/measurements_allsky.csv"),
              ctx.input("results_public/products/measurements_earlier.csv"),
              ctx.input("results_public/products/triceratops.csv"), ctx.input("results_public/overrides.csv"),
              ctx.output("results_public/candidates_allsky.csv"), ctx.output("results_public/tiers_earlier_candidates.csv"), P,
              centroids_csv=ctx.input("results_public/products/centroids.csv"),
              fits_csv=ctx.input("results_public/products/fits.csv"))


@rule(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv", "candidates/ephemerides.csv",
              "data/known/toi.csv", "results_public/products/triceratops.csv", "results_public/products/lightcurves_searched.csv",
              "results_public/products/lightcurves.csv"],
      outputs=["results_public/products/triceratops_plan.csv"], params=["tiers.*", "freshness.*", "triceratops.match_period_rel"])
def triceratops_plan(ctx):
    """The rows that need a TRICERATOPS result or show one, with the inputs a current result has (tri_plan.py)."""
    tol = {k.split(".")[1]: v for k, v in ctx.params().items() if k.startswith("freshness.")}
    lists = (lc.star_hashes(ctx.input("results_public/products/lightcurves_searched.csv")),
             lc.star_hashes(ctx.input("results_public/products/lightcurves.csv")))
    tp.build(ctx.input("results_public/candidates_allsky.csv"), ctx.input("results_public/tiers_earlier_candidates.csv"),
             ctx.input("candidates/ephemerides.csv"), ctx.input("data/known/toi.csv"),
             ctx.input("results_public/products/triceratops.csv"), ctx.output("results_public/products/triceratops_plan.csv"),
             ctx.params(), tol, ctx.param("triceratops.match_period_rel"), lists=lists)


@check(inputs=["results_public/products/triceratops_plan.csv"])
def triceratops_current(ctx):
    rows = [r for r in cat.read_rows(ctx.input("results_public/products/triceratops_plan.csv")) if r["status"] in ("pending", "stale")]
    assert not rows, (f"{len(rows)} TRICERATOPS results are missing or ran on inputs that have changed (cloud.py plan runs "
                      "them):\n" + "\n".join(f"{r['table']} TIC {r['TIC']} P {r['P_d']} ({r['status']}): {r['reason']}"
                                             for r in rows[:60]))


@check(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv"],
       params=["catalog.counted_allsky", "catalog.counted_earlier"])
def counted_measured_centroids(ctx):
    problems = (cc.counted_measured_centroids(ctx.input("results_public/candidates_allsky.csv"), ctx.param("catalog.counted_allsky"))
                + cc.counted_measured_centroids(ctx.input("results_public/tiers_earlier_candidates.csv"),
                                                ctx.param("catalog.counted_earlier")))
    assert not problems, f"{len(problems)} counted candidates have no per-sector centroid measurement:\n" + "\n".join(problems)


@check(inputs=["results_public/products/centroids.csv", "results_public/products/measurements_allsky.csv"], params=["freshness.*"])
def centroid_inputs_current(ctx):
    tol = {k.split(".")[1]: v for k, v in ctx.params().items() if k.startswith("freshness.")}
    problems = cc.centroid_inputs_current(ctx.input("results_public/products/centroids.csv"),
                                          ctx.input("results_public/products/measurements_allsky.csv"), tol)
    assert not problems, f"{len(problems)} centroid measurements used an ephemeris that has changed since:\n" + "\n".join(problems)


LC = "results_public/products/lightcurves"


@rule(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv", lc.MANIFESTS_NEW]
      + lc.MANIFESTS_OLD, outputs=[f"{LC}_searched.csv"])
def lightcurves_searched(ctx):
    """The light curves the searches used for the catalog's stars, one product per star and sector (lcindex.py)."""
    lc.searched(ctx.input("results_public/candidates_allsky.csv"), ctx.input("results_public/tiers_earlier_candidates.csv"),
                ctx.output(f"{LC}_searched.csv"), root=ctx.root)


@rule(inputs=[f"{LC}_searched.csv", f"{LC}_current.csv"], outputs=[f"{LC}.csv"])
def lightcurves(ctx):
    """The light curves new work uses: the searched lists with the MAST snapshot's redeliveries and withdrawals
    (lightcurves_current.csv, written by `lcindex.py refresh`) applied (lcindex.py)."""
    lc.current_lists(ctx.input(f"{LC}_searched.csv"), ctx.input(f"{LC}_current.csv"), ctx.output(f"{LC}.csv"))


@rule(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv", f"{LC}_searched.csv",
              f"{LC}.csv", f"{LC}_current.csv", "results_public/products/fits.csv", "results_public/products/triceratops.csv"],
      outputs=["results_public/products/redo.csv"], params=["catalog.folder_tiers_allsky"])
def redo(ctx):
    """The catalog rows on stars whose light curves have changed, and the stages to redo (lcindex.py)."""
    lc.redo(ctx.input("results_public/candidates_allsky.csv"), ctx.input("results_public/tiers_earlier_candidates.csv"),
            ctx.input(f"{LC}_searched.csv"), ctx.input(f"{LC}.csv"), ctx.input(f"{LC}_current.csv"),
            ctx.input("results_public/products/fits.csv"), ctx.input("results_public/products/triceratops.csv"),
            ctx.output("results_public/products/redo.csv"), ctx.param("catalog.folder_tiers_allsky"))


@check(inputs=["results_public/products/redo.csv"])
def fits_current(ctx):
    rows = lc.stale_fits(ctx.input("results_public/products/redo.csv"))
    assert not rows, (f"{len(rows)} fits were made from light curves that MAST has since redelivered or withdrawn "
                      "(cloud.py plan --fits refits them):\n" + "\n".join(f"{r['table']} TIC {r['TIC']} P {r['P_d']}: "
                                                                          f"redelivered {r['redelivered'] or '-'}, removed "
                                                                          f"{r['removed'] or '-'}" for r in rows[:40]))


@rule(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv",
              "candidates/allsky/*/transit_fit.json", "candidates/allsky/*/vetting.json", "candidates/*/transit_fit.json",
              "candidates/*/vetting.json", "data/catalogs/*.parquet", "data/tess_schedule/TESS_orbit_times.csv"],
      outputs=["candidates/ephemerides.csv", "candidates/predictions.csv"], params=["registry.until"],
      inplace={"candidates/ephemerides.csv": "ledger", "candidates/predictions.csv": "ledger"})
def registry(ctx):
    """The transit registry (predict.py): append-only; newly counted candidates are added with predictions from the
    time of the run, and every registered candidate's tier follows the catalog."""
    predict.register(ctx.param("registry.until"))


@rule(inputs=["results_public/candidates_allsky.csv", "results_cloud/shard*/cands_allsky.csv",
              "results_cloud/as/cands_allsky.csv", "results_cloud/qfull/exo-q*/results/cands_q*.csv",
              "candidates/allsky/*/vetting.json", "data/tess_schedule/TESS_orbit_times.csv"],
      outputs=["validation/findability_transits.csv.gz"], params=["findability.*"])
def findability_transits(ctx):
    """Each counted SNR >= 9 candidate's transits from the search pass that found it (findability.py)."""
    fb.transits(ctx.input("results_public/candidates_allsky.csv"),
                ctx.inputs("results_cloud/shard*/cands_allsky.csv") + [ctx.input("results_cloud/as/cands_allsky.csv")],
                ctx.inputs("results_cloud/qfull/exo-q*/results/cands_q*.csv"), ctx.inputs("candidates/allsky/*/vetting.json"),
                ctx.input("data/tess_schedule/TESS_orbit_times.csv"), ctx.output("validation/findability_transits.csv.gz"),
                ctx.param("findability.tiers"), ctx.param("findability.match_period_rel"))


@rule(inputs=["validation/findability_transits.csv.gz"], outputs=["validation/findability.csv", "validation/findability.json"])
def findability(ctx):
    """SNR by data date and best single sector, per candidate, and the counts (findability.py)."""
    doc_numbers.write(ctx.output("validation/findability.json"),
                      fb.summary(ctx.input("validation/findability_transits.csv.gz"), ctx.output("validation/findability.csv")))


@rule(inputs=["results_public/products/spoc_2min.csv", "validation/findability.csv"],
      outputs=["validation/spoc_2min_recheck.csv"])
def spoc_recheck(ctx):
    """The SPOC 2-minute re-measurements of the candidates with 2-minute data (findability.recheck_table)."""
    fb.recheck_table(ctx.input("results_public/products/spoc_2min.csv"), ctx.input("validation/findability.csv"),
                     ctx.output("validation/spoc_2min_recheck.csv"))


@check(inputs=["results_public/products/spoc_2min.csv", "validation/findability.csv", "validation/findability_transits.csv.gz",
               "results_public/candidates_allsky.csv"], params=["freshness.*"])
def spoc_measured(ctx):
    tol = {k.split(".")[1]: v for k, v in ctx.params().items() if k.startswith("freshness.")}
    problems = fb.recheck_problems(ctx.input("results_public/products/spoc_2min.csv"), ctx.input("validation/findability.csv"),
                                   ctx.input("validation/findability_transits.csv.gz"),
                                   ctx.input("results_public/candidates_allsky.csv"), tol)
    assert not problems, (f"{len(problems)} candidates with 2-minute data need a SPOC re-measurement (spoc_recheck.py):\n"
                          + "\n".join(f"TIC {t} P {p}: {why}" for (t, p), why in sorted(problems.items())))


@rule(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv",
              "candidates/ephemerides.csv", "candidates/predictions.csv", "results_public/funnel_allsky.csv",
              "results_public/products/triceratops.csv", "validation/findability.json", "validation/spoc_2min_recheck.csv",
              "validation/triceratops_inverted_close_neighbour.csv", "validation/false_alarm_classifier_scores_star.csv.gz"],
      outputs=["results_public/numbers.json"], params=["catalog.*", "tiers.centroid_reject_p", "tiers.centroid_neighbour_p",
                                                      "flags.fa_score_min"])
def numbers(ctx):
    out = doc_numbers.compute(
        ctx.input("results_public/candidates_allsky.csv"), ctx.input("results_public/tiers_earlier_candidates.csv"),
        ctx.input("candidates/ephemerides.csv"), ctx.input("candidates/predictions.csv"),
        ctx.input("results_public/funnel_allsky.csv"), ctx.input("results_public/products/triceratops.csv"), ctx.params())
    out.update(doc_numbers.validation(ctx.input("validation/findability.json"), ctx.input("validation/spoc_2min_recheck.csv")))
    out.update(doc_numbers.false_alarms(ctx.input("results_public/funnel_allsky.csv"),
                                        ctx.input("validation/triceratops_inverted_close_neighbour.csv"),
                                        ctx.input("validation/false_alarm_classifier_scores_star.csv.gz"),
                                        ctx.input("results_public/candidates_allsky.csv"), ctx.params()))
    doc_numbers.write(ctx.output("results_public/numbers.json"), out)


DOCS = ("README.md", "results_public/README.md", "validation/findability.md")


@rule(inputs=["results_public/numbers.json"], outputs=list(DOCS), inplace={d: "template" for d in DOCS})
def documents(ctx):
    """The numbers in the documents, between their markers (dag/markers.py)."""
    import json
    from dag.markers import fill
    numbers = json.loads(ctx.input("results_public/numbers.json").read_text())
    for doc in DOCS:
        p = ctx.output(doc)
        p.write_text(fill(p.read_text(), numbers))


# statements in the documents that name values the markers cannot fill: (numbers key, value, where it is stated)
CLAIMS = [("spoc.tce_on_transit_tics", [200744242], "validation/findability.md describes the one SPOC TCE with an epoch "
                                                    "inside our transits, on TIC 200744242")]


@check(inputs=["results_public/numbers.json"])
def prose_claims(ctx):
    import json
    from dag.markers import lookup
    numbers = json.loads(ctx.input("results_public/numbers.json").read_text())
    problems = [f"{key} is {lookup(numbers, key)!r}, not {value!r}: {where}; rewrite it" for key, value, where in CLAIMS
                if lookup(numbers, key) != value]
    assert not problems, "\n".join(problems)


@check(inputs=list(DOCS) + ["results_public/products/README.md"])
def markdown_tables(ctx):
    problems = [x for d in DOCS + ("results_public/products/README.md",) for x in cc.markdown_tables(ctx.input(d))]
    assert not problems, f"{len(problems)} table rows do not match their header:\n" + "\n".join(problems)


@rule(inputs=["results_public/candidates_allsky.csv", "results_cloud/glue/build/folder_sources.csv",
              "results_public/products/triceratops.csv", f"{STORE}/tri/*/*/fpp.json", "results_public/products/fits.csv",
              f"{STORE}/fit/*/*/transit_fit.json"],
      outputs=["candidates/allsky"], params=["catalog.folder_tiers_allsky"], inplace={"candidates/allsky": "ledger"},
      allow_reads=["results_cloud"])
def folders(ctx):
    """Candidate folders (folders.py). Source files are read through the index, which records their hashes."""
    n = fo.build(ctx.root, ctx.input("results_public/candidates_allsky.csv"),
                 ctx.input("results_cloud/glue/build/folder_sources.csv"),
                 ctx.input("results_public/products/triceratops.csv"), ctx.root / STORE,
                 ctx.param("catalog.folder_tiers_allsky"), fits_csv=ctx.input("results_public/products/fits.csv"))
    print(f"folders: {n}")


@check(inputs=["candidates/allsky/*/transit_fit.json", "candidates/*/transit_fit.json", "results_public/candidates_allsky.csv",
               "results_public/tiers_earlier_candidates.csv"])
def fits_match_catalog(ctx):
    problems = cc.fits_match_catalog(ctx.root, ctx.input("results_public/candidates_allsky.csv"),
                                     ctx.input("results_public/tiers_earlier_candidates.csv"))
    assert not problems, f"{len(problems)} catalog values differ from the candidates' fits:\n" + "\n".join(problems[:40])


@check(inputs=["candidates/allsky", "results_public/candidates_allsky.csv", "results_public/products/triceratops.csv"],
       params=["catalog.folder_tiers_allsky"])
def folders_complete(ctx):
    problems = cc.folders_complete(ctx.root, "candidates/allsky", ctx.input("results_public/candidates_allsky.csv"),
                                   ctx.input("results_public/products/triceratops.csv"), "candidates_allsky",
                                   ("vetting.json", "vetting.png", "followup.json"), ctx.param("catalog.folder_tiers_allsky"))
    assert not problems, f"{len(problems)} folder problems:\n" + "\n".join(problems[:40])


@rule(inputs=["results_public/tiers_earlier_candidates.csv", "results_public/products/triceratops.csv",
              f"{STORE}/tri/*/*/fpp.json", "results_public/products/fits.csv", f"{STORE}/fit/*/*/transit_fit.json"],
      outputs=["candidates/TIC*_P*"], inplace={"candidates/TIC*_P*": "ledger"})
def earlier_folders(ctx):
    """The earlier searches' candidate folders (folders.py): every row has one, with the catalog's TRICERATOPS result."""
    n = fo.build_earlier(ctx.root, ctx.input("results_public/tiers_earlier_candidates.csv"),
                         ctx.input("results_public/products/triceratops.csv"), ctx.root / STORE,
                         fits_csv=ctx.input("results_public/products/fits.csv"))
    print(f"earlier folders: {n}")


@check(inputs=["candidates/TIC*_P*", "results_public/tiers_earlier_candidates.csv", "results_public/products/triceratops.csv"])
def earlier_folders_complete(ctx):
    problems = cc.folders_complete(ctx.root, "candidates", ctx.input("results_public/tiers_earlier_candidates.csv"),
                                   ctx.input("results_public/products/triceratops.csv"), "tiers_earlier_candidates",
                                   ("vetting.json", "vetting.png", "transit_fit.json"))
    assert not problems, f"{len(problems)} folder problems:\n" + "\n".join(problems[:40])
