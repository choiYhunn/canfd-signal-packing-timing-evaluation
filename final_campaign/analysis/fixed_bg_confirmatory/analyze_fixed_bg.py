#!/usr/bin/env python3
"""Fixed external-background CONFIRMATORY analysis (A/B/C x L/M/H x run1-5 = 45 TRC).

Purpose: remove the earlier confound (strategy-specific dummy-gap tuning to match total
bus load) by using the SAME configured external-background gap for all strategies at each
BG level, then ask whether packing strategy A/B/C still changes 0x100 timing.

Configured external BG gap (fixed by experiment record, NOT reverse-inferred from TRC):
    BG-L = 630 us, BG-M = 240 us, BG-H = 170 us.
Pre-check background-only PCAN load (calibration reference ONLY, not the A/B/C total load):
    630->~9%, 240->~52%, 170->~75%.

Reuses the verified n=10 module for parsing + wire_breakdown airtime + EXPECTED layout.
No firmware / build / Generate. Original TRC never modified. Writes only in THIS folder;
no existing analysis output is overwritten.
"""
from __future__ import annotations
import csv, os, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RAW = REPO / "3node_fixed_bg"
OLD_SUMMARY = REPO / "3node" / "analysis_n5" / "condition_summary_n5.csv"
CANON = REPO / "trace_fixed2" / "analysis_n10"
sys.path.insert(0, str(CANON))
import analyze_fixed2_64b_n10 as canon
FIG = HERE / "figures"; FIG.mkdir(parents=True, exist_ok=True)

PERIOD = 5000.0
BG_LABEL = {1: "L", 2: "M", 3: "H", 0: "OFF"}
CONFIG_GAP = {1: 630, 2: 240, 3: 170, 0: None}   # configured external BG gap (us), by record
BG_LOAD_REF = {1: 9, 2: 52, 3: 75}               # background-only PCAN load reference (%)
STRAT = ("A", "B", "C")
LEVELS = ("L", "M", "H")
COLORS = {"A": "#0072B2", "B": "#D55E00", "C": "#009E73"}
LVL_X = {"L": 0, "M": 1, "H": 2}
_devnull = csv.DictWriter(open(os.devnull, "w", newline=""),
    fieldnames=["source_file", "strategy", "load_mode", "load_pct_label", "run",
                "analysis_window", "timestamp_us", "gap_us", "error_us", "abs_error_us"])


def parse_name(name):
    stem = name[:-4]
    s = stem[0].upper()
    if s not in STRAT:
        return None
    rest = stem[1:]
    if rest == "0":
        return dict(strategy=s, mode=0, run=0, kind="baseline")
    if "_" in rest:
        d, r = rest.split("_")
        if d in ("1", "2", "3") and r.isdigit():
            return dict(strategy=s, mode=int(d), run=int(r), kind="main")
    return None


def acf_dominant(err):
    e = err[np.isfinite(err)]
    if len(e) < 50:
        return np.nan, -1, np.nan, []
    e0 = e - e.mean(); var = float(np.dot(e0, e0))
    if var <= 0:
        return np.nan, -1, np.nan, []
    maxlag = min(400, len(e0) - 2)
    ac = np.array([np.dot(e0[:-L], e0[L:]) / var for L in range(1, maxlag + 1)])
    seg = ac[1:]
    di = int(np.argmax(seg)) + 2 if len(seg) else -1
    return float(ac[0]), di, (float(ac[di - 1]) if di > 0 else np.nan), ac.tolist()


