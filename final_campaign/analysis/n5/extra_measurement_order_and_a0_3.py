#!/usr/bin/env python3
"""ADDITIONAL analysis only. Does NOT regenerate any existing n=5 CSV/figure.

Part 1: build measurement_order.csv (61 TRC sorted by header start datetime),
        using values already computed in qc_by_file.csv + run_level_metrics.csv.
Part 2: raw +/-50 ms sequence around the a0_3.trc 0x100 30 ms gap, checking
        whether other A control IDs (0x101/0x102/0x110/0x120/0x130) persist.
No firmware/build. No Shared Brain writes. Original TRC never modified.
"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[0]  # ...\3node
FNAME_RE = re.compile(r"^([abc])([0-3])_(\d+)\.trc$", re.I)
TARGET = {0: "baseline", 1: "30", 2: "60", 3: "80"}


def parse_dt(s: str):
    # header form: "2026-08-12 02:32:27.053.0" -> take first 23 chars
    return datetime.strptime(str(s)[:23], "%Y-%m-%d %H:%M:%S.%f")


# ---------- Part 1: measurement_order.csv ----------------------------------
qc = pd.read_csv(HERE / "qc_by_file.csv")
rl = pd.read_csv(HERE / "run_level_metrics.csv")
j = rl.set_index("source_file")["jitter_std_us"].to_dict()
occ = rl.set_index("source_file")["reconstructed_occupancy_pct"].to_dict()

rows = []
for _, r in qc.iterrows():
    f = r["source_file"]
    m = FNAME_RE.fullmatch(str(f))
    if not m:
        continue
    rows.append(dict(
        datetime=parse_dt(r["start_time_text"]),
        filename=f, strategy=m.group(1).upper(),
        target=TARGET[int(m.group(2))], run=int(m.group(3)),
        jitter_us=round(float(j.get(f, float("nan"))), 3),
        reconstructed_occupancy=round(float(occ.get(f, float("nan"))), 4),
    ))
rows.sort(key=lambda x: x["datetime"])
out = []
for i, row in enumerate(rows):
    prev = rows[i - 1] if i > 0 else None
    out.append(dict(
        order=i + 1,
        datetime=row["datetime"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        filename=row["filename"], strategy=row["strategy"],
        target=row["target"], run=row["run"],
        previous_filename=(prev["filename"] if prev else ""),
        previous_strategy=(prev["strategy"] if prev else ""),
        previous_target=(prev["target"] if prev else ""),
        jitter_us=row["jitter_us"], reconstructed_occupancy=row["reconstructed_occupancy"],
    ))
mo = pd.DataFrame(out)
mo.to_csv(HERE / "measurement_order.csv", index=False, encoding="utf-8-sig", lineterminator="\n")

print("=== measurement_order.csv written; full chronological order ===")
print(mo[["order", "datetime", "filename", "strategy", "target", "run",
          "previous_filename", "jitter_us"]].to_string(index=False))

print("\n=== focus: A30 run1 (a1_1) and A60 run1 (a2_1) context ===")
for fn in ("a1_1.trc", "a2_1.trc"):
    o = mo[mo.filename == fn]["order"].iloc[0]
    ctx = mo[(mo.order >= o - 2) & (mo.order <= o + 1)]
    print(f"\n-- {fn} (order {o}) with neighbours --")
    print(ctx[["order", "datetime", "filename", "strategy", "target", "run", "jitter_us"]].to_string(index=False))

print("\n=== per-day first-appearance of each A condition (is run1 the day/session-first & transition-first?) ===")
mo["day"] = mo["datetime"].str[:10]
for cond in ("A30", "A60", "A80"):
    s, t = cond[0], cond[1:]
    sub = mo[(mo.strategy == s) & (mo.target == t)].sort_values("order")
    print(f"\n{cond}:")
    for _, r in sub.iterrows():
        first_A_of_day = mo[(mo.strategy == "A") & (mo.day == r.day)].order.min() == r.order
        print(f"  order {int(r.order):2d} {r.filename} run{int(r.run)} day {r.day} "
              f"jitter {r.jitter_us:6.2f}  prev={r.previous_filename}"
              f"{'  <-- first A of day' if first_A_of_day else ''}")


# ---------- Part 2: a0_3.trc anomaly +/-50 ms raw sequence -------------------
print("\n\n=== Part 2: a0_3.trc 0x100 30 ms gap, +/-50 ms raw window ===")
line_re = re.compile(
    r"^\s*(\d+)\s+([\d.]+)\s+\S+\s+([0-9A-Fa-f]+)\s+\w+\s+(\d+)\s*(.*)$")
recs = []
for ln in (RAW / "a0_3.trc").read_text(errors="replace").splitlines():
    if ln.lstrip().startswith(";") or not ln.strip():
        continue
    m = line_re.match(ln)
    if not m:
        continue
    recs.append(dict(num=int(m.group(1)), t_ms=float(m.group(2)),
                     cid=int(m.group(3), 16), dlc=int(m.group(4))))
df = pd.DataFrame(recs)
p100 = df[df.cid == 0x100].reset_index(drop=True)
gaps = p100["t_ms"].diff()
gi = gaps.idxmax()
g_before = p100.loc[gi - 1]
g_after = p100.loc[gi]
print(f"total records parsed: {len(df)}  0x100 count: {len(p100)}")
print(f"largest 0x100 gap = {gaps.max():.3f} ms, between "
      f"msgNum {int(g_before.num)} (t={g_before.t_ms:.3f} ms) and "
      f"msgNum {int(g_after.num)} (t={g_after.t_ms:.3f} ms). "
      f"msgNum delta = {int(g_after.num - g_before.num)} (==1 means PCAN stored nothing between)")

lo, hi = g_before.t_ms - 50.0, g_after.t_ms + 50.0
win = df[(df.t_ms >= lo) & (df.t_ms <= hi)].copy()
print(f"\nwindow [{lo:.3f}, {hi:.3f}] ms  -> {len(win)} frames")
print("ID counts in window:", {f"0x{k:03X}": int(v) for k, v in win.cid.value_counts().sort_index().items()})

interior = df[(df.t_ms > g_before.t_ms) & (df.t_ms < g_after.t_ms)]
print(f"\nframes strictly INSIDE the 30 ms 0x100 gap: {len(interior)}")
if not interior.empty:
    print("interior ID counts:", {f"0x{k:03X}": int(v) for k, v in interior.cid.value_counts().sort_index().items()})
    print(interior[["num", "t_ms", "cid", "dlc"]].assign(
        cid=lambda d: d.cid.map(lambda x: f"0x{x:03X}")).to_string(index=False))
else:
    print("-> NO frames of ANY ID inside the 30 ms gap (bus/capture-wide silence).")

print("\n-- last 6 frames before gap --")
print(df[df.t_ms <= g_before.t_ms].tail(6).assign(
    cid=lambda d: d.cid.map(lambda x: f"0x{x:03X}"))[["num", "t_ms", "cid", "dlc"]].to_string(index=False))
print("\n-- first 6 frames at/after gap end --")
print(df[df.t_ms >= g_after.t_ms].head(6).assign(
    cid=lambda d: d.cid.map(lambda x: f"0x{x:03X}"))[["num", "t_ms", "cid", "dlc"]].to_string(index=False))

exp_A = [0x100, 0x101, 0x102, 0x110, 0x120, 0x130]
print("\nExpected A control IDs present anywhere in file:",
      {f"0x{c:03X}": int((df.cid == c).sum()) for c in exp_A})
