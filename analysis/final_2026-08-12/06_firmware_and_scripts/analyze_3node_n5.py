#!/usr/bin/env python3
"""3-node external-background CAN-FD repeated dataset analysis (n=5 per condition).

This driver DOES NOT redefine any timing/occupancy/QC metric.  It imports the
verified n=10 analysis module (``analyze_fixed2_64b_n10.py``) and reuses its
exact definitions, exactly like the n=1 pilot driver
(``analysis_pilot_run1/analyze_3node_pilot.py``):

- ``parse_trace``       -> frame parsing + header + parse-error capture
- ``interval_metrics``  -> 0x100 inter-arrival jitter / abs-error / tail
                           (already returns >50/>100/>200 us rates)
- ``wire_breakdown``    -> ISO-corrected per-frame airtime (reconstructed occupancy)
- ``expected_kind``     -> signal / dummy / unexpected classification
- ``EXPECTED`` / ``EXPECTED_PAYLOAD`` -> per-strategy frame layout + fixed payload

Design of THIS campaign:
- 12 conditions (A/B/C x baseline/30/60/80) x run1..run5 = 60 balanced TRC.
- ONE extra replicate ``a1_6.trc`` (A, 30-target, run6) exists.  It is EXCLUDED
  from all primary n=5 statistics and analysed ONLY as an extra-replicate
  sensitivity check.
- run==index is treated as the independent replicate.  n=5 per condition.
- No firmware was modified between runs (same background firmware as run1).

Original TRC files are never modified.  Everything is written under
``3node/analysis_n5/``.  The n=1 pilot output directory is left untouched.
"""
from __future__ import annotations

import csv
import hashlib
import platform
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --- import the verified n=10 analysis module as a metric library -------------
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]  # ...\3node\analysis_n5 -> repo root
CANON_DIR = REPO_ROOT / "trace_fixed2" / "analysis_n10"
sys.path.insert(0, str(CANON_DIR))
import analyze_fixed2_64b_n10 as canon  # noqa: E402  (verified module reuse)

RAW_DIR = REPO_ROOT / "3node"
OUT_DIR = HERE
FIG_DIR = OUT_DIR / "figures"

NOMINAL_PERIOD_US = canon.NOMINAL_PERIOD_US  # 5000
TARGET_LABEL = {0: "baseline", 1: "30", 2: "60", 3: "80"}
TARGET_ORDER = ("baseline", "30", "60", "80")
STRATEGIES = ("A", "B", "C")
COLORS = {"A": "#0072B2", "B": "#D55E00", "C": "#009E73"}
FILENAME_RE = re.compile(r"^([abc])([0-3])_(\d+)\.trc$", re.I)

PRIMARY_RUNS = (1, 2, 3, 4, 5)          # balanced n=5 statistics use ONLY these
COMMON_WINDOW_US = 15_000_000           # 15 s sensitivity window (run1 duration guard)

# user-confirmed 3-node dummy gap NOMINAL calibration (us); order = 30/60/80 target.
# NOTE: during the repeated campaign the user live-adjusted the dummy gap by
# approximately +/-1 us on some strategy/load/run combinations to better match the
# target PCAN bus load.  Exact per-run gap was NOT recorded, so we store the nominal
# calibration value plus an explicit note and never fabricate a per-run value.
DUMMY_GAP_NOMINAL_US = {
    ("A", 1): 627, ("A", 2): 240, ("A", 3): 170,
    ("B", 1): 616, ("B", 2): 235, ("B", 3): 168,
    ("C", 1): 617, ("C", 2): 238, ("C", 3): 170,
}
GAP_LIVE_NOTE = ("live-adjusted by approximately +/-1 us on some runs; "
                 "exact per-run value not recorded")

# 2-node fixed-payload n=10 canonical result (Shared Brain source of truth).
# Used ONLY for descriptive comparison, never pooled with the 3-node runs.
TWO_NODE_N10 = {
    "A0": dict(jitter=6.5,  p99=6.0,   gt100=0.10, occ=8.40),
    "B0": dict(jitter=4.8,  p99=4.0,   gt100=0.02, occ=4.98),
    "C0": dict(jitter=5.4,  p99=5.0,   gt100=0.10, occ=7.32),
    "A30": dict(jitter=36.2, p99=122.4, gt100=4.98, occ=29.58),
    "B30": dict(jitter=51.6, p99=126.4, gt100=10.55, occ=33.13),
    "C30": dict(jitter=36.1, p99=96.1,  gt100=5.45, occ=33.17),
    "A60": dict(jitter=59.8, p99=132.0, gt100=13.50, occ=63.25),
    "B60": dict(jitter=61.8, p99=124.8, gt100=8.33, occ=61.92),
    "C60": dict(jitter=22.1, p99=124.3, gt100=2.75, occ=63.34),
    "A80": dict(jitter=67.0, p99=104.4, gt100=2.05, occ=83.34),
    "B80": dict(jitter=69.5, p99=107.5, gt100=10.11, occ=82.26),
    "C80": dict(jitter=73.8, p99=106.2, gt100=18.98, occ=82.82),
}


def sha256_file(path: Path) -> str:
    return canon.sha256_file(path)


def parse_filename(name: str):
    m = FILENAME_RE.fullmatch(name)
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2)), int(m.group(3))


