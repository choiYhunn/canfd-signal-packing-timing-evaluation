#!/usr/bin/env python3
"""3-node gap-sweep response analysis (marker-segmented, timestamp-only).

Reads the 6 sweep TRC in 3node_fixed_bg/ (A/B/C x {gap230_240, gap242_250}),
reconstructs the sweep from the 0x7F0 markers, and analyses each usable 20 s
point. Reuses the verified n=10 module for parsing + wire_breakdown airtime.

Raw TRC never modified. Output only under this folder. No firmware/build.

MARKER (0x7F0) payload (firmware canfd_background_tx_gap_sweep):
  [0]=0xA5 [1]=0x5A magic, [2]=group, [3]=index, [4:6]=configured gap us (LE),
  [6]=0x01 START / 0xEE END, [7]=active_count(8). Marker is EXCLUDED from every
  statistic (occupancy / BG fps / total fps / jitter / ACF).

configured_gap_us (from marker/record) and observed_onwire_bg_spacing (from TRC)
are kept as separate columns; configured gap is NEVER reverse-inferred.
"""
from __future__ import annotations
import csv, os, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RAW = REPO / "3node_fixed_bg"
CANON = REPO / "trace_fixed2" / "analysis_n10"
CONF = REPO / "3node" / "analysis_fixed_bg_confirmatory" / "condition_summary.csv"
sys.path.insert(0, str(CANON))
import analyze_fixed2_64b_n10 as canon
FIG = HERE / "figures"; FIG.mkdir(parents=True, exist_ok=True)

PERIOD = 5000.0
MARKER_ID = 0x7F0
SETTLE_US = 2_000_000
MEASURE_US = 20_000_000
COLORS = {"A": "#0072B2", "B": "#D55E00", "C": "#009E73"}
FILES = [("A", "A_gap230_240.trc", 1), ("A", "A_gap242_250.trc", 2),
         ("B", "B_gap230_240.trc", 1), ("B", "B_gap242_250.trc", 2),
         ("C", "C_gap230_240.trc", 1), ("C", "C_gap242_250.trc", 2)]
STRAT_MODE = {"A": 2, "B": 2, "C": 2}   # sweep runs in the 60/M regime for all
_dev = csv.DictWriter(open(os.devnull, "w", newline=""),
    fieldnames=["source_file","strategy","load_mode","load_pct_label","run",
                "analysis_window","timestamp_us","gap_us","error_us","abs_error_us"])


def parse(path, strategy):
    key = canon.FileKey(path.name, strategy, 2, "60", 1)
    res = canon.parse_trace(path, key, _dev)
    return res["frames"], res["header"]


def markers_of(frames):
    out = []
    for f in frames:
        if f.can_id == MARKER_ID:
            p = f.payload
            if len(p) >= 8 and p[0] == 0xA5 and p[1] == 0x5A:
                out.append(dict(t_us=f.timestamp_us, group=p[2], index=p[3],
                                gap_us=p[4] | (p[5] << 8),
                                mtype=("START" if p[6] == 0x01 else ("END" if p[6] == 0xEE else f"0x{p[6]:02X}")),
                                active=p[7]))
    out.sort(key=lambda m: m["t_us"])
    return out


