"""Compare two search output directories (signals with SNR>=9 and >=3 good events)."""
import glob
import json
import sys


def load(d):
    out = {}
    for f in glob.glob(d + "/*.json"):
        r = json.load(open(f))
        if "signals" in r:
            out[r["tic"]] = r
    return out


def match(p, q):
    return any(abs(p / (q * h) - 1) < 0.002 for h in (0.5, 1, 2))


A, B = load(sys.argv[1]), load(sys.argv[2])
A.update({k: v for k, v in load("../results/search_controls").items() if k not in A})
found = missed = 0
miss, new = [], []
for tic, rb in B.items():
    ra = A.get(tic)
    if not ra:
        continue
    for s in ra["signals"]:
        if s["bls_snr"] >= 9 and s["n_good_events"] >= 3:
            if any(match(s["period"], x["period"]) for x in rb["signals"]):
                found += 1
            else:
                missed += 1
                miss.append((tic, round(s["period"], 4), round(s["bls_snr"], 1), round(s["sde"], 1),
                             [(round(x["period"], 4), round(x["bls_snr"], 1)) for x in rb["signals"]]))
    for x in rb["signals"]:
        if x["bls_snr"] >= 9 and x["n_good_events"] >= 3 and not any(match(x["period"], s["period"]) for s in ra["signals"]):
            new.append((tic, round(x["period"], 4), round(x["bls_snr"], 1)))
print(f"A signals recovered in B: {found}, missed: {missed}; B-only signals: {len(new)}")
for m in miss:
    print("  MISSED", m)
for t in (4206066, 150428135, 307210830):
    if t in B:
        print(t, [(round(s["period"], 5), round(s["bls_snr"], 1)) for s in B[t]["signals"]])
