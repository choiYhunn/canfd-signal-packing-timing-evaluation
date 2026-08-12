#!/usr/bin/env python3
"""3-node FULL gap-sweep response analysis (marker-segmented, timestamp-only).

Fresh read of the 6 OVERWRITTEN full-sweep TRC in 3node_fixed_bg/. Does NOT reuse
any cached result from analysis_gap_response/. Reuses the verified n=10 module for
parsing + wire_breakdown airtime + EXPECTED layout. Raw TRC never modified; output
only under this folder. No firmware/build.

MARKER 0x7F0 payload: [0..1]=A5 5A, [2]=group, [3]=index, [4:6]=configured gap us
(LE), [6]=0x01 START / 0xEE END, [7]=active_count. Marker EXCLUDED from every stat.
configured_gap_us and observed_onwire_bg_spacing are kept separate; configured gap
is NEVER reverse-inferred from the TRC.
"""
from __future__ import annotations
import csv, os, sys
from collections import Counter, defaultdict
from itertools import combinations
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
FILES = [("A", "A_gap230_240.trc"), ("A", "A_gap242_250.trc"),
         ("B", "B_gap230_240.trc"), ("B", "B_gap242_250.trc"),
         ("C", "C_gap230_240.trc"), ("C", "C_gap242_250.trc")]
GAP_ORDER = [230, 232, 234, 236, 238, 240, 242, 244, 246, 248, 250]
_dev = csv.DictWriter(open(os.devnull, "w", newline=""),
    fieldnames=["source_file","strategy","load_mode","load_pct_label","run",
                "analysis_window","timestamp_us","gap_us","error_us","abs_error_us"])


def parse(path, strategy):
    res = canon.parse_trace(path, canon.FileKey(path.name, strategy, 2, "60", 1), _dev)
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
    air_ctrl = air_bg = 0.0
    esi = fd = brs = err = 0
    payload_ok = layout_ok = True
    monotonic = bool(np.all(np.diff(ts) >= 0)) if len(ts) > 1 else True
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
    ts100 = np.sort(ts[cid == 0x100])
    m, gaps, errors = canon.interval_metrics(ts100, dur, warmup_us=0)
    gap10 = int(np.sum(gaps > 10000)) if len(gaps) else 0
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
    struct_fail = (esi > 0 or err > 0 or not layout_ok or not payload_ok or not monotonic
                   or (obs_0x100_dlc != [exp[0x100][0]] if 0x100 in groups else True) or bg_n == 0)
    return dict(dur=dur, total_frames=len(win), frame_0x100=int(len(ts100)), bg_frames=bg_n, ctrl_frames=ctrl_n,
                occ_tot=occ_tot, occ_ctrl=occ_ctrl, occ_bg=occ_bg, monotonic=monotonic,
                total_fps=len(win)/dur if dur>0 else np.nan, ctrl_fps=ctrl_n/dur if dur>0 else np.nan,
                bg_fps=bg_n/dur if dur>0 else np.nan, bg_spacing_median=bg_med, bg_spacing_mode=bg_mode,
                bg_spacing_p10=bg_p10, bg_spacing_p90=bg_p90, bg_spacing_iqr=bg_iqr, bg_spacing_std=bg_std,
                bg_ids="|".join(f"0x{c:03X}" for c in bg_ids), n_bg_ids=len(bg_ids),
                mean_interval=m["mean_gap_us"], median_interval=m["median_gap_us"], jitter=m["jitter_std_us"],
                mae=m["abs_error_mean_us"], mae_median=m["abs_error_median_us"], p95=m["abs_error_p95_us"],
                p99=m["abs_error_p99_us"], gt100=m["abs_error_gt_100us_rate"]*100 if np.isfinite(m["abs_error_gt_100us_rate"]) else np.nan,
                max_interval=m["max_gap_us"], gap6=m["gap_gt_6000_count"], gap10=gap10, esi=esi, err=err,
                layout_ok=layout_ok, payload_ok=payload_ok, obs_0x100_dlc="|".join(map(str, obs_0x100_dlc)),
                struct_fail=struct_fail, acf1=acf1, domlag=domlag, domacf=domacf, acfcurve=acfcurve)