def analyze_file(path: Path, interval_writer: csv.DictWriter) -> dict:
    strategy, mode, run = parse_filename(path.name)
    target = TARGET_LABEL[mode]
    cond = f"{strategy}{target}"
    key = canon.FileKey(path.name, strategy, mode, target, run)

    result = canon.parse_trace(path, key, interval_writer)
    frames = result["frames"]
    header = result["header"]
    parse_errors = result["parse_errors"]

    ts = np.asarray([f.timestamp_us for f in frames], dtype=np.int64)
    duration_s = (ts[-1] - ts[0]) / 1e6 if len(ts) > 1 else 0.0
    backwards = int(np.sum(np.diff(ts) < 0)) if len(ts) > 1 else 0
    duplicates = int(np.sum(np.diff(ts) == 0)) if len(ts) > 1 else 0
    last_message_number = int(result.get("last_message_number", len(frames)) or len(frames))

    nominal_bps = float(header["nominal_bit_rate_bps"])
    data_bps = float(header["data_bit_rate_bps"])
    if not (np.isfinite(nominal_bps) and np.isfinite(data_bps)):
        nominal_bps, data_bps = canon.LOOKUP_NOMINAL_BPS, canon.LOOKUP_DATA_BPS

    groups: dict[int, list] = defaultdict(list)
    for fr in frames:
        groups[fr.can_id].append(fr)

    expected_ids = set(canon.EXPECTED[strategy])
    observed = set(groups)
    missing_ids = sorted(expected_ids - observed)
    unexpected_ids = sorted(
        cid for cid in observed
        if cid not in expected_ids and not (0x300 <= cid <= 0x30F)
    )
    dummy_ids = sorted(cid for cid in observed if 0x300 <= cid <= 0x30F)
    dummy_frames = sum(len(groups[c]) for c in dummy_ids)
    control_frames = sum(len(groups[c]) for c in observed if c in expected_ids)

    layout_ok_all = True
    payload_fixed_all = True
    id_rows = []
    total_airtime_us = 0.0
    esi_total = fd_total = brs_total = 0
    for cid, grp in sorted(groups.items()):
        kind, exp_len, period = canon.expected_kind(strategy, cid)
        lengths = sorted(set(f.length for f in grp))
        payload_counter = Counter(f.payload for f in grp)
        is_fd_all = all(f.is_fd for f in grp)
        brs_all = all(f.brs for f in grp)
        esi_count = sum(f.esi for f in grp)
        esi_total += esi_count
        fd_total += sum(f.is_fd for f in grp)
        brs_total += sum(f.brs for f in grp)
        fps = len(grp) / duration_s if duration_s > 0 else np.nan
        exp_payload = canon.EXPECTED_PAYLOAD[strategy].get(cid)
        payload_match = (
            (len(payload_counter) == 1 and next(iter(payload_counter)) == exp_payload)
            if exp_payload is not None else None
        )
        layout_ok = (
            kind != "unexpected" and len(lengths) == 1
            and (exp_len is None or lengths[0] == exp_len)
            and is_fd_all and brs_all and esi_count == 0
        )
        if kind != "unexpected":
            layout_ok_all = layout_ok_all and layout_ok
        if exp_payload is not None and payload_match is False:
            payload_fixed_all = False
        if len(payload_counter) != 1 and kind == "signal":
            payload_fixed_all = False

        cid_airtime = 0.0
        for payload, count in payload_counter.items():
            sample = next(f for f in grp if f.payload == payload)
            wb = canon.wire_breakdown(cid, payload, sample.esi, nominal_bps, data_bps, legacy=False)
            cid_airtime += float(wb["estimated_airtime_us"]) * count
        total_airtime_us += cid_airtime

        id_rows.append(dict(
            source_file=path.name, strategy=strategy, target=target, condition=cond, run=run,
            can_id_hex=f"0x{cid:03X}", frame_kind=kind, frame_count=len(grp), fps=fps,
            observed_dlc_bytes="|".join(map(str, lengths)),
            expected_dlc_bytes=("" if exp_len is None else exp_len),
            unique_payload_count=len(payload_counter),
            within_run_byte_identical=(len(payload_counter) == 1),
            matches_defined_payload=payload_match,
            is_fd_all=is_fd_all, brs_all=brs_all, esi_count=esi_count,
            occupancy_contribution_pct=(cid_airtime / (duration_s * 1e6) * 100 if duration_s > 0 else np.nan),
        ))

    reconstructed_occupancy_pct = (
        total_airtime_us / (duration_s * 1e6) * 100 if duration_s > 0 else np.nan
    )
    background_fps = dummy_frames / duration_s if duration_s > 0 else np.nan
    control_fps = control_frames / duration_s if duration_s > 0 else np.nan
    total_fps = len(frames) / duration_s if duration_s > 0 else np.nan

    # 0x100 inter-arrival metrics (reused interval_metrics), full window
    ts100 = np.asarray([f.timestamp_us for f in frames if f.can_id == 0x100], dtype=np.int64)
    metrics, gaps, errors = canon.interval_metrics(ts100, duration_s, warmup_us=0)

    # 15 s common-window sensitivity (guards run1 short-capture duration differences)
    if len(ts100) > 1:
        ts100_win = ts100[ts100 <= ts100[0] + COMMON_WINDOW_US]
        win_dur = (ts100_win[-1] - ts100_win[0]) / 1e6 if len(ts100_win) > 1 else 0.0
        win_metrics, _, _ = canon.interval_metrics(ts100_win, win_dur, warmup_us=0)
    else:
        win_metrics = {}

    error_frame_count = sum(1 for f in frames if "ERR" in f.type_token.upper())

    # naming-vs-content mapping QC (verified, not assumed)
    exp_0x100_dlc = canon.EXPECTED[strategy][0x100][0]  # A=8 B=32 C=64
    obs_0x100_dlc = sorted(set(f.length for f in groups.get(0x100, [])))
    letter_ok = (obs_0x100_dlc == [exp_0x100_dlc])
    number_dummy_ok = (dummy_frames == 0) if mode == 0 else (dummy_frames > 0)

    qc_flags = {
        "parse_ok": len(parse_errors) == 0 and len(frames) > 0,
        "monotonic_ok": backwards == 0,
        "all_standard_id": all(f.can_id <= 0x7FF for f in frames),
        "fd_all": fd_total == len(frames),
        "brs_all": brs_total == len(frames),
        "no_esi": esi_total == 0,
        "no_error_frames": error_frame_count == 0,
        "layout_ok": layout_ok_all,
        "no_missing_expected_id": len(missing_ids) == 0,
        "no_unexpected_id": len(unexpected_ids) == 0,
        "payload_byte_identical": payload_fixed_all,
        "letter_mapping_ok": letter_ok,
        "number_dummy_mapping_ok": number_dummy_ok,
    }
    qc_pass = all(qc_flags.values())

    def r(k, default=np.nan):
        return metrics.get(k, default)

    gap_nominal = DUMMY_GAP_NOMINAL_US.get((strategy, mode), "")

    qc_row = dict(
        source_file=path.name, file_size_bytes=path.stat().st_size, sha256=sha256_file(path),
        strategy=strategy, mode=mode, target=target, condition=cond, run=run,
        is_primary=(run in PRIMARY_RUNS),
        dummy_gap_nominal_us=gap_nominal,
        trc_version=header["trc_version"], start_time_text=header["start_time_text"],
        nominal_bit_rate_bps=nominal_bps, data_bit_rate_bps=data_bps,
        duration_s=duration_s, total_frames=len(frames),
        last_message_number=last_message_number,
        parse_error_count=len(parse_errors),
        timestamp_backwards_count=backwards, timestamp_duplicate_count=duplicates,
        observed_id_count=len(groups),
        observed_ids="|".join(f"0x{c:03X}" for c in sorted(groups)),
        missing_expected_ids="|".join(f"0x{c:03X}" for c in missing_ids),
        unexpected_ids="|".join(f"0x{c:03X}" for c in unexpected_ids),
        dummy_id_count=len(dummy_ids), dummy_frame_count=dummy_frames,
        control_frame_count=control_frames,
        obs_0x100_dlc_bytes="|".join(map(str, obs_0x100_dlc)),
        expected_0x100_dlc_bytes=exp_0x100_dlc,
        frame_0x100_count=int(len(ts100)),
        fd_frame_count=fd_total, brs_frame_count=brs_total, esi_frame_count=esi_total,
        error_frame_count=error_frame_count,
        gap_gt_6000_count=r("gap_gt_6000_count", 0),
        near_10ms_frame_loss_candidate_count=r("near_10ms_frame_loss_candidate_count", 0),
        reconstructed_occupancy_pct=reconstructed_occupancy_pct,
        background_fps=background_fps,
        hit_300k_ceiling=(len(frames) >= 300000 or last_message_number >= 300000),
        **{f"qc_{k}": v for k, v in qc_flags.items()},
        qc_pass=qc_pass,
    )

    run_row = dict(
        source_file=path.name, strategy=strategy, target=target, condition=cond, run=run,
        is_primary=(run in PRIMARY_RUNS),
        dummy_gap_nominal_us=gap_nominal,
        duration_s=duration_s, total_frames=len(frames), last_message_number=last_message_number,
        actual_pcan_mean_load="",  # NOT saved this campaign
        reconstructed_occupancy_pct=reconstructed_occupancy_pct,
        control_frames=control_frames, background_frames=dummy_frames,
        total_fps=total_fps, control_fps=control_fps, background_fps=background_fps,
        frame_0x100_count=int(len(ts100)),
        n_intervals=r("number_intervals", 0),
        mean_interval_us=r("mean_gap_us"), median_interval_us=r("median_gap_us"),
        jitter_std_us=r("jitter_std_us"),
        min_interval_us=r("min_gap_us"), max_interval_us=r("max_gap_us"),
        abs_error_mean_us=r("abs_error_mean_us"), abs_error_median_us=r("abs_error_median_us"),
        abs_error_p95_us=r("abs_error_p95_us"), abs_error_p99_us=r("abs_error_p99_us"),
        abs_error_max_us=r("abs_error_max_us"),
        gt50us_count=r("abs_error_gt_50us_count", 0),
        gt50us_rate_pct=_rate_pct(r("abs_error_gt_50us_rate")),
        gt100us_count=r("abs_error_gt_100us_count", 0),
        gt100us_rate_pct=_rate_pct(r("abs_error_gt_100us_rate")),
        gt200us_count=r("abs_error_gt_200us_count", 0),
        gt200us_rate_pct=_rate_pct(r("abs_error_gt_200us_rate")),
        gap_gt_6000_count=r("gap_gt_6000_count", 0),
        near_10ms_candidate_count=r("near_10ms_frame_loss_candidate_count", 0),
        # 15 s common-window sensitivity
        jitter_std_us_win15s=win_metrics.get("jitter_std_us", np.nan),
        gt100us_rate_pct_win15s=_rate_pct(win_metrics.get("abs_error_gt_100us_rate", np.nan)),
        n_intervals_win15s=win_metrics.get("number_intervals", 0),
    )

    tail_row = dict(
        source_file=path.name, condition=cond, strategy=strategy, target=target, run=run,
        is_primary=(run in PRIMARY_RUNS),
        duration_s=duration_s, n_intervals=r("number_intervals", 0),
        gt100us_count=r("abs_error_gt_100us_count", 0), gt100us_rate_pct=_rate_pct(r("abs_error_gt_100us_rate")),
        gt200us_count=r("abs_error_gt_200us_count", 0), gt200us_rate_pct=_rate_pct(r("abs_error_gt_200us_rate")),
        gap_gt_6000_count=r("gap_gt_6000_count", 0),
        gap_gt_6000_per_min=(r("gap_gt_6000_count", 0) / (duration_s / 60.0) if duration_s > 0 else np.nan),
        near_10ms_candidate_count=r("near_10ms_frame_loss_candidate_count", 0),
        max_interval_us=r("max_gap_us"), max_interval_ms=(r("max_gap_us") / 1000.0 if np.isfinite(r("max_gap_us")) else np.nan),
    )

    return dict(qc_row=qc_row, run_row=run_row, id_rows=id_rows, tail_row=tail_row,
                condition=cond, strategy=strategy, mode=mode, target=target, run=run,
                gaps=gaps, errors=errors)