def process(path):
    meta = parse_name(path.name)
    s, mode = meta["strategy"], meta["mode"]
    key = canon.FileKey(path.name, s, mode, BG_LABEL[mode], meta["run"])
    res = canon.parse_trace(path, key, _devnull)
    frames = res["frames"]; header = res["header"]; perr = res["parse_errors"]
    nb = float(header["nominal_bit_rate_bps"]); db = float(header["data_bit_rate_bps"])
    if not (np.isfinite(nb) and np.isfinite(db)):
        nb, db = canon.LOOKUP_NOMINAL_BPS, canon.LOOKUP_DATA_BPS

    ts = np.array([f.timestamp_us for f in frames], dtype=np.float64)
    cid = np.array([f.can_id for f in frames], dtype=np.int64)
    dur = (ts[-1] - ts[0]) / 1e6 if len(ts) > 1 else 0.0
    backwards = int(np.sum(np.diff(ts) < 0)) if len(ts) > 1 else 0
    last_num = int(res.get("last_message_number", len(frames)) or len(frames))

    groups = defaultdict(list)
    for f in frames:
        groups[f.can_id].append(f)
    exp = canon.EXPECTED[s]
    bg_ids = sorted(c for c in groups if 0x300 <= c <= 0x30F)
    ctrl_ids = sorted(c for c in groups if c in exp)
    unexpected = sorted(c for c in groups if c not in exp and not (0x300 <= c <= 0x30F))
    missing = sorted(set(exp) - set(groups))

    # airtime split (reused wire_breakdown)
    air_ctrl = air_bg = 0.0
    esi_total = fd_total = brs_total = 0
    payload_ok = True; layout_ok = True
    for c, grp in groups.items():
        pc = Counter(f.payload for f in grp)
        esi_total += sum(f.esi for f in grp); fd_total += sum(f.is_fd for f in grp); brs_total += sum(f.brs for f in grp)
        a = 0.0
        for payload, cnt in pc.items():
            smp = next(f for f in grp if f.payload == payload)
            a += float(canon.wire_breakdown(c, payload, smp.esi, nb, db, legacy=False)["estimated_airtime_us"]) * cnt
        if 0x300 <= c <= 0x30F:
            air_bg += a
        elif c in exp:
            air_ctrl += a
            explen = exp[c][0]
            if sorted({f.length for f in grp}) != [explen]:
                layout_ok = False
            if c in canon.EXPECTED_PAYLOAD[s] and not (len(pc) == 1 and next(iter(pc)) == canon.EXPECTED_PAYLOAD[s][c]):
                payload_ok = False
    occ_total = (air_ctrl + air_bg) / (dur * 1e6) * 100 if dur > 0 else np.nan
    occ_ctrl = air_ctrl / (dur * 1e6) * 100 if dur > 0 else np.nan
    occ_bg = air_bg / (dur * 1e6) * 100 if dur > 0 else np.nan

    # 0x100 timing (reused interval_metrics)
    ts100 = ts[cid == 0x100]
    m, gaps, errors = canon.interval_metrics(ts100, dur, warmup_us=0)
    gap_gt_10ms = int(np.sum(gaps > 10000)) if len(gaps) else 0

    # robust phase grid + ACF
    if len(ts100) > 2:
        rel = ts100 - ts100[0]; gm = np.round(rel / PERIOD)
        t0 = float(np.median(ts100 - gm * PERIOD))
        phase_res = ts100 - (t0 + gm * PERIOD)
        phase_res_std = float(np.std(phase_res, ddof=1))
    else:
        phase_res_std = np.nan
    acf1, domlag, domacf, acfcurve = acf_dominant(errors)

    # BG on-wire stats
    bg_ts = np.sort(ts[(cid >= 0x300) & (cid <= 0x30F)])
    if len(bg_ts) > 2:
        d = np.diff(bg_ts); d = d[d > 0]
        vals, cnts = np.unique(d, return_counts=True)
        bg_med = float(np.median(d)); bg_mode = int(vals[np.argmax(cnts)])
        bg_p10, bg_p90 = float(np.percentile(d, 10)), float(np.percentile(d, 90))
        bg_iqr = float(np.percentile(d, 75) - np.percentile(d, 25))
    else:
        bg_med = bg_mode = bg_p10 = bg_p90 = bg_iqr = np.nan
    bg_frames = len(bg_ts); bg_fps = bg_frames / dur if dur > 0 else np.nan
    ctrl_frames = sum(len(groups[c]) for c in ctrl_ids)
    # BG DLC/payload consistency
    bg_dlc = sorted({f.length for c in bg_ids for f in groups[c]})
    bg_payload_ident = all(len(Counter(f.payload for f in groups[c])) == 1 for c in bg_ids) if bg_ids else None

    error_frames = sum(1 for f in frames if "ERR" in f.type_token.upper())

    # QC flags
    struct_fail = (len(perr) > 0 or len(frames) == 0 or backwards > 0
                   or fd_total != len(frames) or brs_total != len(frames) or esi_total > 0
                   or error_frames > 0 or not layout_ok or not payload_ok
                   or len(missing) > 0 or len(unexpected) > 0
                   or (sorted({f.length for f in groups.get(0x100, [])}) != [exp[0x100][0]] if 0x100 in groups else True))
    if mode == 0:
        struct_fail = struct_fail or (bg_frames > 0)   # baseline must have no BG
    else:
        struct_fail = struct_fail or (bg_frames == 0)   # main must have BG
    timing_note = (m["gap_gt_6000_count"] > 0) or (gap_gt_10ms > 0) or (m["near_10ms_frame_loss_candidate_count"] > 0)
    qc = "FAIL" if struct_fail else ("PASS_WITH_TIMING_NOTE" if timing_note else "PASS")

    row = dict(
        file=path.name, strategy=s, bg_level=BG_LABEL[mode], run=meta["run"], kind=meta["kind"],
        configured_external_bg_gap_us=(CONFIG_GAP[mode] if mode else "OFF"),
        bg_load_reference_pct=(BG_LOAD_REF.get(mode, "")),
        duration_s=dur, total_frames=len(frames), last_message_number=last_num,
        timestamp_backwards=backwards, error_frame_count=error_frames, esi_count=esi_total,
        observed_ids="|".join(f"0x{c:03X}" for c in sorted(groups)),
        missing_ids="|".join(f"0x{c:03X}" for c in missing),
        unexpected_ids="|".join(f"0x{c:03X}" for c in unexpected),
        ctrl_ids="|".join(f"0x{c:03X}" for c in ctrl_ids), bg_id_count=len(bg_ids),
        frame_0x100=int(len(ts100)), bg_frames=bg_frames, ctrl_frames=ctrl_frames,
        obs_0x100_dlc="|".join(map(str, sorted({f.length for f in groups.get(0x100, [])}))),
        expected_0x100_dlc=exp[0x100][0], layout_ok=layout_ok, payload_byte_identical=payload_ok,
        bg_dlc="|".join(map(str, bg_dlc)), bg_payload_byte_identical=bg_payload_ident,
        hit_ceiling=(len(frames) >= 300000 or last_num >= 300000),
        approx_30s=(25 <= dur <= 35),
        qc_status=qc,
        # timing
        n_intervals=m["number_intervals"], mean_interval_us=m["mean_gap_us"], median_interval_us=m["median_gap_us"],
        jitter_us=m["jitter_std_us"], abs_err_mean_us=m["abs_error_mean_us"], abs_err_median_us=m["abs_error_median_us"],
        abs_err_p95_us=m["abs_error_p95_us"], abs_err_p99_us=m["abs_error_p99_us"], abs_err_max_us=m["abs_error_max_us"],
        gt100_rate_pct=(m["abs_error_gt_100us_rate"] * 100 if np.isfinite(m["abs_error_gt_100us_rate"]) else np.nan),
        max_interval_us=m["max_gap_us"], gap_gt_6ms=m["gap_gt_6000_count"], gap_gt_10ms=gap_gt_10ms,
        near_10ms=m["near_10ms_frame_loss_candidate_count"], phase_res_std_us=phase_res_std,
        acf_lag1=acf1, dominant_lag=domlag, dominant_acf=domacf,
        # occupancy / bandwidth
        occ_total_pct=occ_total, occ_ctrl_pct=occ_ctrl, occ_bg_pct=occ_bg,
        total_fps=(len(frames) / dur if dur > 0 else np.nan), ctrl_fps=(ctrl_frames / dur if dur > 0 else np.nan),
        bg_fps=bg_fps,
        # observed BG on-wire spacing (DISTINCT from configured gap)
        obs_bg_spacing_median_us=bg_med, obs_bg_spacing_mode_us=bg_mode,
        obs_bg_spacing_p10_us=bg_p10, obs_bg_spacing_p90_us=bg_p90, obs_bg_spacing_iqr_us=bg_iqr,
        actual_pcan_mean_load="UNKNOWN",   # no PCAN load manifest found this campaign
    )
    return row, acfcurve, (bg_ids, {c: len(groups[c]) / dur if dur > 0 else np.nan for c in bg_ids})


