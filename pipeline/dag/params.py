"""Shared thresholds and settings from pipeline/params.toml, addressed by dotted keys ("tiers.fpp_bar").

A rule declares the keys it reads, exactly or by prefix ("tiers.*"). Only those values enter its hash, so changing
one threshold reruns only the rules that use it.
"""
import tomllib


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


def load(path):
    with open(path, "rb") as fh:
        return flatten(tomllib.load(fh))


def matches(key, pattern):
    return key == pattern or (pattern.endswith(".*") and key.startswith(pattern[:-1]))


def select(params, patterns):
    """The values of the declared keys. A pattern that matches no key is an error, so a misspelt key fails loudly
    instead of silently reading nothing."""
    out = {}
    for p in patterns:
        hit = {k: v for k, v in params.items() if matches(k, p)}
        if not hit:
            raise KeyError(f"parameter {p!r} is not in params.toml")
        out.update(hit)
    return out
