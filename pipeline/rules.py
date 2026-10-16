"""The build's rules: each published file, the inputs and parameters it is made from, and the function that makes it.
Run from pipeline/ with `../.venv/bin/python -m dag status|run|check` (see dag/__main__.py)."""
import allsky_figure as af
import catalog as cat
import catalog_checks as cc
import centroid_table as ct
import doc_numbers
import folders as fo
import predict
import triceratops_table as tt
from dag import check, rule


@rule(inputs=["results_public/candidates_allsky.csv"], outputs=["figures/allsky.png"], params=["catalog.counted_allsky"])
def allsky_figure(ctx):
    af.draw(ctx.input("results_public/candidates_allsky.csv"), ctx.output("figures/allsky.png"),
            ctx.param("catalog.counted_allsky"))


@rule(inputs=["results_public/products/triceratops_batches.csv", "results_cloud/t2/part*/list.csv",
              "results_cloud/t2/part*/runs.jsonl", "results_cloud/t2/part*/*_fpp.json", "results_cloud/t2/part*/folds/*.npz",
              "results_public/products/measurements_allsky.csv", "results_public/products/measurements_earlier.csv"],
      outputs=["results_public/products/triceratops.csv"], params=["triceratops.*"])
def triceratops_table(ctx):
    rows = [(t, r["TIC"], r["P_d"]) for t, f in (("candidates_allsky", "measurements_allsky.csv"),
                                                 ("tiers_earlier_candidates", "measurements_earlier.csv"))
            for r in cat.read_rows(ctx.input(f"results_public/products/{f}"))]
    tt.build(ctx.input("results_public/products/triceratops_batches.csv"), ctx.root / "results_cloud", rows,
             ctx.output("results_public/products/triceratops.csv"), runs=ctx.param("triceratops.runs"),
             min_survivors=ctx.param("triceratops.min_survivors"), phase_bin_min=ctx.param("triceratops.phase_bin_min"),
             match_rel=ctx.param("triceratops.match_period_rel"))


@rule(inputs=["results_public/products/centroid_batches.csv", "results_cloud/t10/list.csv", "results_cloud/t10/stars.csv",
              "results_cloud/t10/cs/*.json", "results_public/products/measurements_allsky.csv",
              "results_public/products/measurements_earlier.csv"],
      outputs=["results_public/products/centroids.csv"], params=["triceratops.match_period_rel"])
def centroid_table(ctx):
    rows = [(t, r["TIC"], r["P_d"]) for t, f in (("candidates_allsky", "measurements_allsky.csv"),
                                                 ("tiers_earlier_candidates", "measurements_earlier.csv"))
            for r in cat.read_rows(ctx.input(f"results_public/products/{f}"))]
    ct.build(ctx.input("results_public/products/centroid_batches.csv"), ctx.root / "results_cloud", rows,
             ctx.output("results_public/products/centroids.csv"), match_rel=ctx.param("triceratops.match_period_rel"))


@rule(inputs=["results_public/products/measurements_allsky.csv", "results_public/products/measurements_earlier.csv",
              "results_public/products/triceratops.csv", "results_public/products/centroids.csv", "results_public/overrides.csv"],
      outputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv"],
      params=["catalog.counted_allsky", "tiers.*", "flags.*"])
def catalog(ctx):
    P = ctx.params()
    cat.build(ctx.input("results_public/products/measurements_allsky.csv"),
              ctx.input("results_public/products/measurements_earlier.csv"),
              ctx.input("results_public/products/triceratops.csv"), ctx.input("results_public/overrides.csv"),
              ctx.output("results_public/candidates_allsky.csv"), ctx.output("results_public/tiers_earlier_candidates.csv"), P,
              centroids_csv=ctx.input("results_public/products/centroids.csv"))


@check(inputs=["results_public/products/triceratops.csv", "results_public/products/measurements_allsky.csv",
               "candidates/ephemerides.csv"], params=["freshness.*", "triceratops.match_period_rel"])
def triceratops_inputs_current(ctx):
    tol = {k.split(".")[1]: v for k, v in ctx.params().items() if k.startswith("freshness.")}
    problems = cc.triceratops_inputs_current(ctx.input("results_public/products/triceratops.csv"),
                                             ctx.input("results_public/products/measurements_allsky.csv"),
                                             ctx.input("candidates/ephemerides.csv"), tol, ctx.param("triceratops.match_period_rel"))
    assert not problems, f"{len(problems)} TRICERATOPS results ran on inputs that have changed since:\n" + "\n".join(problems)


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


@rule(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv",
              "candidates/allsky/*/transit_fit.json", "candidates/allsky/*/vetting.json", "candidates/*/transit_fit.json",
              "candidates/*/vetting.json", "data/catalogs/*.parquet", "data/tess_schedule/TESS_orbit_times.csv"],
      outputs=["candidates/ephemerides.csv", "candidates/predictions.csv"], params=["registry.until"],
      inplace={"candidates/ephemerides.csv": "ledger", "candidates/predictions.csv": "ledger"})
