#!/usr/bin/env python3
"""ADDITIONAL: analyse ONLY a2_6/a2_7/a2_8 (new A60 runs). Reuses verified
metric definitions. Does NOT touch existing n=5 outputs / figures / firmware /
Shared Brain. Original TRC never modified."""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[0]
CANON = HERE.parents[1] / "trace_fixed2" / "analysis_n10"
sys.path.insert(0, str(CANON))
import analyze_fixed2_64b_n10 as canon

NEW = ["a2_6.trc", "a2_7.trc", "a2_8.trc"]
devnull = csv.DictWriter(open(Path(__import__("os").devnull), "w", newline=""),
                         fieldnames=["source_file", "strategy", "load_mode", "load_pct_label",
                                     "run", "analysis_window", "timestamp_us", "gap_us",
                                     "error_us", "abs_error_us"])

rows = {}
for name in NEW:
    p = RAW / name
    run = int(name.split("_")[1].split(".")[0])
    key = canon.FileKey(name, "A", 2, "60", run)
    res = canon.parse_trace(p, key, devnull)
    frames = res["frames"]; header = res["header"]; perr = res["parse_errors"]
    ts = np.asarray([f.timestamp_us for f in frames], dtype=np.int64)
    dur = (ts[-1] - ts[0]) / 1e6 if len(ts) > 1 else 0.0
    nb = float(header["nominal_bit_rate_bps"]); db = float(header["data_bit_rate_bps"])
    if not (np.isfinite(nb) and np.isfinite(db)):
        nb, db = canon.LOOKUP_NOMINAL_BPS, canon.LOOKUP_DATA_BPS
    groups = defaultdict(list)
    for fr in frames:
        groups[fr.can_id].append(fr)
    dummy = [c for c in groups if 0x300 <= c <= 0x30F]
    dummy_frames = sum(len(groups[c]) for c in dummy)
    esi_total = sum(f.esi for f in frames)
    fd_total = sum(f.is_fd for f in frames); brs_total = sum(f.brs for f in frames)
    err_frames = sum(1 for f in frames if "ERR" in f.type_token.upper())
    airtime = 0.0
    for cid, grp in groups.items():
        for payload, cnt in Counter(f.payload for f in grp).items():
            s = next(f for f in grp if f.payload == payload)
            airtime += float(canon.wire_breakdown(cid, payload, s.esi, nb, db, legacy=False)["estimated_airtime_us"]) * cnt
    occ = airtime / (dur * 1e6) * 100 if dur > 0 else np.nan
    bgfps = dummy_frames / dur if dur > 0 else np.nan
    ts100 = np.asarray([f.timestamp_us for f in frames if f.can_id == 0x100], dtype=np.int64)
    m, gaps, errors = canon.interval_metrics(ts100, dur, warmup_us=0)
    expected_ids = set(canon.EXPECTED["A"])
    missing = sorted(expected_ids - set(groups))
    unexpected = sorted(c for c in groups if c not in expected_ids and not (0x300 <= c <= 0x30F))
    qc_pass = (len(perr) == 0 and len(frames) > 0 and int(np.sum(np.diff(ts) < 0)) == 0
               and fd_total == len(frames) and brs_total == len(frames) and esi_total == 0
               and err_frames == 0 and not missing and not unexpected and dummy_frames > 0)
    rows[name] = dict(run=run, dur=dur, occ=occ, bgfps=bgfps, n=m["number_intervals"],
                      jit=m["jitter_std_us"], aem=m["abs_error_mean_us"], aemed=m["abs_error_median_us"],
                      p95=m["abs_error_p95_us"], p99=m["abs_error_p99_us"],
                      gt100=m["abs_error_gt_100us_rate"] * 100, maxint=m["max_gap_us"],
                      gap6=m["gap_gt_6000_count"], near10=m["near_10ms_frame_loss_candidate_count"],
                      esi=esi_total, err=err_frames, qc=qc_pass, frames=len(frames))

print("file  run   dur_s     occ%    bgfps    n0x100   jitter   aeMean  aeMed    p95     p99   >100%   maxInt_ms  gap>6ms  ESI  errFr  QC")
for name in NEW:
    r = rows[name]
    print(f"{name}  {r['run']}  {r['dur']:7.2f}  {r['occ']:6.2f}  {r['bgfps']:7.1f}  {r['n']:6d}  "
          f"{r['jit']:7.2f}  {r['aem']:6.1f}  {r['aemed']:6.1f}  {r['p95']:6.1f}  {r['p99']:6.1f}  "
          f"{r['gt100']:5.2f}  {r['maxint']/1000:8.3f}   {r['gap6']:3d}    {r['esi']:2d}   {r['err']:3d}   {'PASS' if r['qc'] else 'FAIL'}")

print("\n=== Combined A60 run-level jitter (existing r1-5 + new r6-8) ===")
prev = {1: 58.88, 2: 22.93, 3: 22.53, 4: 23.34, 5: 23.45}
allj = dict(prev)
for name in NEW:
    allj[rows[name]["run"]] = rows[name]["jit"]
for run in sorted(allj):
    tag = " (new)" if run >= 6 else ""
    print(f"  A60 run{run} = {allj[run]:6.2f} us{tag}")
r28 = [allj[r] for r in range(2, 9)]
print(f"\nrun2-8 (excl run1): mean {np.mean(r28):.2f} +- {np.std(r28, ddof=1):.2f} us, "
      f"range [{min(r28):.2f}, {max(r28):.2f}]")
print(f"run1 = {allj[1]:.2f} us  (distance from run2-8 mean = {allj[1]-np.mean(r28):+.2f} us, "
      f"{(allj[1]-np.mean(r28))/np.std(r28, ddof=1):.1f} SD)")
print("\nnew-run occupancy/bgfps vs existing r2-5: existing A60 occ~63.6%, bgfps~4125; "
      f"new occ {[round(rows[n]['occ'],2) for n in NEW]}, bgfps {[round(rows[n]['bgfps'],0) for n in NEW]}")