def main():
    seg_rows, qc_rows, met_rows, bg_rows, occ_rows = [], [], [], [], []
    acf_map = {}
    for strategy, fname in FILES:
        p = RAW / fname
        frames, header = parse(p, strategy)
        eof = max(f.timestamp_us for f in frames)
        mk = markers_of(frames)
        starts = [m for m in mk if m["mtype"] == "START"]
        ends = [m for m in mk if m["mtype"] == "END"]
        for m in mk:
            seg_rows.append(dict(file=fname, strategy=strategy, group=m["group"], index=m["index"],
                                 configured_gap_us=m["gap_us"], marker_type=m["mtype"],
                                 marker_t_ms=round(m["t_us"]/1000, 3), active_count=m["active"]))
        for j, s in enumerate(starts):
            nxt = starts[j+1]["t_us"] if j+1 < len(starts) else (ends[0]["t_us"] if ends else eof)
            avail = nxt - s["t_us"] - SETTLE_US
            t_lo = s["t_us"] + SETTLE_US; t_hi = t_lo + MEASURE_US
            enough = avail >= MEASURE_US
            if not enough: t_hi = min(t_hi, nxt)
            wm = win_metrics(frames, strategy, header, t_lo, t_hi)
            usable = (t_hi - t_lo) / 1e6
            status = ("FAIL" if (wm["struct_fail"] or not enough)
                      else ("PASS_WITH_TIMING_NOTE" if (wm["gap6"] > 0 or wm["gap10"] > 0) else "PASS"))
            qc_rows.append(dict(file=fname, strategy=strategy, configured_gap_us=s["gap_us"],
                                usable_window_s=round(usable, 3), enough_window=enough,
                                total_frames=wm["total_frames"], frame_0x100=wm["frame_0x100"],
                                bg_frames=wm["bg_frames"], monotonic=wm["monotonic"], esi=wm["esi"],
                                error_frames=wm["err"], layout_ok=wm["layout_ok"], payload_ok=wm["payload_ok"],
                                obs_0x100_dlc=wm["obs_0x100_dlc"], gap6=wm["gap6"], gap10=wm["gap10"],
                                qc_status=status))
            valid = enough and not wm["struct_fail"]
            met_rows.append(dict(strategy=strategy, configured_gap_us=s["gap_us"], valid=valid,
                                 n_intervals=wm["frame_0x100"]-1, mean_interval_us=wm["mean_interval"],
                                 median_interval_us=wm["median_interval"], jitter_us=wm["jitter"], mae_us=wm["mae"],
                                 mae_median_us=wm["mae_median"], p95_us=wm["p95"], p99_us=wm["p99"],
                                 gt100_pct=wm["gt100"], max_interval_us=wm["max_interval"], gap6=wm["gap6"], gap10=wm["gap10"],
                                 acf_lag1=wm["acf1"], dominant_lag=wm["domlag"], dominant_acf=wm["domacf"]))
            bg_rows.append(dict(strategy=strategy, configured_gap_us=s["gap_us"], valid=valid, bg_fps=wm["bg_fps"],
                                total_fps=wm["total_fps"], ctrl_fps=wm["ctrl_fps"],
                                observed_bg_spacing_median_us=wm["bg_spacing_median"], observed_bg_spacing_mode_us=wm["bg_spacing_mode"],
                                observed_bg_spacing_p10_us=wm["bg_spacing_p10"], observed_bg_spacing_p90_us=wm["bg_spacing_p90"],
                                observed_bg_spacing_iqr_us=wm["bg_spacing_iqr"], observed_bg_spacing_std_us=wm["bg_spacing_std"],
                                n_bg_ids=wm["n_bg_ids"], bg_ids=wm["bg_ids"]))
            occ_rows.append(dict(strategy=strategy, configured_gap_us=s["gap_us"], valid=valid,
                                 reconstructed_total_occ_pct=wm["occ_tot"], reconstructed_control_occ_pct=wm["occ_ctrl"],
                                 reconstructed_bg_occ_pct=wm["occ_bg"], total_fps=wm["total_fps"],
                                 control_fps=wm["ctrl_fps"], bg_fps=wm["bg_fps"], actual_pcan_mean_load="UNKNOWN"))
            acf_map[(strategy, s["gap_us"])] = np.array(wm["acfcurve"])

    seg_df = pd.DataFrame(seg_rows); qc_df = pd.DataFrame(qc_rows)
    met_df = pd.DataFrame(met_rows); bg_df = pd.DataFrame(bg_rows); occ_df = pd.DataFrame(occ_rows)

    def jit(s, g):
        r = met_df[(met_df.strategy == s) & (met_df.configured_gap_us == g)]
        return float(r.jitter_us.iloc[0]) if not r.empty else np.nan
    def occ(s, g):
        r = occ_df[(occ_df.strategy == s) & (occ_df.configured_gap_us == g)]
        return float(r.reconstructed_total_occ_pct.iloc[0]) if not r.empty else np.nan

    # same-gap strategy spread
    spread_rows = []
    for g in GAP_ORDER:
        js = {s: jit(s, g) for s in "ABC"}
        vals = [v for v in js.values() if np.isfinite(v)]
        spread_rows.append(dict(configured_gap_us=g, jitter_A=js["A"], jitter_B=js["B"], jitter_C=js["C"],
                                mean_jitter=np.mean(vals) if vals else np.nan,
                                strategy_spread_us=(max(vals)-min(vals)) if len(vals) >= 2 else np.nan))
    spread_df = pd.DataFrame(spread_rows)

    # adjacent-gap deltas (within strategy, consecutive configured gap incl 240->242 cross-group)
    adj_rows = []
    for s in "ABC":
        for g0, g1 in zip(GAP_ORDER[:-1], GAP_ORDER[1:]):
            j0, j1, o0, o1 = jit(s, g0), jit(s, g1), occ(s, g0), occ(s, g1)
            adj_rows.append(dict(strategy=s, gap_from=g0, gap_to=g1, d_gap_us=g1-g0,
                                 cross_group=(g0 == 240 and g1 == 242),
                                 d_occ_pp=round(o1-o0, 3), d_jitter_us=round(j1-j0, 3),
                                 jitter_from=round(j0,2), jitter_to=round(j1,2)))
    adj_df = pd.DataFrame(adj_rows)

    # similar-load comparisons across all valid points
    pts = [dict(strategy=s, gap=g, occ=occ(s, g), jit=jit(s, g)) for s in "ABC" for g in GAP_ORDER]
    sl_rows = []
    for a, b in combinations(pts, 2):
        docc = abs(a["occ"] - b["occ"])
        if docc <= 1.0:
            sl_rows.append(dict(a=f"{a['strategy']}g{a['gap']}", b=f"{b['strategy']}g{b['gap']}",
                                same_strategy=(a["strategy"] == b["strategy"]),
                                occ_a=round(a["occ"],2), occ_b=round(b["occ"],2), occ_diff_pp=round(docc,3),
                                jit_a=round(a["jit"],2), jit_b=round(b["jit"],2),
                                jitter_diff_us=round(abs(a["jit"]-b["jit"]),2)))
    sl_df = pd.DataFrame(sl_rows).sort_values("jitter_diff_us", ascending=False) if sl_rows else pd.DataFrame()

    # ACF only for peak/valley/transition extrema (spec: not all 33 points)
    ACF_GAPS = [234, 238, 240, 244, 250]   # peaks 234/244, valleys 238/250, transition 240
    acf_summary = met_df[met_df.configured_gap_us.isin(ACF_GAPS)][
        ["strategy", "configured_gap_us", "jitter_us", "acf_lag1", "dominant_lag", "dominant_acf"]].copy()

    def w(d, n): d.to_csv(HERE / n, index=False, encoding="utf-8-sig", lineterminator="\n")
    w(seg_df, "marker_segments.csv"); w(qc_df, "point_qc.csv"); w(met_df, "gap_response_metrics.csv")
    w(bg_df, "bg_timing_metrics.csv"); w(occ_df, "occupancy_metrics.csv"); w(spread_df, "same_gap_strategy_spread.csv")
    w(adj_df, "adjacent_gap_deltas.csv"); w(sl_df, "similar_load_comparisons.csv")
    w(acf_summary, "timing_acf_summary.csv")

    # Fig8: ACF at a valley (238), peak (244), valley (250) for strategy A
    fig, ax = plt.subplots(figsize=(9, 5))
    for g, ls in ((238, "-"), (244, "-"), (250, "--")):
        ac = acf_map.get(("A", g))
        if ac is not None and len(ac):
            ax.plot(np.arange(1, len(ac)+1), ac, ls, lw=1.3,
                    label=f"A gap{g} (jitter {met_df[(met_df.strategy=='A')&(met_df.configured_gap_us==g)].jitter_us.iloc[0]:.0f}us)")
    ax.axhline(0, color="k", lw=.6); ax.set_xlim(0, 120)
    ax.set_xlabel("lag (0x100 cycles)"); ax.set_ylabel("inter-arrival error ACF")
    ax.set_title("Fig8: ACF at valley(238)/peak(244)/valley(250) - strategy A")
    ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.3)
    _save(fig, "8_acf_extrema_A")

    make_figures(met_df, occ_df, bg_df, spread_df, adj_df, acf_map)
    write_report(seg_df, qc_df, met_df, bg_df, occ_df, spread_df, adj_df, sl_df, acf_map)
    print("valid points:", int(met_df.valid.sum()), "/", len(met_df))
    print(spread_df[["configured_gap_us","jitter_A","jitter_B","jitter_C","strategy_spread_us"]].to_string(index=False))