def agg(series):
    v = pd.to_numeric(series, errors="coerce").to_numpy(float); v = v[np.isfinite(v)]
    if len(v) == 0:
        return dict(n=0, mean=np.nan, sd=np.nan, median=np.nan, vmin=np.nan, vmax=np.nan)
    return dict(n=len(v), mean=float(v.mean()), sd=(float(v.std(ddof=1)) if len(v) > 1 else np.nan),
                median=float(np.median(v)), vmin=float(v.min()), vmax=float(v.max()))


def main():
    files = sorted(RAW.glob("*.trc"), key=lambda p: p.name.lower())
    rows, acf_map, bg_perid = [], {}, {}
    for p in files:
        if parse_name(p.name) is None:
            rows.append(dict(file=p.name, qc_status="FAIL", unexpected_ids="UNPARSEABLE_NAME")); continue
        r, acf, perid = process(p)
        rows.append(r); acf_map[r["file"]] = np.array(acf); bg_perid[r["file"]] = perid
    df = pd.DataFrame(rows)
    main_df = df[df.kind == "main"].copy()
    base_df = df[df.kind == "baseline"].copy()

    def wcsv(d, name): d.to_csv(HERE / name, index=False, encoding="utf-8-sig", lineterminator="\n")

    # mapping table
    print("=== MAPPING (filename -> strategy / BG level / configured gap; observed-mode check) ===")
    for _, r in main_df.sort_values(["strategy", "bg_level", "run"]).iterrows():
        pass
    map_tbl = (main_df.groupby(["strategy", "bg_level"])
               .agg(runs=("run", lambda x: "|".join(map(str, sorted(x)))),
                    configured_gap=("configured_external_bg_gap_us", "first"),
                    obs_bg_mode=("obs_bg_spacing_mode_us", "median")).reset_index())
    print(map_tbl.to_string(index=False))
    wcsv(df, "file_qc.csv")
    wcsv(main_df[["file", "strategy", "bg_level", "run", "configured_external_bg_gap_us", "n_intervals",
                  "mean_interval_us", "median_interval_us", "jitter_us", "abs_err_mean_us", "abs_err_median_us",
                  "abs_err_p95_us", "abs_err_p99_us", "gt100_rate_pct", "max_interval_us", "gap_gt_6ms",
                  "gap_gt_10ms", "occ_total_pct", "occ_ctrl_pct", "occ_bg_pct", "bg_fps", "phase_res_std_us",
                  "acf_lag1", "dominant_lag", "dominant_acf", "qc_status"]], "run_metrics.csv")

    # condition summary n=5
    cs = []
    for s in STRAT:
        for lv in LEVELS:
            sub = main_df[(main_df.strategy == s) & (main_df.bg_level == lv)]
            if sub.empty: continue
            row = dict(condition=f"{s}-{lv}", strategy=s, bg_level=lv,
                       configured_gap_us=CONFIG_GAP[{"L": 1, "M": 2, "H": 3}[lv]], run_count=len(sub))
            for col, tag in [("jitter_us", "jitter"), ("abs_err_p99_us", "p99"), ("gt100_rate_pct", "gt100"),
                             ("occ_total_pct", "occ_total"), ("occ_ctrl_pct", "occ_ctrl"), ("occ_bg_pct", "occ_bg"),
                             ("bg_fps", "bgfps"), ("duration_s", "dur")]:
                a = agg(sub[col])
                row[f"{tag}_mean"], row[f"{tag}_sd"] = a["mean"], a["sd"]
                row[f"{tag}_median"], row[f"{tag}_min"], row[f"{tag}_max"] = a["median"], a["vmin"], a["vmax"]
            cs.append(row)
    cs_df = pd.DataFrame(cs); wcsv(cs_df, "condition_summary.csv")

    # background statistics (per condition)
    bgs = []
    for s in STRAT:
        for lv in LEVELS:
            sub = main_df[(main_df.strategy == s) & (main_df.bg_level == lv)]
            if sub.empty: continue
            bgs.append(dict(condition=f"{s}-{lv}", strategy=s, bg_level=lv,
                            configured_external_bg_gap_us=CONFIG_GAP[{"L": 1, "M": 2, "H": 3}[lv]],
                            obs_bg_spacing_median_us=agg(sub.obs_bg_spacing_median_us)["mean"],
                            obs_bg_spacing_mode_us=agg(sub.obs_bg_spacing_mode_us)["median"],
                            obs_bg_spacing_p10_us=agg(sub.obs_bg_spacing_p10_us)["mean"],
                            obs_bg_spacing_p90_us=agg(sub.obs_bg_spacing_p90_us)["mean"],
                            obs_bg_spacing_iqr_us=agg(sub.obs_bg_spacing_iqr_us)["mean"],
                            bg_fps_mean=agg(sub.bg_fps)["mean"], bg_fps_sd=agg(sub.bg_fps)["sd"],
                            bg_frames_mean=agg(sub.bg_frames)["mean"],
                            occ_bg_pct_mean=agg(sub.occ_bg_pct)["mean"]))
    bgs_df = pd.DataFrame(bgs); wcsv(bgs_df, "background_statistics.csv")

    # occupancy summary
    occ_rows = []
    for _, r in cs_df.iterrows():
        occ_rows.append(dict(condition=r.condition, strategy=r.strategy, bg_level=r.bg_level,
                             configured_gap_us=r.configured_gap_us,
                             occ_total_mean=r.occ_total_mean, occ_total_sd=r.occ_total_sd,
                             occ_ctrl_mean=r.occ_ctrl_mean, occ_bg_mean=r.occ_bg_mean,
                             jitter_mean=r.jitter_mean, jitter_sd=r.jitter_sd,
                             actual_pcan_mean_load="UNKNOWN"))
    occ_df = pd.DataFrame(occ_rows); wcsv(occ_df, "occupancy_summary.csv")

    # ACF summary
    acf_rows = []
    for _, r in main_df.iterrows():
        acf_rows.append(dict(condition=f"{r.strategy}-{r.bg_level}", strategy=r.strategy, bg_level=r.bg_level,
                             run=r.run, jitter_us=r.jitter_us, acf_lag1=r.acf_lag1,
                             dominant_lag=r.dominant_lag, dominant_acf=r.dominant_acf,
                             phase_res_std_us=r.phase_res_std_us,
                             obs_bg_spacing_median_us=r.obs_bg_spacing_median_us,
                             obs_bg_spacing_mode_us=r.obs_bg_spacing_mode_us))
    acf_df = pd.DataFrame(acf_rows); wcsv(acf_df, "timing_acf_summary.csv")

    # old vs new
    ov = build_old_vs_new(cs_df); wcsv(ov, "old_vs_new_summary.csv")

    make_figures(main_df, cs_df, acf_map, ov)
    write_report(df, main_df, base_df, cs_df, bgs_df, ov, map_tbl)
    print(f"\nQC:", dict(main_df.qc_status.value_counts()), " baseline:", dict(base_df.qc_status.value_counts()))
    print(f"processed {len(main_df)} main + {len(base_df)} baseline -> {HERE}")