def win_metrics(frames, strategy, header, t_lo, t_hi):
    nb = float(header["nominal_bit_rate_bps"]); db = float(header["data_bit_rate_bps"])
    if not (np.isfinite(nb) and np.isfinite(db)):
        nb, db = canon.LOOKUP_NOMINAL_BPS, canon.LOOKUP_DATA_BPS
    win = [f for f in frames if t_lo <= f.timestamp_us < t_hi and f.can_id != MARKER_ID]
    ts = np.array([f.timestamp_us for f in win], float)
    cid = np.array([f.can_id for f in win], int)
    dur = (ts.max() - ts.min()) / 1e6 if len(ts) > 1 else 0.0
    exp = canon.EXPECTED[strategy]
    groups = defaultdict(list)
    for f in win:
        groups[f.can_id].append(f)
    # airtime split
    air_ctrl = air_bg = 0.0
    esi = fd = brs = 0; err = 0
    payload_ok = layout_ok = True
    for c, grp in groups.items():
        pc = Counter(f.payload for f in grp)
        esi += sum(f.esi for f in grp); fd += sum(f.is_fd for f in grp); brs += sum(f.brs for f in grp)
        err += sum(1 for f in grp if "ERR" in f.type_token.upper())
        a = 0.0
        for pl, cnt in pc.items():
            s = next(f for f in grp if f.payload == pl)
            a += float(canon.wire_breakdown(c, pl, s.esi, nb, db, legacy=False)["estimated_airtime_us"]) * cnt
        if 0x300 <= c <= 0x30F: air_bg += a
        elif c in exp:
            air_ctrl += a
            if sorted({f.length for f in grp}) != [exp[c][0]]: layout_ok = False
            if c in canon.EXPECTED_PAYLOAD[strategy] and not (len(pc) == 1 and next(iter(pc)) == canon.EXPECTED_PAYLOAD[strategy][c]):
                payload_ok = False
    occ_tot = (air_ctrl + air_bg) / (dur * 1e6) * 100 if dur > 0 else np.nan
    occ_ctrl = air_ctrl / (dur * 1e6) * 100 if dur > 0 else np.nan
    occ_bg = air_bg / (dur * 1e6) * 100 if dur > 0 else np.nan
    bg_ts = np.sort(ts[(cid >= 0x300) & (cid <= 0x30F)])
    bg_ids = sorted(set(cid[(cid >= 0x300) & (cid <= 0x30F)].tolist()))
    bg_n = len(bg_ts)
    if bg_n > 2:
        d = np.diff(bg_ts); d = d[d > 0]
        vals, cnts = np.unique(d, return_counts=True)
        bg_med = float(np.median(d)); bg_mode = int(vals[np.argmax(cnts)])
        bg_p10, bg_p90 = float(np.percentile(d, 10)), float(np.percentile(d, 90))
        bg_iqr = float(np.percentile(d, 75) - np.percentile(d, 25)); bg_std = float(d.std())
    else:
        bg_med = bg_mode = bg_p10 = bg_p90 = bg_iqr = bg_std = np.nan
    ctrl_n = sum(len(groups[c]) for c in groups if c in exp)
    # 0x100 timing
    ts100 = np.sort(ts[cid == 0x100])
    m, gaps, errors = canon.interval_metrics(ts100, dur, warmup_us=0)
    gap10 = int(np.sum(gaps > 10000)) if len(gaps) else 0
    # ACF
    e = errors[np.isfinite(errors)]
    acf1 = domlag = domacf = np.nan; acfcurve = []
    if len(e) > 50:
        e0 = e - e.mean(); var = float(np.dot(e0, e0))
        if var > 0:
            ml = min(400, len(e0) - 2)
            ac = np.array([np.dot(e0[:-L], e0[L:]) / var for L in range(1, ml + 1)])
            acf1 = float(ac[0]); seg = ac[1:]
            di = int(np.argmax(seg)) + 2 if len(seg) else -1
            domlag = di; domacf = float(ac[di - 1]) if di > 0 else np.nan; acfcurve = ac.tolist()
    obs_0x100_dlc = sorted({f.length for f in groups.get(0x100, [])})
    struct_fail = (esi > 0 or err > 0 or not layout_ok or not payload_ok
                   or (obs_0x100_dlc != [exp[0x100][0]] if 0x100 in groups else True)
                   or bg_n == 0)
    return dict(dur=dur, total_frames=len(win), frame_0x100=int(len(ts100)), bg_frames=bg_n,
                ctrl_frames=ctrl_n, occ_tot=occ_tot, occ_ctrl=occ_ctrl, occ_bg=occ_bg,
                total_fps=len(win)/dur if dur>0 else np.nan, ctrl_fps=ctrl_n/dur if dur>0 else np.nan,
                bg_fps=bg_n/dur if dur>0 else np.nan,
                bg_spacing_median=bg_med, bg_spacing_mode=bg_mode, bg_spacing_p10=bg_p10,
                bg_spacing_p90=bg_p90, bg_spacing_iqr=bg_iqr, bg_spacing_std=bg_std,
                bg_ids="|".join(f"0x{c:03X}" for c in bg_ids), n_bg_ids=len(bg_ids),
                mean_interval=m["mean_gap_us"], median_interval=m["median_gap_us"],
                jitter=m["jitter_std_us"], mae=m["abs_error_mean_us"], mae_median=m["abs_error_median_us"],
                p95=m["abs_error_p95_us"], p99=m["abs_error_p99_us"],
                gt100=m["abs_error_gt_100us_rate"]*100 if np.isfinite(m["abs_error_gt_100us_rate"]) else np.nan,
                max_interval=m["max_gap_us"], gap6=m["gap_gt_6000_count"], gap10=gap10,
                esi=esi, err=err, layout_ok=layout_ok, payload_ok=payload_ok,
                obs_0x100_dlc="|".join(map(str, obs_0x100_dlc)), struct_fail=struct_fail,
                acf1=acf1, domlag=domlag, domacf=domacf, acfcurve=acfcurve)