def make_figures(met_df, occ_df, bg_df, spread_df, adj_df, acf_map):
    def series(df, s, col, key="jitter_us"):
        sub = df[df.strategy == s].sort_values("configured_gap_us")
        return sub.configured_gap_us.to_numpy(), sub[col].to_numpy()

    # 1 gap -> jitter
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for s in "ABC":
        x, y = series(met_df, s, "jitter_us"); ax.plot(x, y, "-o", color=COLORS[s], label=s)
    ax.set_xlabel("configured external BG gap (us)"); ax.set_ylabel("0x100 jitter SD (us)")
    ax.set_title("Fig1: configured gap -> jitter (A/B/C, full sweep 230-250)")
    ax.set_xticks(GAP_ORDER); ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.3)
    ax.text(0,-0.14,"n=1 auto-sweep point/gap (exploratory); jitter != latency; configured gap != wire period",
            transform=ax.transAxes, fontsize=7, color="#666")
    _save(fig, "1_gap_vs_jitter_ABC")

    # 2 gap -> occupancy
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for s in "ABC":
        x, y = series(occ_df, s, "reconstructed_total_occ_pct"); ax.plot(x, y, "-o", color=COLORS[s], label=s)
    ax.set_xlabel("configured BG gap (us)"); ax.set_ylabel("reconstructed total occupancy (%)")
    ax.set_title("Fig2: configured gap -> reconstructed occupancy (NOT PCAN actual load)")
    ax.set_xticks(GAP_ORDER); ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.3)
    _save(fig, "2_gap_vs_occupancy_ABC")

    # 3 occupancy -> jitter
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    for s in "ABC":
        sub_o = occ_df[occ_df.strategy == s].sort_values("configured_gap_us")
        sub_j = met_df[met_df.strategy == s].sort_values("configured_gap_us")
        ax.scatter(sub_o.reconstructed_total_occ_pct, sub_j.jitter_us, color=COLORS[s], s=55, label=s)
        for g, o, jj in zip(sub_o.configured_gap_us, sub_o.reconstructed_total_occ_pct, sub_j.jitter_us):
            ax.annotate(str(int(g)), (o, jj), fontsize=6, xytext=(3,2), textcoords="offset points")
    ax.set_xlabel("reconstructed total occupancy (%)"); ax.set_ylabel("jitter SD (us)")
    ax.set_title("Fig3: occupancy -> jitter (label = configured gap us)")
    ax.legend(frameon=False); ax.grid(alpha=.3)
    _save(fig, "3_occupancy_vs_jitter")

    # 4 gap -> observed BG spacing
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for s in "ABC":
        x, y = series(bg_df, s, "observed_bg_spacing_median_us")
        ax.plot(x, y, "-o", color=COLORS[s], label=f"{s} median")
        x2, y2 = series(bg_df, s, "observed_bg_spacing_mode_us")
        ax.scatter(x2, y2, color=COLORS[s], marker="x", s=55)
    ax.plot(GAP_ORDER, GAP_ORDER, "k:", alpha=.4, label="observed=configured")
    ax.set_xlabel("configured BG gap (us)"); ax.set_ylabel("observed on-wire BG spacing (us)")
    ax.set_title("Fig4: configured gap vs observed BG spacing (o=median, x=mode)")
    ax.set_xticks(GAP_ORDER); ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.3)
    _save(fig, "4_gap_vs_observed_bg_spacing")

    # 5 gap -> BG fps
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for s in "ABC":
        x, y = series(bg_df, s, "bg_fps"); ax.plot(x, y, "-o", color=COLORS[s], label=s)
    ax.set_xlabel("configured BG gap (us)"); ax.set_ylabel("observed on-wire BG fps")
    ax.set_title("Fig5: configured gap -> BG fps"); ax.set_xticks(GAP_ORDER)
    ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.3)
    _save(fig, "5_gap_vs_bg_fps")

    # 6 strategy spread by gap
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([str(g) for g in spread_df.configured_gap_us], spread_df.strategy_spread_us, color="#666")
    ax.set_xlabel("configured BG gap (us)"); ax.set_ylabel("A/B/C jitter spread max-min (us)")
    ax.set_title("Fig6: same-gap strategy jitter spread (small = strategy-independent)")
    ax.grid(axis="y", alpha=.3)
    _save(fig, "6_strategy_spread_by_gap")

    # 7 delta occupancy vs delta jitter (adjacent gaps)
    fig, ax = plt.subplots(figsize=(7.8, 5.4))
    for s in "ABC":
        sub = adj_df[adj_df.strategy == s]
        ax.scatter(sub.d_occ_pp, sub.d_jitter_us, color=COLORS[s], s=55, label=s)
        for _, r in sub.iterrows():
            ax.annotate(f"{r.gap_from}->{r.gap_to}", (r.d_occ_pp, r.d_jitter_us), fontsize=5.5,
                        xytext=(3,2), textcoords="offset points")
    ax.axhline(0, color="k", lw=.6); ax.axvline(0, color="k", lw=.6)
    ax.set_xlabel("delta reconstructed occupancy (pp)"); ax.set_ylabel("delta jitter (us)")
    ax.set_title("Fig7: adjacent-gap delta occupancy vs delta jitter")
    ax.legend(frameon=False); ax.grid(alpha=.3)
    _save(fig, "7_delta_occupancy_vs_delta_jitter")