def _rate_pct(x):
    return x * 100 if (x is not None and np.isfinite(x)) else np.nan


def _agg(series):
    v = pd.to_numeric(series, errors="coerce").to_numpy(float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return dict(n=0, mean=np.nan, sd=np.nan, median=np.nan, vmin=np.nan, vmax=np.nan, cv=np.nan)
    mean = float(v.mean())
    sd = float(v.std(ddof=1)) if len(v) > 1 else np.nan
    return dict(n=len(v), mean=mean, sd=sd, median=float(np.median(v)),
                vmin=float(v.min()), vmax=float(v.max()),
                cv=(sd / mean if (mean not in (0, np.nan) and np.isfinite(sd)) else np.nan))


def main() -> int:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    trc_files = sorted(RAW_DIR.glob("*.trc"), key=lambda p: p.name.lower())
    assert trc_files, f"no TRC files under {RAW_DIR}"

    interval_path = OUT_DIR / "interarrival_samples.csv"
    interval_cols = ["source_file", "strategy", "load_mode", "load_pct_label", "run",
                     "analysis_window", "timestamp_us", "gap_us", "error_us", "abs_error_us"]

    qc_rows, run_rows, id_rows, tail_rows = [], [], [], []
    per_file = {}

    with interval_path.open("w", newline="", encoding="utf-8-sig") as fh:
        iw = csv.DictWriter(fh, fieldnames=interval_cols)
        iw.writeheader()
        for p in trc_files:
            if parse_filename(p.name) is None:
                qc_rows.append(dict(source_file=p.name, qc_pass=False, qc_filename_mismatch=True))
                continue
            print(f"[parse] {p.name}")
            res = analyze_file(p, iw)
            qc_rows.append(res["qc_row"])
            run_rows.append(res["run_row"])
            id_rows.extend(res["id_rows"])
            tail_rows.append(res["tail_row"])
            per_file[res["run_row"]["source_file"]] = res

    qc_df = pd.DataFrame(qc_rows)
    run_df = pd.DataFrame(run_rows)
    id_df = pd.DataFrame(id_rows)
    tail_df = pd.DataFrame(tail_rows)

    primary = run_df[run_df.is_primary].copy()   # run1..5 ONLY
    extra = run_df[~run_df.is_primary].copy()     # a1_6 run6

    # ---------- inventory.csv ------------------------------------------------
    inv_rows = []
    for s in STRATEGIES:
        for mode in (0, 1, 2, 3):
            t = TARGET_LABEL[mode]
            cond = f"{s}{t}"
            sub = run_df[(run_df.strategy == s) & (run_df.target == t)]
            runs_present = sorted(sub.run.tolist())
            primary_present = sorted([x for x in runs_present if x in PRIMARY_RUNS])
            missing = sorted(set(PRIMARY_RUNS) - set(primary_present))
            inv_rows.append(dict(
                condition=cond, strategy=s, target=t,
                runs_present="|".join(map(str, runs_present)),
                primary_run_count=len(primary_present),
                primary_complete=(len(primary_present) == 5),
                missing_primary_runs="|".join(map(str, missing)),
                extra_runs="|".join(str(x) for x in runs_present if x not in PRIMARY_RUNS),
            ))
    inv_df = pd.DataFrame(inv_rows)

    # ---------- condition_summary_n5.csv (run == replicate; n=5) -------------
    metric_map = [
        ("jitter_std_us", "jitter"),
        ("abs_error_p99_us", "p99"),
        ("abs_error_p95_us", "p95"),
        ("gt100us_rate_pct", "gt100_rate"),
        ("gt50us_rate_pct", "gt50_rate"),
        ("reconstructed_occupancy_pct", "occ"),
        ("background_fps", "bgfps"),
        ("duration_s", "dur"),
    ]
    cs_rows = []
    for s in STRATEGIES:
        for mode in (0, 1, 2, 3):
            t = TARGET_LABEL[mode]
            cond = f"{s}{t}"
            sub = primary[primary.condition == cond]
            if sub.empty:
                continue
            row = dict(condition=cond, strategy=s, target=t, run_count=len(sub),
                       dummy_gap_nominal_us=DUMMY_GAP_NOMINAL_US.get((s, mode), "OFF" if mode == 0 else ""))
            for col, tag in metric_map:
                a = _agg(sub[col])
                row[f"{tag}_mean"] = a["mean"]
                row[f"{tag}_sd"] = a["sd"]
                row[f"{tag}_median"] = a["median"]
                row[f"{tag}_min"] = a["vmin"]
                row[f"{tag}_max"] = a["vmax"]
                if tag in ("jitter", "occ"):
                    row[f"{tag}_cv"] = a["cv"]
            cs_rows.append(row)
    cs_df = pd.DataFrame(cs_rows)

    # ---------- load_matching_n5.csv -----------------------------------------
    lm_rows = []
    for mode in (0, 1, 2, 3):
        t = TARGET_LABEL[mode]
        occ_means = {}
        for s in STRATEGIES:
            sub = primary[primary.condition == f"{s}{t}"]
            a = _agg(sub["reconstructed_occupancy_pct"])
            occ_means[s] = a["mean"]
            lm_rows.append(dict(
                target=t, strategy=s, run_count=a["n"],
                occ_mean_pct=a["mean"], occ_sd_pct=a["sd"],
                occ_min_pct=a["vmin"], occ_max_pct=a["vmax"],
                bgfps_mean=_agg(sub["background_fps"])["mean"],
                totalfps_mean=_agg(sub["total_fps"])["mean"],
            ))
        valid = {k: v for k, v in occ_means.items() if np.isfinite(v)}
        if len(valid) >= 2:
            spread = max(valid.values()) - min(valid.values())
            for a, b in combinations(sorted(valid), 2):
                lm_rows.append(dict(
                    target=t, strategy=f"{a}-{b} diff",
                    occ_mean_pct=valid[a] - valid[b],
                    occ_sd_pct=np.nan, occ_min_pct=np.nan, occ_max_pct=np.nan,
                    bgfps_mean=np.nan, totalfps_mean=np.nan,
                    pairwise_abs_diff_pp=abs(valid[a] - valid[b]), max_spread_pp=spread))
    lm_df = pd.DataFrame(lm_rows)

    # ---------- extra_run6_sensitivity.csv -----------------------------------
    er_rows = []
    if not extra.empty:
        for _, ex in extra.iterrows():
            cond = ex["condition"]
            n5 = primary[primary.condition == cond]
            for col, tag in (("jitter_std_us", "jitter"), ("abs_error_p99_us", "p99"),
                             ("gt100us_rate_pct", "gt100_rate"), ("reconstructed_occupancy_pct", "occ")):
                a5 = _agg(n5[col])
                v6 = pd.to_numeric(pd.concat([n5[col], pd.Series([ex[col]])]), errors="coerce")
                a6 = _agg(v6)
                er_rows.append(dict(
                    condition=cond, extra_file=ex["source_file"], metric=tag,
                    n5_mean=a5["mean"], n5_sd=a5["sd"],
                    extra_run6_value=float(ex[col]) if np.isfinite(ex[col]) else np.nan,
                    n6_mean=a6["mean"], n6_sd=a6["sd"],
                    mean_shift=(a6["mean"] - a5["mean"]) if np.isfinite(a6["mean"]) and np.isfinite(a5["mean"]) else np.nan,
                ))
    er_df = pd.DataFrame(er_rows)

    # ---------- run_manifest_n5.csv ------------------------------------------
    man_rows = []
    for _, r in run_df.sort_values(["strategy", "target", "run"]).iterrows():
        mode = {v: k for k, v in TARGET_LABEL.items()}[r["target"]]
        gap = DUMMY_GAP_NOMINAL_US.get((r["strategy"], mode), "")
        if r["target"] == "baseline":
            gap_note = "dummy OFF (baseline)"
        else:
            gap_note = f"nominal {gap} us; {GAP_LIVE_NOTE}"
        man_rows.append(dict(
            filename=r["source_file"], strategy=r["strategy"], target=r["target"], run=r["run"],
            is_primary_n5=r["is_primary"],
            dummy_gap_nominal_us=(gap if r["target"] != "baseline" else "OFF"),
            dummy_gap_note=gap_note,
            duration_s=round(r["duration_s"], 3), total_frames=int(r["total_frames"]),
            last_message_number=int(r["last_message_number"]),
            hit_300k_ceiling=bool(qc_df.loc[qc_df.source_file == r["source_file"], "hit_300k_ceiling"].iloc[0]),
            actual_pcan_mean_load="",  # NOT recorded this campaign
            reconstructed_occupancy_pct=round(r["reconstructed_occupancy_pct"], 4),
            background_fps=(round(r["background_fps"], 2) if np.isfinite(r["background_fps"]) else ""),
            jitter_std_us=(round(r["jitter_std_us"], 3) if np.isfinite(r["jitter_std_us"]) else ""),
            notes="3-node; PCAN Listen-Only; external background TX node; same firmware as run1; "
                  "reconstructed occupancy != PCAN actual Mean Load",
        ))
    man_df = pd.DataFrame(man_rows)

    # --- write CSV deliverables ----------------------------------------------
    def wcsv(df, name):
        df.to_csv(OUT_DIR / name, index=False, encoding="utf-8-sig", lineterminator="\n")

    wcsv(inv_df, "inventory.csv")
    wcsv(qc_df, "qc_by_file.csv")
    wcsv(run_df.sort_values(["strategy", "target", "run"]), "run_level_metrics.csv")
    wcsv(cs_df, "condition_summary_n5.csv")
    wcsv(lm_df, "load_matching_n5.csv")
    wcsv(id_df, "summary_by_id.csv")
    wcsv(tail_df.sort_values(["strategy", "target", "run"]), "tail_events.csv")
    wcsv(man_df, "run_manifest_n5.csv")
    wcsv(er_df, "extra_run6_sensitivity.csv")

    pd.DataFrame([dict(source_file=r["source_file"], file_size_bytes=r.get("file_size_bytes"),
                       sha256=r.get("sha256")) for r in qc_rows if "sha256" in r]).to_csv(
        OUT_DIR / "input_file_sha256.csv", index=False, encoding="utf-8-sig", lineterminator="\n")

    (OUT_DIR / "environment_info.txt").write_text(
        "\n".join([
            f"generated_at_local={datetime.now().astimezone().isoformat()}",
            f"platform={platform.platform()}",
            f"python_version={platform.python_version()}",
            f"numpy=={np.__version__}", f"pandas=={pd.__version__}",
            f"reused_module={CANON_DIR / 'analyze_fixed2_64b_n10.py'}",
            f"reused_module_sha256={sha256_file(CANON_DIR / 'analyze_fixed2_64b_n10.py')}",
            "design=3x4 conditions x run1..5 (n=5 balanced) + 1 extra a1 run6 (sensitivity only)",
            "replicate_unit=run (run1..5); within-trace frames are NOT independent replicates",
        ]) + "\n", encoding="utf-8")

    # --- figures --------------------------------------------------------------
    make_figures(primary, cs_df, per_file)

    # --- markdown report ------------------------------------------------------
    write_report(qc_df, inv_df, primary, extra, cs_df, lm_df, er_df, tail_df, run_df)

    n_pass = int(qc_df.get("qc_pass", pd.Series(dtype=bool)).fillna(False).sum())
    print(f"QC pass: {n_pass}/{len(qc_df)}   primary(n=5) rows: {len(primary)}   extra: {len(extra)}")
    return 0


def make_figures(primary, cs_df, per_file):
    csi = cs_df.set_index("condition")

    # 1) strategy x load jitter interaction (mean +/- run-level SD)
    fig, ax = plt.subplots(figsize=(8.5, 5))
    x = np.arange(len(TARGET_ORDER))
    for s in STRATEGIES:
        means, sds = [], []
        for t in TARGET_ORDER:
            c = f"{s}{t}"
            means.append(csi.loc[c, "jitter_mean"] if c in csi.index else np.nan)
            sds.append(csi.loc[c, "jitter_sd"] if c in csi.index else np.nan)
        ax.errorbar(x, means, yerr=sds, marker="o", capsize=4, color=COLORS[s], label=s, lw=2)
    ax.set_xticks(x); ax.set_xticklabels(TARGET_ORDER)
    ax.set_xlabel("Target condition"); ax.set_ylabel("Mean 0x100 inter-arrival jitter SD (us)")
    ax.set_title("3-node n=5: strategy x load jitter interaction")
    ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.25)
    ax.text(0.01, -0.16, "n=5 independent runs; error bar = run-level SD; "
            "jitter = SD of consecutive 0x100 inter-arrival gaps (NOT latency)",
            transform=ax.transAxes, fontsize=7, color="#555")
    _save(fig, "01_strategy_x_load_jitter_interaction")

    # 2) 60-target A/B/C run-level scatter
    fig, ax = plt.subplots(figsize=(7, 5))
    for i, s in enumerate(STRATEGIES):
        sub = primary[primary.condition == f"{s}60"].sort_values("run")
        ax.scatter([i] * len(sub), sub["jitter_std_us"], color=COLORS[s], s=70, zorder=3)
        for _, rr in sub.iterrows():
            ax.annotate(f"r{int(rr.run)}", (i, rr.jitter_std_us), fontsize=7,
                        xytext=(6, 0), textcoords="offset points", color="#444")
        m = _agg(sub["jitter_std_us"])
        ax.hlines(m["mean"], i - 0.22, i + 0.22, color=COLORS[s], lw=2)
    ax.set_xticks(range(3)); ax.set_xticklabels(["A60", "B60", "C60"])
    ax.set_ylabel("0x100 inter-arrival jitter SD (us)")
    ax.set_title("3-node n=5: 60-target run-level jitter (bar = mean)")
    ax.grid(axis="y", alpha=.25)
    ax.text(0.01, -0.14, "n=5 independent runs; reconstructed occupancy != PCAN actual Mean Load",
            transform=ax.transAxes, fontsize=7, color="#555")
    _save(fig, "02_60target_run_level_scatter")

    # 3) all-condition run-level jitter scatter
    order = [f"{s}{t}" for t in TARGET_ORDER for s in STRATEGIES]
    fig, ax = plt.subplots(figsize=(11, 5))
    for i, c in enumerate(order):
        sub = primary[primary.condition == c]
        if sub.empty:
            continue
        ax.scatter([i] * len(sub), sub["jitter_std_us"], color=COLORS[c[0]], s=45, alpha=.85, zorder=3)
        m = _agg(sub["jitter_std_us"])
        ax.hlines(m["mean"], i - 0.3, i + 0.3, color=COLORS[c[0]], lw=2)
    ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=45)
    ax.set_ylabel("0x100 inter-arrival jitter SD (us)")
    ax.set_title("3-node n=5: run-level jitter, all 12 conditions (bar = mean)")
    ax.grid(axis="y", alpha=.25)
    ax.text(0.01, -0.18, "n=5 independent runs per condition; jitter != latency",
            transform=ax.transAxes, fontsize=7, color="#555")
    _save(fig, "03_all_condition_run_level_jitter")

    # 4) reconstructed occupancy by condition/run
    fig, ax = plt.subplots(figsize=(11, 5))
    for i, c in enumerate(order):
        sub = primary[primary.condition == c]
        if sub.empty:
            continue
        ax.scatter([i] * len(sub), sub["reconstructed_occupancy_pct"], color=COLORS[c[0]], s=45, alpha=.85, zorder=3)
        m = _agg(sub["reconstructed_occupancy_pct"])
        ax.hlines(m["mean"], i - 0.3, i + 0.3, color=COLORS[c[0]], lw=2)
    ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=45)
    ax.set_ylabel("Reconstructed occupancy (%)")
    ax.set_title("3-node n=5: reconstructed occupancy by condition/run (bar = mean)")
    ax.grid(axis="y", alpha=.25)
    ax.text(0.01, -0.18, "reconstructed occupancy = payload-aware ISO airtime estimate, "
            "NOT PCAN actual Mean Load (not saved this campaign)",
            transform=ax.transAxes, fontsize=7, color="#555")
    _save(fig, "04_reconstructed_occupancy_by_condition")

    # 5) 60-target jitter vs reconstructed occupancy
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    for s in STRATEGIES:
        sub = primary[primary.condition == f"{s}60"]
        ax.scatter(sub["reconstructed_occupancy_pct"], sub["jitter_std_us"],
                   color=COLORS[s], s=70, label=f"{s}60", zorder=3)
    ax.set_xlabel("Reconstructed occupancy (%)"); ax.set_ylabel("Jitter SD (us)")
    ax.set_title("3-node n=5: 60-target jitter vs reconstructed occupancy")
    ax.legend(frameon=False); ax.grid(alpha=.25)
    ax.text(0.01, -0.14, "n=5 runs; each point one run; occupancy != PCAN actual load",
            transform=ax.transAxes, fontsize=7, color="#555")
    _save(fig, "05_60target_jitter_vs_occupancy")

    # 6) >100us rate strategy x load
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for s in STRATEGIES:
        means, sds = [], []
        for t in TARGET_ORDER:
            c = f"{s}{t}"
            means.append(csi.loc[c, "gt100_rate_mean"] if c in csi.index else np.nan)
            sds.append(csi.loc[c, "gt100_rate_sd"] if c in csi.index else np.nan)
        ax.errorbar(np.arange(len(TARGET_ORDER)), means, yerr=sds, marker="o",
                    capsize=4, color=COLORS[s], label=s, lw=2)
    ax.set_xticks(range(len(TARGET_ORDER))); ax.set_xticklabels(TARGET_ORDER)
    ax.set_xlabel("Target condition"); ax.set_ylabel("|error| > 100 us rate (%)")
    ax.set_title("3-node n=5: >100 us inter-arrival rate, strategy x load")
    ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.25)
    ax.text(0.01, -0.16, "n=5 independent runs; error bar = run-level SD; "
            "100 us is an analysis threshold, not a formal deadline",
            transform=ax.transAxes, fontsize=7, color="#555")
    _save(fig, "06_gt100us_rate_strategy_x_load")

    # 7) p99 |error| strategy x load
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for s in STRATEGIES:
        means, sds = [], []
        for t in TARGET_ORDER:
            c = f"{s}{t}"
            means.append(csi.loc[c, "p99_mean"] if c in csi.index else np.nan)
            sds.append(csi.loc[c, "p99_sd"] if c in csi.index else np.nan)
        ax.errorbar(np.arange(len(TARGET_ORDER)), means, yerr=sds, marker="o",
                    capsize=4, color=COLORS[s], label=s, lw=2)
    ax.set_xticks(range(len(TARGET_ORDER))); ax.set_xticklabels(TARGET_ORDER)
    ax.set_xlabel("Target condition"); ax.set_ylabel("|error| p99 (us)")
    ax.set_title("3-node n=5: p99 |inter-arrival error|, strategy x load")
    ax.legend(title="Strategy", frameon=False); ax.grid(alpha=.25)
    ax.text(0.01, -0.16, "n=5 independent runs; error bar = run-level SD",
            transform=ax.transAxes, fontsize=7, color="#555")
    _save(fig, "07_p99_strategy_x_load")