def build_old_vs_new(cs_df):
    lvl_to_tgt = {"L": "30", "M": "60", "H": "80"}
    rows = []
    if OLD_SUMMARY.exists():
        old = pd.read_csv(OLD_SUMMARY)
        for s in STRAT:
            for lv in LEVELS:
                new = cs_df[cs_df.condition == f"{s}-{lv}"]
                oc = old[old.condition == f"{s}{lvl_to_tgt[lv]}"]
                if new.empty or oc.empty: continue
                rows.append(dict(strategy=s, bg_level=lv, configured_gap_new=CONFIG_GAP[{"L":1,"M":2,"H":3}[lv]],
                    old_target=f"{s}{lvl_to_tgt[lv]}",
                    old_gap_note="strategy-specific tuned gap (confounded)",
                    new_jitter_mean=float(new.jitter_mean.iloc[0]), new_jitter_sd=float(new.jitter_sd.iloc[0]),
                    old_jitter_mean=float(oc.jitter_mean.iloc[0]), old_jitter_sd=float(oc.jitter_sd.iloc[0]),
                    new_occ_total_mean=float(new.occ_total_mean.iloc[0]), old_occ_mean=float(oc.occ_mean.iloc[0]),
                    new_gt100_mean=float(new.gt100_mean.iloc[0]), old_gt100_mean=float(oc.gt100_rate_mean.iloc[0])))
    return pd.DataFrame(rows)