def _save(fig, stem):
    fig.tight_layout(); fig.savefig(FIG / f"{stem}.png", dpi=185, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _f(v, n=2):
    try: return f"{float(v):.{n}f}"
    except (TypeError, ValueError): return "n/a"


def write_report(seg_df, qc_df, met_df, bg_df, occ_df, spread_df, adj_df, sl_df, acf_map):
    npass = int((qc_df.qc_status != "FAIL").sum())
    L = ["# 3-node FULL gap-sweep response analysis (230-250 us)", ""]
    L += [
        "Fresh read of the 6 overwritten full-sweep TRC in `3node_fixed_bg/`. No cached result reused.",
        "Markers (0x7F0) decoded and excluded from all statistics. `configured_gap_us` (marker payload) and",
        "`observed_onwire_bg_spacing` (TRC) are separate; configured gap never reverse-inferred.",
        "Each point = one START marker; first 2 s settle dropped, next 20 s analysed. Auto-sweep points are",
        "exploratory (NOT independent reset replicates); no inferential stats.",
        "",
        f"## Acquisition: all 6 files COMPLETE. QC {npass}/{len(qc_df)} not-FAIL.",
        "",
        "| file | markers | START | END | decoded gaps | dur s | frames |",
        "|---|--:|--:|--:|---|--:|--:|",
    ]
    for (strategy, fname) in FILES:
        sd = seg_df[seg_df.file == fname]
        starts = sd[sd.marker_type == "START"]; ends = sd[sd.marker_type == "END"]
        gaps = "/".join(str(int(g)) for g in starts.sort_values("index").configured_gap_us)
        dur = sd.marker_t_ms.max()/1000
        tot = int(qc_df[qc_df.file == fname].total_frames.sum())
        L.append(f"| {fname} | {len(sd)} | {len(starts)} | {len(ends)} | {gaps} | ~{dur:.0f}+ | ~{tot} |")

    L += ["", "## Q1. gap -> jitter (us), all 11 gaps", "",
          "| gap | A | B | C | mean | spread(max-min) |", "|--:|--:|--:|--:|--:|--:|"]
    for _, r in spread_df.iterrows():
        L.append(f"| {int(r.configured_gap_us)} | {_f(r.jitter_A)} | {_f(r.jitter_B)} | {_f(r.jitter_C)} | "
                 f"{_f(r.mean_jitter)} | {_f(r.strategy_spread_us)} |")

    L += ["", "## occupancy + BG (configured vs observed), per gap (mean of A/B/C)", "",
          "| gap | obs spacing median | obs mode | bg fps | occ_total% | occ_ctrl% (A/B/C) | occ_bg% |",
          "|--:|--:|--:|--:|--:|---|--:|"]
    for g in GAP_ORDER:
        b = bg_df[bg_df.configured_gap_us == g]; o = occ_df[occ_df.configured_gap_us == g]
        cc = "/".join(_f(occ_df[(occ_df.strategy==s)&(occ_df.configured_gap_us==g)].reconstructed_control_occ_pct.iloc[0],2) for s in "ABC")
        L.append(f"| {g} | {_f(b.observed_bg_spacing_median_us.mean(),1)} | {_f(b.observed_bg_spacing_mode_us.median(),0)} | "
                 f"{_f(b.bg_fps.mean(),0)} | {_f(o.reconstructed_total_occ_pct.mean(),2)} | {cc} | {_f(o.reconstructed_bg_occ_pct.mean(),2)} |")

    # adjacent deltas: strongest small-occ-change / large-jitter-change
    adj_df2 = adj_df.assign(ratio=adj_df.d_jitter_us.abs() / adj_df.d_occ_pp.abs().replace(0, np.nan))
    L += ["", "## Q9. adjacent-gap deltas (largest jitter change per small occupancy change)", "",
          "| strategy | gap | d_gap us | d_occ pp | d_jitter us |", "|---|---|--:|--:|--:|"]
    for _, r in adj_df.reindex(adj_df.d_jitter_us.abs().sort_values(ascending=False).index).head(8).iterrows():
        L.append(f"| {r.strategy} | {r.gap_from}->{r.gap_to} | {r.d_gap_us} | {_f(r.d_occ_pp,2)} | {_f(r.d_jitter_us,2)} |")

    if not sl_df.empty:
        L += ["", "## Q8. similar-occupancy, different-jitter (|d_occ|<=1.0 pp), strongest first", "",
              "| a | b | same_strat | occ a | occ b | d_occ pp | jit a | jit b | d_jit us |", "|---|---|:--:|--:|--:|--:|--:|--:|--:|"]
        for _, r in sl_df.head(10).iterrows():
            L.append(f"| {r.a} | {r.b} | {r.same_strategy} | {r.occ_a} | {r.occ_b} | {r.occ_diff_pp} | {r.jit_a} | {r.jit_b} | {r.jitter_diff_us} |")

    L += ["", "## Claim boundary", "",
          "- auto-sweep = exploratory (n=1/gap, phase may carry across points); confirm with independent resets.",
          "- reconstructed occupancy != PCAN actual load; jitter != latency; observed BG spacing is endogenous;",
          "  configured gap != exact wire period. No arbitration/phase-resonance causal claim.",
          "", "## Figures", ""]
    for png in sorted(FIG.glob("*.png")):
        L.append(f"- `figures/{png.name}`")
    (HERE / "gap_sweep_full_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