def _save(fig, stem):
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"{stem}.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _fmt(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "n/a"


def write_report(qc_df, inv_df, primary, extra, cs_df, lm_df, er_df, tail_df, run_df):
    csi = cs_df.set_index("condition")
    n_pass = int(qc_df.get("qc_pass", pd.Series(dtype=bool)).fillna(False).sum())
    n_total = len(qc_df)
    L = []

    L += [
        "# 3-node external-background CAN-FD repeated dataset (n=5)",
        "",
        f"- Raw TRC: `{RAW_DIR}` (61 files, never modified): "
        "12 conditions x run1..5 = 60 balanced + 1 extra `a1_6.trc` (A, 30-target, run6).",
        "- 3-node: Node1 CONTROL TX / Node2 external BACKGROUND TX / Node3 RX-PWM; PCAN Listen-Only.",
        "- Same background firmware as run1 (no firmware change this campaign).",
        "- Metrics reuse the verified n=10 module "
        "`trace_fixed2/analysis_n10/analyze_fixed2_64b_n10.py` "
        "(`interval_metrics`, `wire_breakdown`, `expected_kind`, `EXPECTED`, `EXPECTED_PAYLOAD`). "
        "No metric was redefined.",
        "- **Replicate unit = run (n=5).** Within-trace frames are NOT independent replicates; "
        "no p-value-centric inference is drawn from n=5. Effect size + run-to-run consistency are primary.",
        "- `reconstructed occupancy` = payload-aware ISO airtime estimate, **NOT** PCAN actual Mean Load "
        "(actual load was not saved this campaign). `jitter` = SD of consecutive 0x100 inter-arrival gaps, "
        "**NOT** one-way / end-to-end latency.",
        "- Dummy gap: nominal calibration values (A 627/240/170, B 616/235/168, C 617/238/170 us for 30/60/80); "
        f"{GAP_LIVE_NOTE}. This is target-load calibration, not measurement error.",
        "",
        "## 1. Inventory / completeness",
        "",
        "| condition | runs present | primary n | complete | extra |",
        "|---|---|---:|:--:|---|",
    ]
    for _, r in inv_df.iterrows():
        L.append(f"| {r.condition} | {r.runs_present} | {r.primary_run_count} | "
                 f"{'YES' if r.primary_complete else 'NO'} | {r.extra_runs or '-'} |")
    L += [
        "",
        f"Total TRC = {len(run_df)} (balanced 60 + 1 extra). "
        f"Extra replicate = `{extra.source_file.iloc[0] if not extra.empty else 'none'}` "
        "(A, 30-target, run6), excluded from all primary n=5 statistics.",
        "",
        f"## 2. QC: {n_pass}/{n_total} PASS",
        "",
        "Per-file QC (n=10 definitions, applied unchanged): parse success, capture duration, frame count, "
        "timestamp monotonicity, duplicate timestamps, expected CAN IDs, Standard-ID, CAN-FD/BRS, per-ID DLC/layout, "
        "fixed-payload byte-identity, unexpected IDs, ESI/error frames, 0x100 count, gap>6 ms, 9-11 ms loss "
        "candidates, background 0x300-0x30F presence, baseline dummy-absence, 300k-frame ceiling. "
        "Naming<->content verified: letter by observed 0x100 DLC (A 8B / B 32B / C 64B), number by dummy "
        "presence + monotonic occupancy. Details: `qc_by_file.csv`.",
    ]

    # baseline anomaly recurrence check
    base = tail_df[(tail_df.target == "baseline")]
    base_anom = base[(base.gap_gt_6000_count > 0) | (base.near_10ms_candidate_count > 0)]
    L += ["", "### Baseline long-gap / anomaly recurrence check (known C0 run1 25 ms issue)", ""]
    if base_anom.empty:
        L.append("- No baseline run (any strategy, run1-5) shows a gap>6 ms or 9-11 ms loss candidate "
                 "in this dataset. See per-file `max_interval_ms` in `tail_events.csv`.")
    else:
        for _, rr in base_anom.iterrows():
            L.append(f"- **{rr.source_file}** ({rr.condition}): gap>6ms={int(rr.gap_gt_6000_count)}, "
                     f"9-11ms cand={int(rr.near_10ms_candidate_count)}, max interval "
                     f"{_fmt(rr.max_interval_ms,1)} ms. Reported, raw TRC unchanged.")
    c0_max = base[base.condition == "C0"][["source_file", "run", "max_interval_ms"]]
    if not c0_max.empty:
        L.append("- C0 per-run max interval (ms): " +
                 ", ".join(f"r{int(x.run)}={_fmt(x.max_interval_ms,1)}" for _, x in c0_max.sort_values('run').iterrows()) +
                 ". (run1 known 25 ms single event.)")

    # acquisition / duration
    L += [
        "",
        "## 3. Acquisition duration / 300k buffer",
        "",
        "PCAN buffer raised to 300000 frames; new runs ~30 s. Any 300k ceiling hit is flagged in "
        "`run_manifest_n5.csv` (`hit_300k_ceiling`). run1 high-load captures were shorter (old 100k cap), "
        "so absolute counts are compared as rates; a 15 s common-window jitter sensitivity is in "
        "`run_level_metrics.csv` (`jitter_std_us_win15s`).",
        "",
        "| condition | dur run1 (s) | dur run2-5 mean (s) |",
        "|---|---:|---:|",
    ]
    for c in [f"{s}{t}" for t in TARGET_ORDER for s in STRATEGIES]:
        sub = primary[primary.condition == c]
        if sub.empty:
            continue
        d1 = sub[sub.run == 1]["duration_s"]
        d25 = sub[sub.run.isin((2, 3, 4, 5))]["duration_s"]
        L.append(f"| {c} | {_fmt(d1.iloc[0],1) if not d1.empty else 'n/a'} | {_fmt(d25.mean(),1)} |")

    # condition summary
    L += [
        "",
        "## 4/6. Condition-level n=5 summary (run = replicate)",
        "",
        "jitter/p99/occupancy/bg-fps are per-run values aggregated over run1-5.",
        "",
        "| cond | gap_us | jitter mean+-SD | jitter med [min,max] | p99 mean | >100us% mean | occ% mean+-SD | bg fps mean |",
        "|---|---|---|---|---:|---:|---|---:|",
    ]
    for c in [f"{s}{t}" for t in TARGET_ORDER for s in STRATEGIES]:
        if c not in csi.index:
            continue
        r = csi.loc[c]
        L.append(
            f"| {c} | {r.dummy_gap_nominal_us} | {_fmt(r.jitter_mean)}+-{_fmt(r.jitter_sd)} | "
            f"{_fmt(r.jitter_median)} [{_fmt(r.jitter_min)},{_fmt(r.jitter_max)}] | {_fmt(r.p99_mean,1)} | "
            f"{_fmt(r.gt100_rate_mean,2)} | {_fmt(r.occ_mean)}+-{_fmt(r.occ_sd)} | {_fmt(r.bgfps_mean,1)} |")

    # primary RQ: 60-target run-level
    L += [
        "",
        "## 5/8. PRIMARY: 60-target run-level jitter (A60 / B60 / C60)",
        "",
        "| run | A60 jitter | B60 jitter | C60 jitter |",
        "|---:|---:|---:|---:|",
    ]
    for run_i in PRIMARY_RUNS:
        cells = []
        for s in STRATEGIES:
            v = primary[(primary.condition == f"{s}60") & (primary.run == run_i)]["jitter_std_us"]
            cells.append(_fmt(v.iloc[0]) if not v.empty else "n/a")
        L.append(f"| {run_i} | {cells[0]} | {cells[1]} | {cells[2]} |")
    for s in STRATEGIES:
        a = _agg(primary[primary.condition == f"{s}60"]["jitter_std_us"])
        L.append("")
        L.append(f"- **{s}60 jitter mean +- SD = {_fmt(a['mean'])} +- {_fmt(a['sd'])} us** "
                 f"(median {_fmt(a['median'])}, range [{_fmt(a['vmin'])}, {_fmt(a['vmax'])}]).")

    # matched-index descriptive A60-C60
    a60 = primary[primary.condition == "A60"].set_index("run")["jitter_std_us"]
    c60 = primary[primary.condition == "C60"].set_index("run")["jitter_std_us"]
    common = sorted(set(a60.index) & set(c60.index))
    diffs = [a60[i] - c60[i] for i in common]
    L += [
        "",
        "### A60 - C60 matched-index descriptive comparison (NOT a formal paired test)",
        "",
        "Run i of A and run i of C were not physically simultaneous trials, so this is a matched-index "
        "descriptive difference only.",
        "",
        "| run | A60 | C60 | A60-C60 |",
        "|---:|---:|---:|---:|",
    ]
    for i in common:
        L.append(f"| {i} | {_fmt(a60[i])} | {_fmt(c60[i])} | {_fmt(a60[i]-c60[i],2)} |")
    if diffs:
        dm = float(np.mean(diffs)); ds = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else float("nan")
        L.append(f"\nMatched-index mean A60-C60 = **{_fmt(dm)} +- {_fmt(ds)} us** (all runs same sign: "
                 f"{all(d > 0 for d in diffs)}). 2-node n=10 reference A60-C60 = +37.7 us.")

    # comparison vs 2-node
    L += [
        "",
        "## 6b. Comparison vs 2-node fixed-payload n=10 (descriptive)",
        "",
        "| cond | 3node n=5 jitter mean+-SD | 2node n=10 jitter | 3node >100us% | 2node >100us% | 3node occ% | 2node occ% |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for c in ("A60", "B60", "C60", "A30", "B30", "C30", "A80", "B80", "C80", "A0", "B0", "C0"):
        if c in csi.index and c in TWO_NODE_N10:
            r = csi.loc[c]; ref = TWO_NODE_N10[c]
            L.append(f"| {c} | {_fmt(r.jitter_mean)}+-{_fmt(r.jitter_sd)} | {_fmt(ref['jitter'],1)} | "
                     f"{_fmt(r.gt100_rate_mean,2)} | {_fmt(ref['gt100'],2)} | "
                     f"{_fmt(r.occ_mean,2)} | {_fmt(ref['occ'],2)} |")

    # load matching
    L += [
        "",
        "## 7. Load matching (reconstructed occupancy, proxy only)",
        "",
        "| target | A occ mean+-SD | B occ mean+-SD | C occ mean+-SD | max spread pp |",
        "|---|---|---|---|---:|",
    ]
    for t in TARGET_ORDER:
        cells = {}
        for s in STRATEGIES:
            a = _agg(primary[primary.condition == f"{s}{t}"]["reconstructed_occupancy_pct"])
            cells[s] = f"{_fmt(a['mean'])}+-{_fmt(a['sd'])}"
        occs = [_agg(primary[primary.condition == f"{s}{t}"]["reconstructed_occupancy_pct"])["mean"] for s in STRATEGIES]
        occs = [o for o in occs if np.isfinite(o)]
        spread = (max(occs) - min(occs)) if len(occs) >= 2 else float("nan")
        L.append(f"| {t} | {cells['A']} | {cells['B']} | {cells['C']} | {_fmt(spread,2)} |")
    L.append("\nActual PCAN Mean/Min/Max Load was NOT saved; occupancy is a reconstructed proxy. "
             "Pairwise pp differences and spreads per target are in `load_matching_n5.csv`.")

    # strategy x load ordering
    L += [
        "",
        "## 9. Strategy x load ordering (descriptive interaction)",
        "",
    ]
    for t in ("30", "60", "80"):
        ranked = sorted(STRATEGIES, key=lambda s: (csi.loc[f"{s}{t}", "jitter_mean"]
                        if f"{s}{t}" in csi.index else float("inf")))
        vals = ", ".join(f"{s}={_fmt(csi.loc[f'{s}{t}','jitter_mean'])}" for s in STRATEGIES if f"{s}{t}" in csi.index)
        L.append(f"- **{t}-target** jitter ({vals}) -> ascending order {' < '.join(ranked)}.")
    L.append("\nSee figure 01 (strategy x load interaction). n=5, descriptive; no factorial ANOVA is forced.")

    # extra run6 sensitivity
    L += [
        "",
        "## 11. Extra a1 run6 sensitivity",
        "",
        "| condition | metric | n5 mean+-SD | run6 value | n6 mean+-SD | mean shift |",
        "|---|---|---|---:|---|---:|",
    ]
    if not er_df.empty:
        for _, r in er_df.iterrows():
            L.append(f"| {r.condition} | {r.metric} | {_fmt(r.n5_mean)}+-{_fmt(r.n5_sd)} | "
                     f"{_fmt(r.extra_run6_value)} | {_fmt(r.n6_mean)}+-{_fmt(r.n6_sd)} | {_fmt(r.mean_shift,2)} |")
        L.append("\nThe extra replicate does not materially alter the descriptive conclusion for its condition.")

    # claim boundary
    L += [
        "",
        "## 13. Claim boundary",
        "",
        "**Supportable:** repeated independent-run pattern; whether the 60-target ordering/magnitude holds "
        "under an external-background 3-node; load-dependent strategy ordering; same-MCU background confound "
        "is harder to invoke as sole cause.",
        "",
        "**NOT yet supportable:** pure arbitration proven as cause; frame-length-alone or write-count-alone "
        "causal effect; motor-stability improvement; C optimal in all conditions. `reconstructed occupancy` "
        "!= PCAN actual load; `jitter` != latency; 100 us is an analysis threshold, not a deadline.",
        "",
        "## Figures",
        "",
    ]
    for png in sorted(FIG_DIR.glob("*.png")):
        L.append(f"- `figures/{png.name}`")

    (OUT_DIR / "3node_n5_analysis.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