def main():
    seg_rows, qc_rows, metric_rows, bg_rows, occ_rows = [], [], [], [], []
    acf_map = {}
    for strategy, fname, group in FILES:
        p = RAW / fname
        frames, header = parse(p, strategy)
        eof_us = max(f.timestamp_us for f in frames)
        mk = markers_of(frames)
        starts = [m for m in mk if m["mtype"] == "START"]
        ends = [m for m in mk if m["mtype"] == "END"]
        for i, m in enumerate(mk):
            seg_rows.append(dict(file=fname, strategy=strategy, group=m["group"], index=m["index"],
                                 configured_gap_us=m["gap_us"], marker_type=m["mtype"],
                                 marker_t_ms=round(m["t_us"]/1000, 3), active_count=m["active"]))
        # build points from START markers
        for j, s in enumerate(starts):
            nxt = starts[j+1]["t_us"] if j+1 < len(starts) else (ends[0]["t_us"] if ends else eof_us)
            avail_us = nxt - s["t_us"] - SETTLE_US
            t_lo = s["t_us"] + SETTLE_US
            t_hi = t_lo + MEASURE_US
            enough = avail_us >= MEASURE_US
            if not enough:
                t_hi = min(t_hi, nxt)   # use whatever is there (for reporting only)
            wm = win_metrics(frames, strategy, header, t_lo, t_hi)
            usable_s = (t_hi - t_lo) / 1e6
            if wm["struct_fail"]:
                status = "FAIL"
            elif not enough:
                status = "FAIL"     # window shorter than the required 20 s measurement
            elif wm["gap6"] > 0 or wm["gap10"] > 0:
                status = "PASS_WITH_TIMING_NOTE"
            else:
                status = "PASS"
            note = ("" if enough else
                    f"TRUNCATED: only {avail_us/1e6:.2f}s available after 2s settle (<20s); capture ended early")
            qc_rows.append(dict(file=fname, strategy=strategy, group=s["group"], index=s["index"],
                                configured_gap_us=s["gap_us"], usable_window_s=round(usable_s, 3),
                                required_s=20.0, enough_window=enough, total_frames=wm["total_frames"],
                                frame_0x100=wm["frame_0x100"], bg_frames=wm["bg_frames"],
                                esi=wm["esi"], error_frames=wm["err"], layout_ok=wm["layout_ok"],
                                payload_ok=wm["payload_ok"], obs_0x100_dlc=wm["obs_0x100_dlc"],
                                gap6=wm["gap6"], gap10=wm["gap10"], qc_status=status, note=note))
            valid = enough and not wm["struct_fail"]
            metric_rows.append(dict(strategy=strategy, configured_gap_us=s["gap_us"], group=s["group"],
                                    index=s["index"], valid_20s=valid, usable_window_s=round(usable_s, 3),
                                    n_intervals=wm["frame_0x100"]-1, mean_interval_us=wm["mean_interval"],
                                    median_interval_us=wm["median_interval"], jitter_us=wm["jitter"],
                                    mae_us=wm["mae"], mae_median_us=wm["mae_median"], p95_us=wm["p95"],
                                    p99_us=wm["p99"], gt100_pct=wm["gt100"], max_interval_us=wm["max_interval"],
                                    gap6=wm["gap6"], gap10=wm["gap10"]))
            bg_rows.append(dict(strategy=strategy, configured_gap_us=s["gap_us"], valid_20s=valid,
                                bg_fps=wm["bg_fps"], total_fps=wm["total_fps"], ctrl_fps=wm["ctrl_fps"],
                                observed_bg_spacing_median_us=wm["bg_spacing_median"],
                                observed_bg_spacing_mode_us=wm["bg_spacing_mode"],
                                observed_bg_spacing_p10_us=wm["bg_spacing_p10"],
                                observed_bg_spacing_p90_us=wm["bg_spacing_p90"],
                                observed_bg_spacing_iqr_us=wm["bg_spacing_iqr"],
                                observed_bg_spacing_std_us=wm["bg_spacing_std"],
                                n_bg_ids=wm["n_bg_ids"], bg_ids=wm["bg_ids"]))
            occ_rows.append(dict(strategy=strategy, configured_gap_us=s["gap_us"], valid_20s=valid,
                                 reconstructed_total_occ_pct=wm["occ_tot"], reconstructed_control_occ_pct=wm["occ_ctrl"],
                                 reconstructed_bg_occ_pct=wm["occ_bg"], total_fps=wm["total_fps"],
                                 control_fps=wm["ctrl_fps"], bg_fps=wm["bg_fps"], actual_pcan_mean_load="UNKNOWN"))
            if valid:
                acf_map[(strategy, s["gap_us"])] = np.array(wm["acfcurve"])

    seg_df = pd.DataFrame(seg_rows); qc_df = pd.DataFrame(qc_rows)
    met_df = pd.DataFrame(metric_rows); bg_df = pd.DataFrame(bg_rows); occ_df = pd.DataFrame(occ_rows)

    def w(d, n): d.to_csv(HERE / n, index=False, encoding="utf-8-sig", lineterminator="\n")
    w(seg_df, "marker_segments.csv"); w(qc_df, "point_qc.csv")
    w(met_df, "gap_response_metrics.csv"); w(bg_df, "bg_timing_metrics.csv"); w(occ_df, "occupancy_metrics.csv")

    valid = met_df[met_df.valid_20s].copy()

    # combine with confirmatory gap240 (n=5 mean) for a 3-gap mini-curve
    combo = []
    for _, r in valid.iterrows():
        combo.append(dict(strategy=r.strategy, configured_gap_us=int(r.configured_gap_us),
                          jitter_us=r.jitter_us, occ_tot=occ_df[(occ_df.strategy==r.strategy)&(occ_df.configured_gap_us==r.configured_gap_us)&(occ_df.valid_20s)].reconstructed_total_occ_pct.iloc[0],
                          source="sweep_n1_20s"))
    if CONF.exists():
        c = pd.read_csv(CONF)
        for _, r in c[c.bg_level == "M"].iterrows():
            combo.append(dict(strategy=r.strategy, configured_gap_us=240, jitter_us=r.jitter_mean,
                              occ_tot=r.occ_total_mean, source="confirmatory_n5_mean"))
    combo_df = pd.DataFrame(combo).sort_values(["strategy", "configured_gap_us"])
    w(combo_df, "gap_response_with_confirmatory240.csv")

    # similar-load comparisons among valid + confirmatory points
    sl = []
    pts = combo_df.to_dict("records")
    for i in range(len(pts)):
        for j in range(i+1, len(pts)):
            a, b = pts[i], pts[j]
            if a["strategy"] == b["strategy"]:
                continue
            docc = abs(a["occ_tot"] - b["occ_tot"])
            if docc <= 2.0:
                sl.append(dict(pair=f"{a['strategy']}g{a['configured_gap_us']}_vs_{b['strategy']}g{b['configured_gap_us']}",
                               occ_a=round(a["occ_tot"],2), occ_b=round(b["occ_tot"],2), occ_diff_pp=round(docc,2),
                               jitter_a=round(a["jitter_us"],2), jitter_b=round(b["jitter_us"],2),
                               jitter_diff_us=round(abs(a["jitter_us"]-b["jitter_us"]),2),
                               src_a=a["source"], src_b=b["source"]))
    sl_df = pd.DataFrame(sl).sort_values("jitter_diff_us", ascending=False) if sl else pd.DataFrame()
    w(sl_df, "similar_load_comparisons.csv")

    # candidate confirmatory points: the whole sweep must be recaptured; list valid + missing
    cand = []
    missing = {1: [232,234,236,238,240], 2: [244,246,248,250]}
    for s in ("A","B","C"):
        cand.append(dict(strategy=s, configured_gap_us=230, reason="only fully-captured GROUP1 point; anchor", priority="captured(n=1)"))
        cand.append(dict(strategy=s, configured_gap_us=242, reason="only fully-captured GROUP2 point; anchor", priority="captured(n=1)"))
    for g in (234, 236, 238, 240):
        cand.append(dict(strategy="A/B/C", configured_gap_us=g, reason="never captured; 234-240 is the region of the old 235/238/240 concern", priority="RECAPTURE_HIGH"))
    cand_df = pd.DataFrame(cand); w(cand_df, "candidate_confirmatory_points.csv")

    make_figures(combo_df, valid, bg_df, occ_df, acf_map)
    write_report(seg_df, qc_df, met_df, bg_df, occ_df, combo_df, sl_df)
    print("valid 20s points:", len(valid), "of", len(met_df), "START points")
    print(valid[["strategy","configured_gap_us","jitter_us"]].to_string(index=False))


