"""MOLUSC samples other than the catalog's, to measure how much a signal's Gaia-limited FPP depends on its sample of
simulated companions: molusc_batch.py with the seed of sample k (EXO_MOLUSC_SAMPLE, k > 0) in place of the star's
catalog seed (molusc_batch.molusc_seed, sample 0). The catalog does not use these samples: `cloud.py plan
--molusc-sample k` puts them in batches run into a store of their own (cloud.py run --store).

Usage: EXO_MOLUSC_SAMPLE=k python molusc_sample.py ARGS   (the arguments of molusc_batch.py)
"""
import hashlib
import os
import sys

import molusc_batch as mb


def sample_seed(tic, k):
    """The seed of a star's MOLUSC sample k (sample 0 is the catalog's)."""
    if int(k) == 0:
        return getattr(mb.molusc_seed, "__wrapped__", mb.molusc_seed)(tic)
    return int.from_bytes(hashlib.sha256(f"molusc|{int(tic)}|{int(k)}".encode()).digest()[:4], "little")


def use_sample(k):
    """molusc_batch with sample k's seed; each star runs in a subprocess of this file, with the same sample."""
    seed = mb.molusc_seed.__wrapped__ if hasattr(mb.molusc_seed, "__wrapped__") else mb.molusc_seed

    def molusc_seed(tic):
        return seed(tic) if int(k) == 0 else sample_seed(tic, k)
    molusc_seed.__wrapped__ = seed
    mb.molusc_seed = molusc_seed
    mb.__file__ = os.path.abspath(__file__)


def main():
    use_sample(int(os.environ.get("EXO_MOLUSC_SAMPLE", "0")))
    return mb.main()


if __name__ == "__main__":
    sys.exit(main())
