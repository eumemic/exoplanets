"""The build's rules: each published file, the inputs and parameters it is made from, and the function that makes it.
Run from pipeline/ with `../.venv/bin/python -m dag status|run|check` (see dag/__main__.py)."""
import allsky_figure as af
import catalog as cat
import catalog_checks as cc
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


@rule(inputs=["results_public/products/measurements_allsky.csv", "results_public/products/measurements_earlier.csv",
              "results_public/products/triceratops.csv", "results_public/overrides.csv"],
      outputs=["results_public/candidates_allsky.csv", "results_public/tiers_earlier_candidates.csv"],
      params=["catalog.counted_allsky", "tiers.*", "flags.*"])
def catalog(ctx):
    P = ctx.params()
    cat.build(ctx.input("results_public/products/measurements_allsky.csv"),
              ctx.input("results_public/products/measurements_earlier.csv"),
              ctx.input("results_public/products/triceratops.csv"), ctx.input("results_public/overrides.csv"),
              ctx.output("results_public/candidates_allsky.csv"), ctx.output("results_public/tiers_earlier_candidates.csv"), P)


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