def _sc(ax, xs, sub, col, color):
    x = xs + np.linspace(-0.13, 0.13, len(sub))
    ax.scatter(x, sub[col], color=color, s=48, zorder=3, edgecolor="white", linewidth=.5)
    a = agg(sub[col]); ax.hlines(a["mean"], xs - 0.16, xs + 0.16, color=color, lw=2.2, zorder=4)


def make_figures(main_df, cs_df, acf_map, ov):
    # 1. jitter by fixed BG x strategy (individual run points)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for si, s in enumerate(STRAT):
        for lv in LEVELS:
            sub = main_df[(main_df.strategy == s) & (main_df.bg_level == lv)]
            if sub.empty: continue
            base = LVL_X[lv] * 1.0 + (si - 1) * 0.24
            _sc(ax, base, sub, "jitter_us", COLORS[s])
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["BG-L (630us, ~9%)", "BG-M (240us, ~52%)", "BG-H (170us, ~75%)"])
    ax.set_ylabel("0x100 inter-arrival jitter SD (us)")
    ax.set_title("Fig1: jitter by fixed-BG level x strategy (n=5 runs each; bar=mean)")
    for s in STRAT:
        ax.scatter([], [], color=COLORS[s], label=s)
    ax.legend(title="Strategy", frameon=False); ax.grid(axis="y", alpha=.3)
    ax.text(0, -0.13, "SAME configured external BG gap for A/B/C at each level. jitter != latency; "
            "occupancy proxy != PCAN actual load", transform=ax.transAxes, fontsize=7, color="#666")
    _save(fig, "jitter_by_fixed_bg_strategy")

    # 2. occupancy by fixed BG x strategy
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for si, s in enumerate(STRAT):
        for lv in LEVELS:
            sub = main_df[(main_df.strategy == s) & (main_df.bg_level == lv)]
            if sub.empty: continue
            _sc(ax, LVL_X[lv] + (si - 1) * 0.24, sub, "occ_total_pct", COLORS[s])
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["BG-L", "BG-M", "BG-H"])
    ax.set_ylabel("reconstructed TOTAL occupancy (%)")
    ax.set_title("Fig2: reconstructed occupancy by fixed-BG level x strategy (NOT PCAN actual load)")
    for s in STRAT: ax.scatter([], [], color=COLORS[s], label=s)
    ax.legend(title="Strategy", frameon=False); ax.grid(axis="y", alpha=.3)
    _save(fig, "occupancy_by_fixed_bg_strategy")

    # 3. jitter vs occupancy
    fig, ax = plt.subplots(figsize=(7.6, 5.6))
    mk = {"L": "o", "M": "s", "H": "^"}
    for s in STRAT:
        for lv in LEVELS:
            sub = main_df[(main_df.strategy == s) & (main_df.bg_level == lv)]
            ax.scatter(sub.occ_total_pct, sub.jitter_us, color=COLORS[s], marker=mk[lv], s=55,
                       edgecolor="white", linewidth=.5)
    for s in STRAT: ax.scatter([], [], color=COLORS[s], label=f"{s}")
    for lv in LEVELS: ax.scatter([], [], color="#555", marker=mk[lv], label=f"BG-{lv}")
    ax.set_xlabel("reconstructed total occupancy (%)"); ax.set_ylabel("jitter SD (us)")
    ax.set_title("Fig3: jitter vs occupancy (bandwidth-timing relation)")
    ax.legend(frameon=False, fontsize=8, ncol=2); ax.grid(alpha=.3)
    _save(fig, "jitter_vs_occupancy")

    # 4. BG fps by condition (configured identical, observed differs?)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for si, s in enumerate(STRAT):
        for lv in LEVELS:
            sub = main_df[(main_df.strategy == s) & (main_df.bg_level == lv)]
            if sub.empty: continue
            _sc(ax, LVL_X[lv] + (si - 1) * 0.24, sub, "bg_fps", COLORS[s])
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["BG-L (630us)", "BG-M (240us)", "BG-H (170us)"])
    ax.set_ylabel("observed on-wire BG fps")
    ax.set_title("Fig4: on-wire BG throughput by condition (configured gap identical within level)")
    for s in STRAT: ax.scatter([], [], color=COLORS[s], label=s)
    ax.legend(title="Strategy", frameon=False); ax.grid(axis="y", alpha=.3)
    _save(fig, "bg_fps_by_condition")

    # 5. mid 240us ACF comparison (A-M/B-M/C-M)
    fig, ax = plt.subplots(figsize=(9, 5))
    for s in STRAT:
        sub = main_df[(main_df.strategy == s) & (main_df.bg_level == "M")].sort_values("run")
        if sub.empty: continue
        f = sub.iloc[0]["file"]; ac = acf_map.get(f)
        if ac is not None and len(ac):
            ax.plot(np.arange(1, len(ac) + 1), ac, color=COLORS[s], lw=1.3,
                    label=f"{s}-M run{int(sub.iloc[0]['run'])} (jit {sub.iloc[0]['jitter_us']:.0f})")
    ax.axhline(0, color="k", lw=.6); ax.set_xlim(0, 120)
    ax.set_xlabel("lag (0x100 cycles)"); ax.set_ylabel("inter-arrival error ACF")
    ax.set_title("Fig5: BG-M (gap=240 IDENTICAL) inter-arrival-error ACF, A vs B vs C")
    ax.legend(frameon=False, fontsize=8); ax.grid(alpha=.3)
    _save(fig, "mid_240us_acf_comparison")

    # 6. old vs new
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    if not ov.empty:
        x = np.arange(len(ov)); w = 0.38
        labels = [f"{r.strategy}-{r.bg_level}\n(old {r.old_target})" for _, r in ov.iterrows()]
        ax.bar(x - w/2, ov.old_jitter_mean, w, yerr=ov.old_jitter_sd, capsize=3, color="#bbb", label="OLD tuned-gap (confounded)")
        ax.bar(x + w/2, ov.new_jitter_mean, w, yerr=ov.new_jitter_sd, capsize=3,
               color=[COLORS[s] for s in ov.strategy], label="NEW fixed-gap")
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7)
        ax.set_ylabel("jitter SD (us)"); ax.legend(frameon=False, fontsize=8)
    ax.set_title("Fig6: OLD strategy-specific-gap vs NEW fixed-gap jitter")
    ax.grid(axis="y", alpha=.3)
    ax.text(0, -0.16, "OLD A-M(old A60) mean includes run1 anomaly; see report", transform=ax.transAxes, fontsize=7, color="#666")
    _save(fig, "old_vs_new_comparison")