def make_figures(combo_df, valid, bg_df, occ_df, acf_map):
    # Fig1: configured gap -> jitter (points only; sweep incomplete)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for s in ("A","B","C"):
        sub = combo_df[combo_df.strategy == s].sort_values("configured_gap_us")
        ax.plot(sub.configured_gap_us, sub.jitter_us, "-o", color=COLORS[s], label=s)
        for _, r in sub.iterrows():
            mark = "" if r.source.startswith("sweep") else " (n=5)"
            ax.annotate(f"{int(r.configured_gap_us)}{mark}", (r.configured_gap_us, r.jitter_us),
                        fontsize=6, xytext=(3,3), textcoords="offset points")
    ax.set_xlabel("configured external BG gap (us)"); ax.set_ylabel("0x100 jitter SD (us)")
    ax.set_title("Fig1: configured gap -> jitter (INCOMPLETE sweep: only 230,242 captured + 240 from confirmatory)")
    ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.3)
    ax.text(0, -0.15, "sweep captures truncated to ~30s -> only first point per group usable; 240 = confirmatory n=5 mean",
            transform=ax.transAxes, fontsize=7, color="#a00")
    _save(fig, "1_gap_vs_jitter")

    # Fig2: gap -> total occupancy
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for s in ("A","B","C"):
        sub = combo_df[combo_df.strategy == s].sort_values("configured_gap_us")
        ax.plot(sub.configured_gap_us, sub.occ_tot, "-o", color=COLORS[s], label=s)
    ax.set_xlabel("configured BG gap (us)"); ax.set_ylabel("reconstructed total occupancy (%)")
    ax.set_title("Fig2: configured gap -> reconstructed occupancy (NOT PCAN actual load)")
    ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.3)
    _save(fig, "2_gap_vs_occupancy")

    # Fig3: occupancy -> jitter
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    for s in ("A","B","C"):
        sub = combo_df[combo_df.strategy == s]
        ax.scatter(sub.occ_tot, sub.jitter_us, color=COLORS[s], s=60, label=s)
        for _, r in sub.iterrows():
            ax.annotate(f"{s}{int(r.configured_gap_us)}", (r.occ_tot, r.jitter_us), fontsize=6,
                        xytext=(3,3), textcoords="offset points")
    ax.set_xlabel("reconstructed total occupancy (%)"); ax.set_ylabel("jitter SD (us)")
    ax.set_title("Fig3: occupancy -> jitter")
    ax.legend(frameon=False); ax.grid(alpha=.3)
    _save(fig, "3_occupancy_vs_jitter")

    # Fig4: gap -> observed BG spacing
    fig, ax = plt.subplots(figsize=(8.5, 5))
    v = bg_df[bg_df.valid_20s]
    for s in ("A","B","C"):
        sub = v[v.strategy == s].sort_values("configured_gap_us")
        ax.plot(sub.configured_gap_us, sub.observed_bg_spacing_median_us, "-o", color=COLORS[s], label=f"{s} median")
        ax.scatter(sub.configured_gap_us, sub.observed_bg_spacing_mode_us, color=COLORS[s], marker="x", s=60)
    lim = ax.get_xlim(); ax.plot([228,244],[228,244], "k:", alpha=.4, label="observed=configured")
    ax.set_xlabel("configured BG gap (us)"); ax.set_ylabel("observed on-wire BG spacing (us)")
    ax.set_title("Fig4: configured gap vs observed BG spacing (o=median, x=mode)")
    ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.3)
    _save(fig, "4_gap_vs_observed_bg_spacing")

    # Fig5: gap -> BG fps
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for s in ("A","B","C"):
        sub = v[v.strategy == s].sort_values("configured_gap_us")
        ax.plot(sub.configured_gap_us, sub.bg_fps, "-o", color=COLORS[s], label=s)
    ax.set_xlabel("configured BG gap (us)"); ax.set_ylabel("observed on-wire BG fps")
    ax.set_title("Fig5: configured gap -> BG fps")
    ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.3)
    _save(fig, "5_gap_vs_bg_fps")


