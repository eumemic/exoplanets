"""A small build system for this repository: every published file is rebuilt from declared inputs by declared code,
and rebuilt again whenever any of them changes. See graph.py for the model and README "Build" for the commands."""
from .graph import BuildError, Project, check, rule  # noqa: F401
