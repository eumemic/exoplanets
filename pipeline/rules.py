"""The build's rules: each published file, the inputs and parameters it is made from, and the function that makes it.
Run from pipeline/ with `../.venv/bin/python -m dag status|run|check` (see dag/__main__.py)."""
import allsky_figure as af
from dag import rule


@rule(inputs=["results_public/candidates_allsky.csv"], outputs=["figures/allsky.png"], params=["catalog.counted_allsky"])
def allsky_figure(ctx):
    af.draw(ctx.input("results_public/candidates_allsky.csv"), ctx.output("figures/allsky.png"),
            ctx.param("catalog.counted_allsky"))