def registry(ctx):
    """The transit registry (predict.py): append-only; newly counted candidates are added with predictions from the
    time of the run, and every registered candidate's tier follows the catalog."""
    predict.register(ctx.param("registry.until"))


@rule(inputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv",
              "candidates/ephemerides.csv", "candidates/predictions.csv", "results_public/funnel_allsky.csv",
              "results_public/products/triceratops.csv"],
      outputs=["results_public/numbers.json"], params=["catalog.*", "tiers.centroid_reject_p", "tiers.centroid_neighbour_p",
                                                      "flags.fa_score_min"])
def numbers(ctx):
    doc_numbers.write(ctx.output("results_public/numbers.json"), doc_numbers.compute(
        ctx.input("results_public/candidates_allsky.csv"), ctx.input("results_public/tiers_earlier_candidates.csv"),
        ctx.input("candidates/ephemerides.csv"), ctx.input("candidates/predictions.csv"),
        ctx.input("results_public/funnel_allsky.csv"), ctx.input("results_public/products/triceratops.csv"), ctx.params()))


@rule(inputs=["results_public/numbers.json"], outputs=["README.md", "results_public/README.md"],
      inplace={"README.md": "template", "results_public/README.md": "template"})
def documents(ctx):
    """The numbers in the documents, between their markers (dag/markers.py)."""
    import json
    from dag.markers import fill
    numbers = json.loads(ctx.input("results_public/numbers.json").read_text())
    for doc in ("README.md", "results_public/README.md"):
        p = ctx.output(doc)
        p.write_text(fill(p.read_text(), numbers))


@check(inputs=["README.md", "results_public/README.md", "results_public/products/README.md"])
def markdown_tables(ctx):
    problems = [x for d in ("README.md", "results_public/README.md", "results_public/products/README.md")
                for x in cc.markdown_tables(ctx.input(d))]
    assert not problems, f"{len(problems)} table rows do not match their header:\n" + "\n".join(problems)


@rule(inputs=["results_public/candidates_allsky.csv", "results_cloud/glue/build/folder_sources.csv",
              "results_public/products/triceratops.csv", "results_cloud/t2/part*/*_fpp.json"],
      outputs=["candidates/allsky"], params=["catalog.folder_tiers_allsky"], inplace={"candidates/allsky": "ledger"},
      allow_reads=["results_cloud"])
def folders(ctx):
    """Candidate folders (folders.py). Source files are read through the index, which records their hashes."""
    n = fo.build(ctx.root, ctx.input("results_public/candidates_allsky.csv"),
                 ctx.input("results_cloud/glue/build/folder_sources.csv"),
                 ctx.input("results_public/products/triceratops.csv"), ctx.root / "results_cloud",
                 ctx.param("catalog.folder_tiers_allsky"))
    print(f"folders: {n}")


@check(inputs=["candidates/allsky", "results_public/candidates_allsky.csv", "results_public/products/triceratops.csv"],
       params=["catalog.folder_tiers_allsky"])
def folders_complete(ctx):
    problems = cc.folders_complete(ctx.root, "candidates/allsky", ctx.input("results_public/candidates_allsky.csv"),
                                   ctx.input("results_public/products/triceratops.csv"), "candidates_allsky",
                                   ("vetting.json", "vetting.png", "followup.json"), ctx.param("catalog.folder_tiers_allsky"))
    assert not problems, f"{len(problems)} folder problems:\n" + "\n".join(problems[:40])


@rule(inputs=["results_public/tiers_earlier_candidates.csv", "results_public/products/triceratops.csv",
              "results_cloud/t2/part*/*_fpp.json"],
      outputs=["candidates/TIC*_P*"], inplace={"candidates/TIC*_P*": "ledger"})
def earlier_folders(ctx):
    """The earlier searches' candidate folders (folders.py): every row has one, with the catalog's TRICERATOPS result."""
    n = fo.build_earlier(ctx.root, ctx.input("results_public/tiers_earlier_candidates.csv"),
                         ctx.input("results_public/products/triceratops.csv"), ctx.root / "results_cloud")
    print(f"earlier folders: {n}")


@check(inputs=["candidates/TIC*_P*", "results_public/tiers_earlier_candidates.csv", "results_public/products/triceratops.csv"])
def earlier_folders_complete(ctx):
    problems = cc.folders_complete(ctx.root, "candidates", ctx.input("results_public/tiers_earlier_candidates.csv"),
                                   ctx.input("results_public/products/triceratops.csv"), "tiers_earlier_candidates",
                                   ("vetting.json", "vetting.png", "transit_fit.json"))
    assert not problems, f"{len(problems)} folder problems:\n" + "\n".join(problems[:40])