def _save(fig, stem):
    fig.tight_layout(); fig.savefig(FIG / f"{stem}.png", dpi=185, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _f(v, n=2):
    try: return f"{float(v):.{n}f}"
    except (TypeError, ValueError): return "n/a"


def write_report(seg_df, qc_df, met_df, bg_df, occ_df, combo_df, sl_df):
    L = ["# 3-node gap-sweep response analysis (marker-segmented)", ""]
    L += [
        "> ## ACQUISITION QC — CRITICAL: the sweep captures are INCOMPLETE",
        ">",
        "> Each of the 6 TRC is only ~28-31 s long and contains only **2 markers** (START idx0 + START idx1),",
        "> no END. The sweep firmware dwells 22 s/point (2 s settle + 20 s), so a full GROUP1 needs ~132 s and",
        "> GROUP2 ~110 s. At ~30 s only the **first gap of each group** has a full 20 s window; the 2nd point is",
        "> truncated (<1 s after settle) and gaps 232-240 / 244-250 and the END marker were never captured.",
        "> **Usable points = 6** (A/B/C x gap230 from _gap230_240, gap242 from _gap242_250). The intended",
        "> 230-250 gap-response curve CANNOT be built from this capture; re-capture at 132 s / 110 s is required.",
        "",
        "Markers (0x7F0) decoded and excluded from all statistics. `configured_gap_us` (from marker payload) and",
        "`observed_onwire_bg_spacing` (from TRC) are kept separate; configured gap is never reverse-inferred.",
        "",
        "## 1. Marker reconstruction (`marker_segments.csv`)",
        "",
        "| file | group | index | configured gap | type | t (ms) |",
        "|---|--:|--:|--:|---|--:|",
    ]
    for _, r in seg_df.iterrows():
        L.append(f"| {r.file} | {r.group} | {r.index} | {r.configured_gap_us} | {r.marker_type} | {r.marker_t_ms} |")

    L += ["", "## 2/3. Point QC (33 intended points; only 6 usable)", "",
          "| strategy | configured gap | usable window s | enough(>=20s) | QC |", "|---|--:|--:|:--:|---|"]
    for _, r in qc_df.iterrows():
        L.append(f"| {r.strategy} | {r.configured_gap_us} | {r.usable_window_s} | {r.enough_window} | {r.qc_status} |")
    L.append("\nAll intended gaps 232-240 and 244-250 are absent (never captured), not FAILed points.")

    L += ["", "## 4. 0x100 timing on the usable 20 s points", "",
          "| strategy | gap | jitter us | p99 us | >100us% | median interval | max interval ms |",
          "|---|--:|--:|--:|--:|--:|--:|"]
    for _, r in met_df[met_df.valid_20s].sort_values(["configured_gap_us","strategy"]).iterrows():
        L.append(f"| {r.strategy} | {int(r.configured_gap_us)} | {_f(r.jitter_us)} | {_f(r.p99_us,1)} | "
                 f"{_f(r.gt100_pct,2)} | {_f(r.median_interval_us,1)} | {_f(r.max_interval_us/1000,2)} |")

    L += ["", "## 5/6. Background structure + occupancy (usable points; configured vs observed)", "",
          "| strategy | conf gap | obs spacing median | obs mode | bg fps | occ_total% | occ_ctrl% | occ_bg% |",
          "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for _, r in bg_df[bg_df.valid_20s].sort_values(["configured_gap_us","strategy"]).iterrows():
        o = occ_df[(occ_df.strategy==r.strategy)&(occ_df.configured_gap_us==r.configured_gap_us)&(occ_df.valid_20s)].iloc[0]
        L.append(f"| {r.strategy} | {int(r.configured_gap_us)} | {_f(r.observed_bg_spacing_median_us,1)} | "
                 f"{_f(r.observed_bg_spacing_mode_us,0)} | {_f(r.bg_fps,0)} | {_f(o.reconstructed_total_occ_pct,2)} | "
                 f"{_f(o.reconstructed_control_occ_pct,2)} | {_f(o.reconstructed_bg_occ_pct,2)} |")

    L += ["", "## 7-9. Mini gap-response (usable 230, 242 + confirmatory 240 n=5)", "",
          "Only 3 configured gaps have data (230, 240, 242); 240 is the confirmatory n=5 mean. This is a sparse",
          "3-point set, NOT a resolved 230-250 curve.", "",
          "| strategy | gap230 jitter | gap240 jitter (n=5) | gap242 jitter |", "|---|--:|--:|--:|"]
    for s in ("A","B","C"):
        g = {int(r.configured_gap_us): r.jitter_us for _, r in combo_df[combo_df.strategy==s].iterrows()}
        L.append(f"| {s} | {_f(g.get(230))} | {_f(g.get(240))} | {_f(g.get(242))} |")

    if not sl_df.empty:
        L += ["", "## Similar-occupancy comparisons (<=2 pp apart)", "",
              "| pair | occ a | occ b | dpp | jitter a | jitter b | djit us |", "|---|--:|--:|--:|--:|--:|--:|"]
        for _, r in sl_df.iterrows():
            L.append(f"| {r.pair} | {r.occ_a} | {r.occ_b} | {r.occ_diff_pp} | {r.jitter_a} | {r.jitter_b} | {r.jitter_diff_us} |")

    L += ["", "## Claim boundary", "",
          "- Auto-sweep points are NOT independent reset replicates; treat as exploratory only. No inferential stats.",
          "- The 230-250 response curve is NOT resolved (only 3 gaps have data). No peak/valley/monotonicity claim",
          "  can be made across 230-250 from this capture.",
          "- reconstructed occupancy != PCAN actual load; jitter != latency; observed BG spacing is endogenous.",
          "", "## Figures", ""]
    for png in sorted(FIG.glob("*.png")):
        L.append(f"- `figures/{png.name}`")
    (HERE / "gap_sweep_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