def _save(fig, stem):
    fig.tight_layout(); fig.savefig(FIG / f"{stem}.png", dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _f(v, n=2):
    try: return f"{float(v):.{n}f}"
    except (TypeError, ValueError): return "n/a"


def write_report(df, main_df, base_df, cs_df, bgs_df, ov, map_tbl):
    csi = cs_df.set_index("condition")
    L = ["# Fixed external-background CONFIRMATORY analysis (A/B/C x L/M/H x n=5)", ""]
    L += [
        f"- Raw: `{RAW}` (48 TRC: 45 main + 3 BG-OFF baseline a0/b0/c0). Original TRC unmodified; "
        "outputs only in this folder.",
        "- **Same configured external BG gap for all strategies at each level** (L=630, M=240, H=170 us) - "
        "this removes the earlier strategy-specific dummy-gap tuning confound.",
        "- Background-only PCAN load reference (calibration only, NOT the A/B/C total load): "
        "630->~9%, 240->~52%, 170->~75%.",
        "- Metrics reuse verified n=10 module (`interval_metrics`, `wire_breakdown`, `EXPECTED` layout). "
        "Replicate unit = run (n=5); no frame-level pseudo-replication. jitter = SD of consecutive 0x100 "
        "inter-arrival gaps (NOT latency). reconstructed occupancy != PCAN actual Mean Load (actual = UNKNOWN, "
        "not recorded).",
        "",
        "## 1. Mapping (verified, filename -> condition; observed-mode is a MAPPING CHECK, not a configured value)",
        "",
        "| strategy | BG level | configured gap us | runs | obs BG spacing mode us |",
        "|---|---|--:|---|--:|",
    ]
    for _, r in map_tbl.iterrows():
        L.append(f"| {r.strategy} | {r.bg_level} | {CONFIG_GAP[{'L':1,'M':2,'H':3}[r.bg_level]]} | {r.runs} | {_f(r.obs_bg_mode,0)} |")

    qcc = dict(main_df.qc_status.value_counts())
    L += ["", f"## 2. QC: main {qcc}", "",
          "Control layout verified against source module `EXPECTED` (A: 0x100/0x101/0x102 + 50ms 0x110/0x120/0x130; "
          "B: 0x100(32B)+0x110(32B); C: 0x100(64B)). Per-file detail in `file_qc.csv`."]
    notes = main_df[main_df.qc_status != "PASS"]
    if not notes.empty:
        L += ["", "Timing-note / fail files:"]
        for _, r in notes.iterrows():
            L.append(f"- {r.file} ({r.strategy}-{r.bg_level} run{int(r.run)}): {r.qc_status}; "
                     f"gap>6ms={int(r.gap_gt_6ms)}, gap>10ms={int(r.gap_gt_10ms)}, max {(_f(r.max_interval_us/1000,1))} ms.")
    else:
        L.append("\nAll 45 main files structurally PASS.")

    L += ["", "## 3. Background common-input check (configured vs observed on-wire)", "",
          "| condition | configured gap | obs mode | obs median | obs IQR | bg fps mean+-sd | occ_bg% |",
          "|---|--:|--:|--:|--:|--|--:|"]
    for _, r in bgs_df.iterrows():
        L.append(f"| {r.condition} | {r.configured_external_bg_gap_us} | {_f(r.obs_bg_spacing_mode_us,0)} | "
                 f"{_f(r.obs_bg_spacing_median_us,1)} | {_f(r.obs_bg_spacing_iqr_us,1)} | "
                 f"{_f(r.bg_fps_mean,0)}+-{_f(r.bg_fps_sd,0)} | {_f(r.occ_bg_pct_mean,1)} |")

    L += ["", "## 4/5. 0x100 jitter by condition (n=5 run-level)", "",
          "| condition | jitter mean+-SD us | median [min,max] | p99 mean | >100us% mean | occ_total% mean+-SD |",
          "|---|--|--|--:|--:|--|"]
    for lv in LEVELS:
        for s in STRAT:
            c = f"{s}-{lv}"
            if c not in csi.index: continue
            r = csi.loc[c]
            L.append(f"| {c} | {_f(r.jitter_mean)}+-{_f(r.jitter_sd)} | {_f(r.jitter_median)} "
                     f"[{_f(r.jitter_min)},{_f(r.jitter_max)}] | {_f(r.p99_mean,1)} | {_f(r.gt100_mean,2)} | "
                     f"{_f(r.occ_total_mean)}+-{_f(r.occ_total_sd)} |")

    # per-level ordering
    L += ["", "### Per-level strategy ordering (ascending jitter)"]
    for lv in LEVELS:
        got = [(s, csi.loc[f"{s}-{lv}", "jitter_mean"]) for s in STRAT if f"{s}-{lv}" in csi.index]
        got.sort(key=lambda t: t[1])
        L.append(f"- **BG-{lv}**: " + " < ".join(f"{s}({_f(j)})" for s, j in got))

    L += ["", "## 6. Occupancy / bandwidth (same BG input, strategy differs)", "",
          "| condition | occ_total% | occ_ctrl% | occ_bg% | jitter us |", "|---|--:|--:|--:|--:|"]
    for lv in LEVELS:
        for s in STRAT:
            c = f"{s}-{lv}"
            if c not in csi.index: continue
            r = csi.loc[c]
            L.append(f"| {c} | {_f(r.occ_total_mean,2)} | {_f(r.occ_ctrl_mean,2)} | {_f(r.occ_bg_mean,2)} | {_f(r.jitter_mean,2)} |")

    L += ["", "## 7. OLD (strategy-specific tuned gap, confounded) vs NEW (fixed gap)", "",
          "| strat | level | new gap | old target | old jitter | new jitter | old occ% | new occ% |",
          "|---|---|--:|---|--|--|--:|--:|"]
    if not ov.empty:
        for _, r in ov.iterrows():
            L.append(f"| {r.strategy} | {r.bg_level} | {r.configured_gap_new} | {r.old_target} | "
                     f"{_f(r.old_jitter_mean)}+-{_f(r.old_jitter_sd)} | {_f(r.new_jitter_mean)}+-{_f(r.new_jitter_sd)} | "
                     f"{_f(r.old_occ_mean,1)} | {_f(r.new_occ_total_mean,1)} |")
    L.append("\n(OLD A-M corresponds to old A60 whose n=5 mean includes the run1 anomaly ~59us; old A60 run2-8 ~23us.)")

    # baseline
    L += ["", "## 10. Baseline (reference only; NOT new n=5)", "",
          "| file | dur s | 0x100 | jitter us | median|err| us | max interval ms | note |", "|---|--:|--:|--:|--:|--:|---|"]
    for _, r in base_df.iterrows():
        note = "known rare silence" if r.max_interval_us and r.max_interval_us > 20000 else ""
        L.append(f"| {r.file} | {_f(r.duration_s,1)} | {int(r.frame_0x100)} | {_f(r.jitter_us,1)} | "
                 f"{_f(r.abs_err_median_us,1)} | {_f((r.max_interval_us or 0)/1000,1)} | {note} |")
    L.append("\nRobust baseline: median |error| column is the robust summary (jitter SD can be inflated by a "
             "single rare silence; known C0/A0 anomalies from the exploratory set are preserved there, not here).")

    L += ["", "## Figures", ""]
    for png in sorted(FIG.glob("*.png")):
        L.append(f"- `figures/{png.name}`")
    (HERE / "fixed_bg_confirmatory_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
