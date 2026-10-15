"""TRICERATOPS probabilities combined with the centroid Bayes factor BF = L(target) / max L(capable neighbour)
(README, tier N): the nearby-star scenarios are weighted by 1/BF and the probabilities renormalised.

FPP and NFPP must describe the same runs. The combined FPP uses the means of the ten runs' FPP and NFPP; the combined
NFPP, used for the limit NFPP_c < 0.1, uses the largest NFPP of the runs, which is conservative. Until 14 October 2026
the combined FPP also used the largest NFPP; where it exceeded the mean FPP the result was negative
(validation/fpp_combination.md)."""
import math


def combine(fpp_mean, nfpp_mean, nfpp_max, bf):
    """(FPP_c, NFPP_c). Without a Bayes factor (no capable neighbour within 30") the TRICERATOPS values stand."""
    if bf is None or not math.isfinite(bf):
        return fpp_mean, nfpp_max
    fpp_c = 1 - (1 - fpp_mean) / (1 - nfpp_mean + nfpp_mean / bf)
    nfpp_c = (nfpp_max / bf) / (1 - nfpp_max + nfpp_max / bf)
    return fpp_c, nfpp_c
