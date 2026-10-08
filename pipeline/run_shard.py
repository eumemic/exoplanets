"""Search one shard of a large target list in chunks, so light curves never pile up on disk: for
each chunk, download, run the stack-slide search, then delete the light curves of stars with no
signal at SNR >= 9 (the vetting threshold; the rest are kept for vetting). Resumable: searched
stars are skipped.

Usage: python run_shard.py TARGETS.parquet MANIFEST.parquet --shard K --nshards N --out DIR
                           [--chunk 10000] [--procs 63]
Shards are every N-th star of TARGETS sorted by TIC ID.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from common import CAT, tic_path

PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("targets")
    ap.add_argument("manifest")
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--nshards", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=10000)
    ap.add_argument("--procs", type=int, default=(os.cpu_count() or 8) - 1)
    ap.add_argument("--keep-snr", type=float, default=9.0)
    ap.add_argument("--chunk-timeout", type=int, default=3600, help="seconds allowed for one chunk's search")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = sorted(pd.read_parquet(a.targets, columns=["ID"])["ID"].astype("int64"))[a.shard::a.nshards]
    done = {int(p.stem) for p in out.glob("*.json")}
    todo = [i for i in ids if i not in done]
    print(f"shard {a.shard}/{a.nshards}: {len(ids):,} stars, {len(todo):,} to search", flush=True)
    t0 = time.time()
    for c in range(0, len(todo), a.chunk):
        chunk = todo[c:c + a.chunk]
        lst = CAT / f"shard{a.shard}_chunk.txt"
        lst.write_text("\n".join(map(str, chunk)) + "\n")
        subprocess.run([PY, "download.py", str(lst), "--manifest", a.manifest, "--workers", "64"],
                       check=True, stdout=subprocess.DEVNULL)
        p = subprocess.Popen([PY, "search.py", str(lst), "--stars", a.targets, "--out", str(out), "--method",
                              "stack", "--procs", str(a.procs)], stdout=subprocess.DEVNULL, start_new_session=True)
        try:
            p.wait(timeout=a.chunk_timeout)
        except subprocess.TimeoutExpired:
            # a pathological star must not stall the shard: stop the chunk and record what is unfinished
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            stuck = [t for t in chunk if not (out / f"{t}.json").exists() and tic_path(t).exists()]
            for t in stuck:
                (out / f"{t}.json").write_text(json.dumps({"tic": t, "error": "search timed out"}))
            print(f"chunk timed out after {a.chunk_timeout} s; {len(stuck)} stars recorded as timed out", flush=True)
        kept = 0
        for tic in chunk:
            f = out / f"{tic}.json"
            sig = json.load(open(f)).get("signals", []) if f.exists() else []
            if any(s["bls_snr"] >= a.keep_snr for s in sig):
                kept += 1
            elif tic_path(tic).exists():
                tic_path(tic).unlink()
        n = c + len(chunk)
        print(f"{n:,}/{len(todo):,} stars  {n / (time.time() - t0):.1f}/s  kept light curves of {kept}",
              flush=True)
    print("SHARD_DONE", flush=True)


if __name__ == "__main__":
    main()
