#!/usr/bin/env python3
"""Final n=10 audit and run-level analysis for the fixed-payload CAN-FD TRCs.

This program never modifies input traces.  It audits the complete 3 x 4 x 10
design, reproduces the legacy n=3 definitions, and reports an ISO-corrected
payload-aware occupancy estimate separately from PCAN actual load (unavailable
unless explicitly present in trace metadata).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import logging
import math
import os
import platform
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy import stats


SCRIPT_VERSION = "1.0.0"
SEED = 20260721
BOOTSTRAP_ITERATIONS = 20_000
NOMINAL_PERIOD_US = 5_000
LOAD_LABEL = {0: "baseline", 1: "30", 2: "60", 3: "80"}
LOAD_VALUE = {0: 0.0, 1: 30.0, 2: 60.0, 3: 80.0}
STRATEGIES = ("A", "B", "C")
MODES = (0, 1, 2, 3)
RUNS = tuple(range(1, 11))
WIRE_DLC = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8,
            12: 9, 16: 10, 20: 11, 24: 12, 32: 13, 48: 14, 64: 15}
LOOKUP_AIRTIME_US = {8: 109.3, 12: 125.6, 16: 141.9, 32: 209.8, 64: 340.4}
LOOKUP_NOMINAL_BPS = 497_500.0
LOOKUP_DATA_BPS = 1_960_000.0
FILENAME_RE = re.compile(r"^(a|b|c)([0-3])_(0?[1-9]|10)_fixed2\.trc$", re.I)
TRC2_RE = re.compile(
    r"^\s*(?P<num>\d+)\s+(?P<time>[0-9]+(?:\.[0-9]+)?)\s+"
    r"(?P<type>\S+)\s+(?P<id>[0-9A-Fa-f]+)\s+(?P<direction>Rx|Tx)\s+"
    r"(?P<length>\d+)\s*(?P<data>.*)$", re.I)
BIT_RATE_RE = re.compile(
    r"Nominal\s+(?P<n>[0-9.]+)\s*(?P<nu>[kKmM]?)Bit/s,\s*"
    r"Data\s+(?P<d>[0-9.]+)\s*(?P<du>[kKmM]?)Bit/s", re.I)

EXPECTED: dict[str, dict[int, tuple[int, int]]] = {
    "A": {0x100: (8, 5_000), 0x101: (8, 5_000), 0x102: (16, 5_000),
          0x110: (8, 50_000), 0x120: (8, 50_000), 0x130: (16, 50_000)},
    "B": {0x100: (32, 5_000), 0x110: (32, 50_000)},
    "C": {0x100: (64, 5_000)},
}
EXPECTED_PAYLOAD_HEX = {
    "A": {
        0x100: "F4 01 01 02 2C 01 00 A5",
        0x101: "88 FF FA 00 E8 03 EE 02",
        0x102: "E0 01 E2 01 DF 01 E1 01 E7 FF 64 00 D8 FF AA 55",
        0x110: "34 12 41 00 E4 0C 00 00",
        0x120: "E8 03 C8 00 32 00 20 03",
        0x130: "44 33 22 11 88 77 66 55 D4 C3 B2 A1 3C 2D 1E 0F",
    },
    "B": {
        0x100: "F4 01 01 02 2C 01 00 A5 88 FF FA 00 E8 03 EE 02 "
               "E0 01 E2 01 DF 01 E1 01 E7 FF 64 00 D8 FF AA 55",
        0x110: "34 12 41 00 E4 0C 00 00 E8 03 C8 00 32 00 20 03 "
               "44 33 22 11 88 77 66 55 D4 C3 B2 A1 3C 2D 1E 0F",
    },
    "C": {
        0x100: "F4 01 01 02 2C 01 00 A5 88 FF FA 00 E8 03 EE 02 "
               "E0 01 E2 01 DF 01 E1 01 E7 FF 64 00 D8 FF AA 55 "
               "34 12 41 00 E4 0C 00 00 E8 03 C8 00 32 00 20 03 "
               "44 33 22 11 88 77 66 55 D4 C3 B2 A1 3C 2D 1E 0F",
    },
}
EXPECTED_PAYLOAD = {
    s: {i: bytes.fromhex(v) for i, v in ids.items()}
    for s, ids in EXPECTED_PAYLOAD_HEX.items()
}
COLORS = {"A": "#0072B2", "B": "#D55E00", "C": "#009E73"}


@dataclass(frozen=True, slots=True)
class FileKey:
    source_file: str
    strategy: str
    mode: int
    load: str
    run: int


@dataclass(slots=True)
class Frame:
    timestamp_us: int
    can_id: int
    length: int
    payload: bytes
    is_fd: bool
    brs: bool
    esi: bool
    direction: str
    type_token: str
    line_number: int


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--bootstrap", type=int, default=BOOTSTRAP_ITERATIONS)
    p.add_argument("--seed", type=int, default=SEED)
    return p.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def parse_key(path: Path) -> FileKey | None:
    m = FILENAME_RE.fullmatch(path.name)
    if not m:
        return None
    mode = int(m.group(2))
    return FileKey(path.name, m.group(1).upper(), mode, LOAD_LABEL[mode], int(m.group(3)))


def rate_bps(value: str, unit: str) -> float:
    return float(value) * {"": 1.0, "k": 1_000.0, "m": 1_000_000.0}[unit.lower()]


def bits(value: int, width: int) -> list[int]:
    return [(value >> shift) & 1 for shift in range(width - 1, -1, -1)]


def dynamic_stuff_counts(tagged: Sequence[tuple[int, str]]) -> tuple[int, int]:
    """Count ISO CAN-FD dynamic stuff bits from SOF through the data field."""
    previous: int | None = None
    run = 0
    n_nominal = 0
    n_data = 0
    for bit, phase in tagged:
        if previous is not None and run == 5:
            stuff = 1 - previous
            if phase == "nominal":
                n_nominal += 1
            else:
                n_data += 1
            previous, run = stuff, 1
        if bit == previous:
            run += 1
        else:
            previous, run = bit, 1
    return n_nominal, n_data


def wire_breakdown(can_id: int, payload: bytes, esi: bool,
                   nominal_bps: float, data_bps: float,
                   legacy: bool = False) -> dict[str, float | int]:
    """Return a Standard-ID BRS ISO CAN-FD frame breakdown including intermission.

    ISO CRC fields contain 4 stuff-count/parity bits, CRC-17/21, and 6/7 fixed
    stuff bits respectively.  ``legacy=True`` reproduces the prior 5/6 fixed-bit
    implementation so the pre-specified n=3 audit can be compared exactly.
    """
    dlc = WIRE_DLC[len(payload)]
    nominal_tagged = ([(0, "nominal")]
                      + [(b, "nominal") for b in bits(can_id, 11)]
                      + [(0, "nominal"), (0, "nominal"), (1, "nominal"),
                         (0, "nominal"), (1, "nominal")])
    data_tagged = [(1 if esi else 0, "data")]
    data_tagged += [(b, "data") for b in bits(dlc, 4)]
    for byte in payload:
        data_tagged += [(b, "data") for b in bits(byte, 8)]
    dyn_nom, dyn_data = dynamic_stuff_counts(nominal_tagged + data_tagged)
    crc_width = 17 if len(payload) <= 16 else 21
    fixed = (5 if crc_width == 17 else 6) if legacy else (6 if crc_width == 17 else 7)
    base_nominal = 30  # SOF..BRS (17), CRC delimiter..intermission (13)
    base_data = 5 + 8 * len(payload) + 5 + crc_width  # ESI+DLC, data, count/parity, CRC
    nominal_bits = base_nominal + dyn_nom
    data_bits = base_data + dyn_data + fixed
    transmitted = nominal_bits + data_bits
    airtime_us = 1e6 * (nominal_bits / nominal_bps + data_bits / data_bps)
    return {
        "base_bits": base_nominal + base_data,
        "dynamic_nominal_stuff_bits": dyn_nom,
        "dynamic_data_stuff_bits": dyn_data,
        "dynamic_stuff_bits": dyn_nom + dyn_data,
        "fixed_stuff_bits": fixed,
        "crc_width_bits": crc_width,
        "nominal_rate_bits": nominal_bits,
        "data_rate_bits": data_bits,
        "total_transmitted_bits": transmitted,
        "total_wire_equivalent_bits": nominal_bits + data_bits * nominal_bps / data_bps,
        "estimated_airtime_us": airtime_us,
    }


def nominal_no_dynamic_airtime(length: int, nominal_bps: float, data_bps: float) -> float:
    crc = 17 if length <= 16 else 21
    fixed = 6 if crc == 17 else 7
    return 1e6 * (30 / nominal_bps + (5 + 8 * length + 5 + crc + fixed) / data_bps)


def excel_serial_to_datetime(value: str) -> datetime | None:
    try:
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    except Exception:
        return None


def expected_kind(strategy: str, can_id: int) -> tuple[str, int | None, int | None]:
    if can_id in EXPECTED[strategy]:
        length, period = EXPECTED[strategy][can_id]
        return "signal", length, period
    if 0x300 <= can_id <= 0x30F:
        return "dummy", 12, None
    return "unexpected", None, None


def describe_metric(values: Sequence[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {k: np.nan for k in ("mean", "sample_sd", "median", "q1", "q3", "iqr", "min", "max")}
    q1, q3 = np.percentile(a, [25, 75])
    return {"mean": float(a.mean()), "sample_sd": float(a.std(ddof=1)) if len(a) > 1 else np.nan,
            "median": float(np.median(a)), "q1": float(q1), "q3": float(q3),
            "iqr": float(q3 - q1), "min": float(a.min()), "max": float(a.max())}


def interval_metrics(timestamps: np.ndarray, capture_duration_s: float,
                     warmup_us: int = 0) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    keep = timestamps >= timestamps[0] + warmup_us if len(timestamps) else np.array([], dtype=bool)
    ts = timestamps[keep]
    gaps = np.diff(ts).astype(float)
    errors = gaps - NOMINAL_PERIOD_US
    abs_e = np.abs(errors)
    observation_s = (ts[-1] - ts[0]) / 1e6 if len(ts) > 1 else 0.0
    q = lambda x: float(np.percentile(abs_e, x)) if len(abs_e) else np.nan
    row = {
        "number_0x100_frames": int(len(ts)), "number_intervals": int(len(gaps)),
        "observation_duration_s": observation_s, "capture_duration_s": capture_duration_s,
        "fps_0x100": float(len(ts) / observation_s) if observation_s > 0 else np.nan,
        "mean_gap_us": float(gaps.mean()) if len(gaps) else np.nan,
        "median_gap_us": float(np.median(gaps)) if len(gaps) else np.nan,
        "jitter_std_us": float(gaps.std(ddof=1)) if len(gaps) > 1 else np.nan,
        "mean_error_us": float(errors.mean()) if len(errors) else np.nan,
        "median_error_us": float(np.median(errors)) if len(errors) else np.nan,
        "abs_error_mean_us": float(abs_e.mean()) if len(abs_e) else np.nan,
        "abs_error_median_us": q(50), "abs_error_p90_us": q(90),
        "abs_error_p95_us": q(95), "abs_error_p99_us": q(99),
        "abs_error_max_us": float(abs_e.max()) if len(abs_e) else np.nan,
        "min_gap_us": float(gaps.min()) if len(gaps) else np.nan,
        "max_gap_us": float(gaps.max()) if len(gaps) else np.nan,
        "gap_gt_6000_count": int(np.sum(gaps > 6000)),
        "gap_lt_4000_count": int(np.sum(gaps < 4000)),
        "duplicate_zero_negative_gap_count": int(np.sum(gaps <= 0)),
        "update_gap_violation_candidate_count": int(np.sum(gaps > 6000)),
        "frame_loss_candidate_count": int(np.sum(gaps >= 7500)),
        "near_10ms_frame_loss_candidate_count": int(np.sum((gaps >= 9000) & (gaps <= 11000))),
    }
    for t in (50, 100, 200):
        row[f"abs_error_gt_{t}us_count"] = int(np.sum(abs_e > t))
        row[f"abs_error_gt_{t}us_rate"] = float(np.mean(abs_e > t)) if len(abs_e) else np.nan
    return row, gaps, errors


def parse_trace(path: Path, key: FileKey, interval_writer: csv.DictWriter) -> dict[str, Any]:
    frames: list[Frame] = []
    header: dict[str, Any] = {"trc_version": "", "start_time_raw": "", "start_time_text": "",
                              "nominal_bit_rate_bps": np.nan, "data_bit_rate_bps": np.nan}
    parse_errors: list[dict[str, Any]] = []
    header_drop_error_lines: list[str] = []
    with path.open("r", encoding="cp1252", errors="replace") as f:
        for line_number, raw in enumerate(f, 1):
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith(";"):
                upper = stripped.upper()
                if upper.startswith(";$FILEVERSION="):
                    header["trc_version"] = stripped.split("=", 1)[1].strip()
                elif upper.startswith(";$STARTTIME="):
                    header["start_time_raw"] = stripped.split("=", 1)[1].strip()
                elif "START TIME:" in upper:
                    header["start_time_text"] = stripped.split(":", 1)[1].strip()
                m = BIT_RATE_RE.search(stripped)
                if m:
                    header["nominal_bit_rate_bps"] = rate_bps(m.group("n"), m.group("nu"))
                    header["data_bit_rate_bps"] = rate_bps(m.group("d"), m.group("du"))
                if re.search(r"\b(drop|dropped|error|overrun)\b", stripped, re.I):
                    header_drop_error_lines.append(stripped)
                continue
            m = TRC2_RE.match(raw)
            if not m:
                parse_errors.append({"source_file": path.name, "line_number": line_number,
                                     "error_reason": "unrecognized_or_status_row", "raw_line": stripped})
                continue
            try:
                length = int(m.group("length"))
                payload = bytes(int(x, 16) for x in m.group("data").split())
                if len(payload) != length:
                    raise ValueError(f"payload_count_{len(payload)}_vs_length_{length}")
                token = m.group("type").upper()
                is_fd = token.startswith("F") or "FD" in token
                frames.append(Frame(int(round(float(m.group("time")) * 1000)),
                                    int(m.group("id"), 16), length, payload, is_fd,
                                    is_fd and "B" in token, is_fd and "E" in token,
                                    m.group("direction").title(), token, line_number))
            except Exception as exc:
                parse_errors.append({"source_file": path.name, "line_number": line_number,
                                     "error_reason": str(exc), "raw_line": stripped})
    if not frames:
        return {"frames": frames, "header": header, "parse_errors": parse_errors,
                "header_drop_error_lines": header_drop_error_lines}
    ts100 = np.asarray([f.timestamp_us for f in frames if f.can_id == 0x100], dtype=np.int64)
    for warmup, label in ((0, "full"), (1_000_000, "exclude_first_1s")):
        if len(ts100):
            ts = ts100[ts100 >= ts100[0] + warmup]
            for i in range(1, len(ts)):
                gap = int(ts[i] - ts[i - 1])
                err = gap - NOMINAL_PERIOD_US
                interval_writer.writerow({"source_file": key.source_file, "strategy": key.strategy,
                                           "load_mode": key.mode, "load_pct_label": key.load,
                                           "run": key.run, "analysis_window": label,
                                           "timestamp_us": int(ts[i]), "gap_us": gap,
                                           "error_us": err, "abs_error_us": abs(err)})
    return {"frames": frames, "header": header, "parse_errors": parse_errors,
            "header_drop_error_lines": header_drop_error_lines}


def base_meta(key: FileKey) -> dict[str, Any]:
    return {"source_file": key.source_file, "strategy": key.strategy,
            "load_mode": key.mode, "load_pct_label": key.load, "run": key.run}


def analyze_dataset(input_dir: Path, output_dir: Path) -> dict[str, pd.DataFrame]:
    trc_files = sorted(input_dir.glob("*.trc"), key=lambda p: p.name.lower())
    inventory_rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    by_combo: dict[tuple[str, int, int], list[Path]] = defaultdict(list)
    for p in trc_files:
        key = parse_key(p)
        row = {"source_file": p.name, "file_size_bytes": p.stat().st_size,
               "sha256": sha256_file(p), "filename_valid": key is not None,
               "strategy": key.strategy if key else "", "load_mode": key.mode if key else np.nan,
               "load_pct_label": key.load if key else "", "run": key.run if key else np.nan,
               "inventory_status": "present" if key else "filename_mismatch"}
        inventory_rows.append(row)
        if key:
            by_combo[(key.strategy, key.mode, key.run)].append(p)
        else:
            failures.append({"severity": "fatal", "source_file": p.name,
                             "failure_type": "filename_mismatch", "detail": p.name})
        if p.stat().st_size == 0:
            failures.append({"severity": "fatal", "source_file": p.name,
                             "failure_type": "empty_file", "detail": "0 bytes"})
    for combo in itertools.product(STRATEGIES, MODES, RUNS):
        paths = by_combo.get(combo, [])
        if len(paths) != 1:
            failures.append({"severity": "fatal", "source_file": "|".join(p.name for p in paths),
                             "failure_type": "missing_combination" if not paths else "duplicate_combination",
                             "detail": f"strategy={combo[0]}, mode={combo[1]}, run={combo[2]}, count={len(paths)}"})

    interval_path = output_dir / "interval_level_0x100.csv.gz"
    interval_columns = ["source_file", "strategy", "load_mode", "load_pct_label", "run",
                        "analysis_window", "timestamp_us", "gap_us", "error_us", "abs_error_us"]
    run_rows: list[dict[str, Any]] = []
    layout_rows: list[dict[str, Any]] = []
    payload_rows: list[dict[str, Any]] = []
    payload_failures: list[dict[str, Any]] = []
    occupancy_breakdown: list[dict[str, Any]] = []
    occupancy_run_rows: list[dict[str, Any]] = []
    tail_rows: list[dict[str, Any]] = []
    parse_error_rows: list[dict[str, Any]] = []
    measurement_rows: list[dict[str, Any]] = []
    qc_id_rows: list[dict[str, Any]] = []
    cached_intervals: list[dict[str, Any]] = []

    with gzip.open(interval_path, "wt", newline="", encoding="utf-8") as interval_handle:
        interval_writer = csv.DictWriter(interval_handle, fieldnames=interval_columns)
        interval_writer.writeheader()
        for p in trc_files:
            key = parse_key(p)
            if key is None or p.stat().st_size == 0:
                continue
            logging.info("Parsing %s", p.name)
            result = parse_trace(p, key, interval_writer)
            frames: list[Frame] = result["frames"]
            header = result["header"]
            parse_error_rows.extend(result["parse_errors"])
            meta = base_meta(key)
            if result["parse_errors"]:
                failures.append({"severity": "fatal", "source_file": p.name,
                                 "failure_type": "parse_error", "detail": f"{len(result['parse_errors'])} rows"})
            if not frames:
                failures.append({"severity": "fatal", "source_file": p.name,
                                 "failure_type": "no_parsed_frames", "detail": "zero data frames"})
                continue
            ts = np.asarray([f.timestamp_us for f in frames], dtype=np.int64)
            capture_duration_s = (ts[-1] - ts[0]) / 1e6
            start_dt = excel_serial_to_datetime(header["start_time_raw"])
            measurement_rows.append({**meta, "trc_start_time_raw": header["start_time_raw"],
                                     "trc_start_datetime": start_dt.isoformat(sep=" ") if start_dt else "",
                                     "header_start_time_text": header["start_time_text"],
                                     "file_last_write_time": datetime.fromtimestamp(p.stat().st_mtime).isoformat(sep=" "),
                                     "capture_duration_s": capture_duration_s})
            backwards = int(np.sum(np.diff(ts) < 0))
            duplicates = int(np.sum(np.diff(ts) == 0))
            if backwards:
                failures.append({"severity": "fatal", "source_file": p.name,
                                 "failure_type": "timestamp_nonmonotonic", "detail": str(backwards)})
            if duplicates:
                failures.append({"severity": "warning", "source_file": p.name,
                                 "failure_type": "duplicate_frame_timestamps", "detail": str(duplicates)})

            nominal_bps = float(header["nominal_bit_rate_bps"])
            data_bps = float(header["data_bit_rate_bps"])
            if not (np.isfinite(nominal_bps) and np.isfinite(data_bps)):
                failures.append({"severity": "fatal", "source_file": p.name,
                                 "failure_type": "missing_bitrate_header", "detail": str(header)})
                nominal_bps, data_bps = LOOKUP_NOMINAL_BPS, LOOKUP_DATA_BPS
            groups: dict[int, list[Frame]] = defaultdict(list)
            for frame in frames:
                groups[frame.can_id].append(frame)
            observed = set(groups)
            missing_ids = set(EXPECTED[key.strategy]) - observed
            if missing_ids:
                failures.append({"severity": "fatal", "source_file": p.name,
                                 "failure_type": "missing_expected_id",
                                 "detail": "|".join(f"0x{x:03X}" for x in sorted(missing_ids))})

            total_corrected_airtime = 0.0
            total_legacy_airtime = 0.0
            total_lookup_airtime = 0.0
            total_header_nominal_airtime = 0.0
            for can_id, group in sorted(groups.items()):
                kind, expected_len, period_us = expected_kind(key.strategy, can_id)
                lengths = sorted(set(f.length for f in group))
                payload_counter = Counter(f.payload for f in group)
                hashes = sorted(hashlib.sha256(payload).hexdigest().upper() for payload in payload_counter)
                is_fd_all = all(f.is_fd for f in group)
                brs_all = all(f.brs for f in group)
                esi_count = sum(f.esi for f in group)
                direction_values = "|".join(sorted(set(f.direction for f in group)))
                duration = capture_duration_s if capture_duration_s > 0 else np.nan
                fps = len(group) / duration if np.isfinite(duration) else np.nan
                expected_payload = EXPECTED_PAYLOAD[key.strategy].get(can_id)
                expected_payload_match = (len(payload_counter) == 1 and next(iter(payload_counter)) == expected_payload
                                          if expected_payload is not None else np.nan)
                layout_ok = (kind != "unexpected" and len(lengths) == 1 and
                             (expected_len is None or lengths[0] == expected_len) and
                             is_fd_all and brs_all and esi_count == 0)
                layout_rows.append({**meta, "can_id_hex": f"0x{can_id:03X}", "frame_kind": kind,
                                    "expected_length_bytes": expected_len, "observed_lengths_bytes": "|".join(map(str, lengths)),
                                    "frame_count": len(group), "fps": fps, "expected_period_us": period_us,
                                    "is_fd_all": is_fd_all, "brs_all": brs_all, "esi_count": esi_count,
                                    "direction_values": direction_values, "layout_ok": layout_ok})
                qc_id_rows.append({**meta, "can_id_hex": f"0x{can_id:03X}", "frame_kind": kind,
                                   "frame_count": len(group), "fps": fps, "unique_payload_count": len(payload_counter),
                                   "unique_length_count": len(lengths), "is_fd_all": is_fd_all,
                                   "brs_all": brs_all, "esi_count": esi_count})
                payload_rows.append({**meta, "can_id_hex": f"0x{can_id:03X}", "frame_kind": kind,
                                     "frame_count": len(group), "unique_payload_count": len(payload_counter),
                                     "payload_sha256": "|".join(hashes),
                                     "representative_payload_hex": next(iter(payload_counter)).hex(" ").upper(),
                                     "within_run_byte_identical": len(payload_counter) == 1,
                                     "matches_defined_signal_payload": expected_payload_match})
                if not layout_ok:
                    failures.append({"severity": "fatal", "source_file": p.name,
                                     "failure_type": "frame_layout_violation",
                                     "detail": f"id=0x{can_id:03X}, kind={kind}, lengths={lengths}, FD={is_fd_all}, BRS={brs_all}, ESI={esi_count}"})
                if len(payload_counter) != 1 or expected_payload_match is False:
                    payload_failures.append({**meta, "can_id_hex": f"0x{can_id:03X}",
                                             "failure_type": "within_run_payload_change" if len(payload_counter) != 1 else "defined_signal_payload_mismatch",
                                             "unique_payload_count": len(payload_counter), "payload_sha256": "|".join(hashes)})

                for payload, count in sorted(payload_counter.items(), key=lambda x: x[0]):
                    sample = next(f for f in group if f.payload == payload)
                    corr = wire_breakdown(can_id, payload, sample.esi, nominal_bps, data_bps, legacy=False)
                    legacy = wire_breakdown(can_id, payload, sample.esi, nominal_bps, data_bps, legacy=True)
                    lookup = LOOKUP_AIRTIME_US.get(len(payload), np.nan)
                    header_nominal = nominal_no_dynamic_airtime(len(payload), nominal_bps, data_bps)
                    total_corrected_airtime += float(corr["estimated_airtime_us"]) * count
                    total_legacy_airtime += float(legacy["estimated_airtime_us"]) * count
                    total_lookup_airtime += lookup * count
                    total_header_nominal_airtime += header_nominal * count
                    occupancy_breakdown.append({**meta, "can_id_hex": f"0x{can_id:03X}", "frame_kind": kind,
                                                "payload_sha256": hashlib.sha256(payload).hexdigest().upper(),
                                                "payload_hex": payload.hex(" ").upper(), "data_length_bytes": len(payload),
                                                "frame_count": count, **corr,
                                                "legacy_fixed_stuff_bits": legacy["fixed_stuff_bits"],
                                                "legacy_estimated_airtime_us_per_frame": legacy["estimated_airtime_us"],
                                                "nominal_lookup_airtime_us_per_frame": lookup,
                                                "header_rate_no_dynamic_airtime_us_per_frame": header_nominal,
                                                "occupancy_contribution_pct": float(corr["estimated_airtime_us"]) * count / (capture_duration_s * 1e6) * 100,
                                                "legacy_occupancy_contribution_pct": float(legacy["estimated_airtime_us"]) * count / (capture_duration_s * 1e6) * 100})
            occupancy_run_rows.append({**meta, "capture_duration_s": capture_duration_s,
                                       "nominal_bit_rate_bps": nominal_bps, "data_bit_rate_bps": data_bps,
                                       "pcan_actual_mean_load_pct": np.nan, "pcan_actual_min_load_pct": np.nan,
                                       "pcan_actual_max_load_pct": np.nan, "pcan_actual_load_status": "unavailable_in_trc_header",
                                       "nominal_lookup_occupancy_pct": total_lookup_airtime / (capture_duration_s * 1e6) * 100,
                                       "header_rate_no_dynamic_occupancy_pct": total_header_nominal_airtime / (capture_duration_s * 1e6) * 100,
                                       "legacy_reconstructed_occupancy_pct": total_legacy_airtime / (capture_duration_s * 1e6) * 100,
                                       "reconstructed_occupancy_pct": total_corrected_airtime / (capture_duration_s * 1e6) * 100,
                                       "iso_correction_minus_legacy_pp": (total_corrected_airtime - total_legacy_airtime) / (capture_duration_s * 1e6) * 100,
                                       "lookup_rate_difference_pp": (total_header_nominal_airtime - total_lookup_airtime) / (capture_duration_s * 1e6) * 100})

            ts100 = np.asarray([f.timestamp_us for f in frames if f.can_id == 0x100], dtype=np.int64)
            for warmup, label in ((0, "full"), (1_000_000, "exclude_first_1s")):
                metrics, gaps, errors = interval_metrics(ts100, capture_duration_s, warmup)
                run_rows.append({**meta, "analysis_window": label, **metrics})
                if label == "full":
                    cached_intervals.extend({**meta, "error_us": float(e), "abs_error_us": abs(float(e))} for e in errors)
            if len(ts100):
                index100 = [i for i, f in enumerate(frames) if f.can_id == 0x100]
                for j in range(1, len(index100)):
                    current_idx = index100[j]
                    gap = frames[current_idx].timestamp_us - frames[index100[j - 1]].timestamp_us
                    error = gap - NOMINAL_PERIOD_US
                    if abs(error) <= 50:
                        continue
                    previous = frames[current_idx - 1] if current_idx > 0 else None
                    if previous:
                        pb = wire_breakdown(previous.can_id, previous.payload, previous.esi,
                                            nominal_bps, data_bps, legacy=False)
                    else:
                        pb = {"estimated_airtime_us": np.nan}
                    tail_rows.append({**meta, "event_timestamp_us": frames[current_idx].timestamp_us,
                                      "gap_us": gap, "inter_arrival_error_us": error,
                                      "abs_error_us": abs(error), "abs_error_gt_50us": abs(error) > 50,
                                      "abs_error_gt_100us": abs(error) > 100,
                                      "abs_error_gt_200us": abs(error) > 200,
                                      "preceding_frame_id_hex": f"0x{previous.can_id:03X}" if previous else "",
                                      "preceding_frame_kind": expected_kind(key.strategy, previous.can_id)[0] if previous else "",
                                      "preceding_frame_dlc_bytes": previous.length if previous else np.nan,
                                      "preceding_frame_reconstructed_airtime_us": pb["estimated_airtime_us"],
                                      "timestamp_separation_from_preceding_frame_us": frames[current_idx].timestamp_us - previous.timestamp_us if previous else np.nan,
                                      "timestamp_semantics": "PCAN-View Rx offset; SOF versus completion not established",
                                      "interpretation_scope": "exploratory association; not causal blocking proof"})

            inv = next(r for r in inventory_rows if r["source_file"] == p.name)
            inv.update({"parse_success": True, "parsed_frame_count": len(frames),
                        "parse_error_count": len(result["parse_errors"]),
                        "first_timestamp_us": int(ts[0]), "last_timestamp_us": int(ts[-1]),
                        "capture_duration_s": capture_duration_s,
                        "timestamp_backwards_count": backwards, "timestamp_duplicate_count": duplicates,
                        "trc_version": header["trc_version"], "trc_start_time_raw": header["start_time_raw"],
                        "trc_start_time_text": header["start_time_text"],
                        "nominal_bit_rate_bps": header["nominal_bit_rate_bps"],
                        "data_bit_rate_bps": header["data_bit_rate_bps"],
                        "fd_frame_count": sum(f.is_fd for f in frames),
                        "brs_frame_count": sum(f.brs for f in frames), "esi_frame_count": sum(f.esi for f in frames),
                        "header_drop_error_record_count": len(result["header_drop_error_lines"]),
                        "observed_id_count": len(groups), "observed_ids_hex": "|".join(f"0x{x:03X}" for x in sorted(groups)),
                        "frame_0x100_count": len(ts100),
                        "fps_0x100": len(ts100) / capture_duration_s if capture_duration_s > 0 else np.nan})

    inventory = pd.DataFrame(inventory_rows)
    payload_df = pd.DataFrame(payload_rows)
    if not payload_df.empty:
        for (strategy, load, can_id), g in payload_df.groupby(["strategy", "load_mode", "can_id_hex"]):
            if g["payload_sha256"].nunique() > 1:
                payload_failures.append({"source_file": "|".join(g.source_file), "strategy": strategy,
                                         "load_mode": load, "load_pct_label": LOAD_LABEL[int(load)], "run": "all",
                                         "can_id_hex": can_id, "failure_type": "between_run_payload_change_same_condition",
                                         "unique_payload_count": g["payload_sha256"].nunique(),
                                         "payload_sha256": "|".join(sorted(g["payload_sha256"].unique()))})
        signal_payloads = payload_df[payload_df.frame_kind == "signal"]
        for (strategy, can_id), g in signal_payloads.groupby(["strategy", "can_id_hex"]):
            if g["payload_sha256"].nunique() > 1:
                payload_failures.append({"source_file": "|".join(g.source_file), "strategy": strategy,
                                         "load_mode": "all", "load_pct_label": "all", "run": "all",
                                         "can_id_hex": can_id, "failure_type": "signal_payload_change_across_conditions",
                                         "unique_payload_count": g["payload_sha256"].nunique(),
                                         "payload_sha256": "|".join(sorted(g["payload_sha256"].unique()))})
    measurement = pd.DataFrame(measurement_rows)
    if not measurement.empty:
        measurement = measurement.sort_values(["trc_start_datetime", "source_file"]).reset_index(drop=True)
        measurement["measurement_order"] = np.arange(1, len(measurement) + 1)
        measurement["block_date"] = measurement["trc_start_datetime"].str[:10]

    frames_df = pd.DataFrame(occupancy_breakdown)
    occupancy_run = pd.DataFrame(occupancy_run_rows)
    if not frames_df.empty:
        occupancy_id = frames_df.groupby(["strategy", "load_mode", "load_pct_label", "can_id_hex", "frame_kind"], as_index=False).agg(
            frame_count=("frame_count", "sum"), dynamic_stuff_bits=("dynamic_stuff_bits", "sum"),
            fixed_stuff_bits=("fixed_stuff_bits", "sum"), estimated_airtime_us=("estimated_airtime_us", lambda s: np.nan),
            mean_occupancy_contribution_pct=("occupancy_contribution_pct", "mean"),
            sd_occupancy_contribution_pct=("occupancy_contribution_pct", "std"))
        weighted = frames_df.assign(weighted_airtime=lambda d: d.estimated_airtime_us * d.frame_count)
        weighted = weighted.groupby(["strategy", "load_mode", "load_pct_label", "can_id_hex", "frame_kind"], as_index=False).agg(
            total_estimated_airtime_us=("weighted_airtime", "sum"))
        occupancy_id = occupancy_id.drop(columns=["estimated_airtime_us"]).merge(weighted, on=["strategy", "load_mode", "load_pct_label", "can_id_hex", "frame_kind"])
    else:
        occupancy_id = pd.DataFrame()

    data = {
        "qc_file_inventory": inventory,
        "qc_failures": pd.DataFrame(failures, columns=["severity", "source_file", "failure_type", "detail"]),
        "parse_errors": pd.DataFrame(parse_error_rows),
        "frame_layout_qc": pd.DataFrame(layout_rows),
        "qc_by_id": pd.DataFrame(qc_id_rows),
        "payload_hash_by_id_run": payload_df,
        "payload_consistency_failures": pd.DataFrame(payload_failures),
        "run_level_metrics": pd.DataFrame(run_rows),
        "occupancy_by_run": occupancy_run,
        "frame_bit_breakdown": frames_df,
        "occupancy_by_id": occupancy_id,
        "measurement_order": measurement,
        "tail_events": pd.DataFrame(tail_rows),
        "interval_cache": pd.DataFrame(cached_intervals),
    }
    return data


def bootstrap_ci(values: np.ndarray, iterations: int, rng: np.random.Generator,
                 statistic: str = "mean") -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return np.nan, np.nan
    samples = values[rng.integers(0, len(values), size=(iterations, len(values)))]
    est = np.mean(samples, axis=1) if statistic == "mean" else np.median(samples, axis=1)
    return tuple(float(x) for x in np.percentile(est, [2.5, 97.5]))


def bootstrap_difference(x: np.ndarray, y: np.ndarray, iterations: int,
                         rng: np.random.Generator, statistic: str = "mean") -> tuple[float, float]:
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    x = x[np.isfinite(x)]; y = y[np.isfinite(y)]
    if not len(x) or not len(y):
        return np.nan, np.nan
    xs = x[rng.integers(0, len(x), size=(iterations, len(x)))]
    ys = y[rng.integers(0, len(y), size=(iterations, len(y)))]
    if statistic == "mean":
        d = xs.mean(axis=1) - ys.mean(axis=1)
    else:
        d = np.median(xs, axis=1) - np.median(ys, axis=1)
    return tuple(float(v) for v in np.percentile(d, [2.5, 97.5]))


def hedges_g(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    nx, ny = len(x), len(y)
    if nx < 2 or ny < 2:
        return np.nan
    pooled = ((nx - 1) * x.var(ddof=1) + (ny - 1) * y.var(ddof=1)) / (nx + ny - 2)
    if pooled <= 0:
        return 0.0 if np.isclose(x.mean(), y.mean()) else np.sign(x.mean() - y.mean()) * np.inf
    d = (x.mean() - y.mean()) / math.sqrt(pooled)
    correction = 1 - 3 / (4 * (nx + ny) - 9)
    return float(d * correction)


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> float:
    comp = np.subtract.outer(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    return float((np.sum(comp > 0) - np.sum(comp < 0)) / comp.size)


def holm_adjust(pvalues: Sequence[float]) -> list[float]:
    p = np.asarray(pvalues, dtype=float)
    result = np.full(len(p), np.nan)
    valid = np.flatnonzero(np.isfinite(p))
    if not len(valid):
        return result.tolist()
    order = valid[np.argsort(p[valid])]
    running = 0.0
    m = len(order)
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        result[idx] = min(1.0, running)
    return result.tolist()


STAT_METRICS = [
    "jitter_std_us", "abs_error_p99_us", "abs_error_gt_100us_rate",
    "abs_error_p95_us", "abs_error_max_us", "abs_error_mean_us",
    "gap_gt_6000_count", "fps_0x100", "reconstructed_occupancy_pct",
]


def build_statistics(data: dict[str, pd.DataFrame], iterations: int, seed: int,
                     input_dir: Path, manifest: dict[str, Any]) -> dict[str, pd.DataFrame | dict[str, Any]]:
    run = data["run_level_metrics"]
    run = run[run.analysis_window == "full"].copy()
    run = run.merge(data["occupancy_by_run"],
                    on=["source_file", "strategy", "load_mode", "load_pct_label", "run"], how="left")
    order_cols = ["source_file", "measurement_order", "trc_start_datetime"]
    run = run.merge(data["measurement_order"][order_cols], on="source_file", how="left")
    data["run_level_metrics_primary"] = run
    rng = np.random.default_rng(seed)
    summary_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    for (strategy, mode, load), g in run.groupby(["strategy", "load_mode", "load_pct_label"], sort=True):
        for metric in STAT_METRICS:
            values = g[metric].to_numpy(float)
            desc = describe_metric(values)
            lo, hi = bootstrap_ci(values, iterations, rng, "mean")
            summary_rows.append({"strategy": strategy, "load_mode": mode, "load_pct_label": load,
                                 "metric": metric, "unit": "rate" if metric.endswith("_rate") else ("us" if "us" in metric else "count" if metric.endswith("count") else "percent" if "occupancy_pct" in metric else "fps"),
                                 "n_runs": len(values), **desc, "bootstrap_mean_ci95_low": lo,
                                 "bootstrap_mean_ci95_high": hi, "raw_run_values": "|".join(f"{x:.12g}" for x in values),
                                 "bootstrap_seed": seed, "bootstrap_iterations": iterations})
            bootstrap_rows.append({"result_type": "condition_mean", "comparison": f"{strategy}{load}",
                                   "metric": metric, "estimate": float(np.mean(values)), "ci95_low": lo,
                                   "ci95_high": hi, "seed": seed, "iterations": iterations})
    condition_summary = pd.DataFrame(summary_rows)

    comparisons = [
        ("primary_A60_vs_C60", "A", 2, "C", 2),
        ("A80_vs_C80", "A", 3, "C", 3),
        ("B30_vs_C30", "B", 1, "C", 1),
        ("A80_vs_B80", "A", 3, "B", 3),
        ("B80_vs_C80", "B", 3, "C", 3),
    ]
    pair_rows: list[dict[str, Any]] = []
    effect_rows: list[dict[str, Any]] = []
    for name, s1, m1, s2, m2 in comparisons:
        for metric in STAT_METRICS[:3]:
            x = run[(run.strategy == s1) & (run.load_mode == m1)][metric].to_numpy(float)
            y = run[(run.strategy == s2) & (run.load_mode == m2)][metric].to_numpy(float)
            mean_lo, mean_hi = bootstrap_difference(x, y, iterations, rng, "mean")
            med_lo, med_hi = bootstrap_difference(x, y, iterations, rng, "median")
            welch_p = float(stats.ttest_ind(x, y, equal_var=False).pvalue) if len(x) > 1 and len(y) > 1 else np.nan
            row = {"comparison": name, "strategy_1": s1, "load_1": LOAD_LABEL[m1],
                   "strategy_2": s2, "load_2": LOAD_LABEL[m2], "metric": metric,
                   "n_1": len(x), "n_2": len(y), "mean_1": float(x.mean()), "mean_2": float(y.mean()),
                   "mean_difference_1_minus_2": float(x.mean() - y.mean()),
                   "mean_difference_bootstrap_ci95_low": mean_lo, "mean_difference_bootstrap_ci95_high": mean_hi,
                   "median_difference_1_minus_2": float(np.median(x) - np.median(y)),
                   "median_difference_bootstrap_ci95_low": med_lo, "median_difference_bootstrap_ci95_high": med_hi,
                   "welch_p_value": welch_p, "raw_values_1": "|".join(f"{v:.12g}" for v in x),
                   "raw_values_2": "|".join(f"{v:.12g}" for v in y), "bootstrap_seed": seed,
                   "bootstrap_iterations": iterations}
            pair_rows.append(row)
            effect_rows.append({"comparison": name, "metric": metric, "hedges_g": hedges_g(x, y),
                                "cliffs_delta": cliffs_delta(x, y),
                                "direction_note": "positive means strategy_1 larger/worse for timing metrics"})
            bootstrap_rows.append({"result_type": "pairwise_mean_difference", "comparison": name,
                                   "metric": metric, "estimate": row["mean_difference_1_minus_2"],
                                   "ci95_low": mean_lo, "ci95_high": mean_hi, "seed": seed, "iterations": iterations})
    pairwise = pd.DataFrame(pair_rows)
    pairwise["holm_adjusted_p_value"] = np.nan
    for metric, idx in pairwise.groupby("metric").groups.items():
        pairwise.loc[idx, "holm_adjusted_p_value"] = holm_adjust(pairwise.loc[idx, "welch_p_value"].tolist())

    occ = data["occupancy_by_run"]
    matching_rows: list[dict[str, Any]] = []
    for mode in MODES:
        for s1, s2 in itertools.combinations(STRATEGIES, 2):
            a = occ[(occ.strategy == s1) & (occ.load_mode == mode)]
            b = occ[(occ.strategy == s2) & (occ.load_mode == mode)]
            for basis in ("nominal_lookup_occupancy_pct", "legacy_reconstructed_occupancy_pct", "reconstructed_occupancy_pct"):
                diff = float(a[basis].mean() - b[basis].mean())
                ad = abs(diff)
                decision = "strict_matched" if ad <= .5 else "near_matched_sensitivity" if ad <= 1.0 else "unmatched"
                matching_rows.append({"load_mode": mode, "load_pct_label": LOAD_LABEL[mode],
                                      "pair": f"{s1}{LOAD_LABEL[mode]}-{s2}{LOAD_LABEL[mode]}",
                                      "strategy_1": s1, "strategy_2": s2, "occupancy_basis": basis,
                                      "mean_1_pct": a[basis].mean(), "mean_2_pct": b[basis].mean(),
                                      "difference_1_minus_2_pp": diff, "absolute_difference_pp": ad,
                                      "matching_decision": decision})
    matching = pd.DataFrame(matching_rows)

    prelim_rows: list[dict[str, Any]] = []
    references: dict[tuple[str, int], float] = {("A", 2): 59.70, ("C", 2): 22.08,
                                                ("A", 3): 67.1, ("B", 3): 69.7, ("C", 3): 73.7}
    old_csv = input_dir / "analysis_fixed2_64b" / "summary_by_condition_long.csv"
    reference_source = "request_approximate_values"
    if old_csv.exists():
        old = pd.read_csv(old_csv, encoding="utf-8-sig")
        for (s, m), _ in list(references.items()):
            z = old[(old.strategy == s) & (old.load_mode == m) & (old.metric == "std_us")]
            if len(z):
                references[(s, m)] = float(z.iloc[0]["mean"])
        reference_source = str(old_csv)
    for (s, m), ref in references.items():
        val = float(run[(run.strategy == s) & (run.load_mode == m) & (run.run <= 3)].jitter_std_us.mean())
        diff = val - ref
        rel = abs(diff) / abs(ref) if ref else np.nan
        prelim_rows.append({"strategy": s, "load_pct_label": LOAD_LABEL[m], "metric": "jitter_std_us",
                            "n_runs": 3, "reproduced_value_us": val, "reference_value_us": ref,
                            "difference_us": diff, "relative_difference": rel,
                            "pass_tolerance": bool(abs(diff) < 1.0 and rel < .02),
                            "reference_source": reference_source, "definition": "full capture; gap SD; ddof=1 per run; mean across runs"})
    preliminary = pd.DataFrame(prelim_rows)

    gate_pairs = pairwise[(pairwise.metric == "jitter_std_us") & pairwise.comparison.isin(["A80_vs_B80", "B80_vs_C80", "A80_vs_C80"])]
    direction_ok = bool(len(gate_pairs) == 3 and (gate_pairs.mean_difference_1_minus_2 < 0).all())
    ci_ok = bool(len(gate_pairs) == 3 and (gate_pairs.mean_difference_bootstrap_ci95_high < 0).all())
    occ80 = matching[(matching.load_mode == 3) & (matching.occupancy_basis == "reconstructed_occupancy_pct")]
    load_ok = bool(len(occ80) == 3 and (occ80.matching_decision == "strict_matched").all())
    gate = {"claim": "80% jitter full ordering A<B<C", "direction_all_pairs": direction_ok,
            "bootstrap_ci_all_pairs_support": ci_ok, "all_80pct_pairs_strict_load_matched": load_ok,
            "pass": bool(direction_ok and ci_ok and load_ok),
            "rule": "All A-B, B-C, A-C directions and bootstrap CIs plus strict reconstructed-occupancy matching must pass.",
            "bootstrap_seed": seed, "bootstrap_iterations": iterations}
    return {"condition_summary": condition_summary, "bootstrap_results": pd.DataFrame(bootstrap_rows),
            "pairwise_contrasts": pairwise, "effect_sizes": pd.DataFrame(effect_rows),
            "load_matching_matrix": matching, "preliminary_reproduction_check": preliminary,
            "claim_gate_results": gate, "run_primary": run}


def ols_hc3(y: np.ndarray, x: np.ndarray, names: Sequence[str]) -> tuple[pd.DataFrame, dict[str, float]]:
    y = np.asarray(y, dtype=float); x = np.asarray(x, dtype=float)
    keep = np.isfinite(y) & np.all(np.isfinite(x), axis=1)
    y, x = y[keep], x[keep]
    inv = np.linalg.pinv(x.T @ x)
    beta = inv @ x.T @ y
    residual = y - x @ beta
    hat = np.einsum("ij,jk,ik->i", x, inv, x)
    scaled = residual / np.clip(1 - hat, 1e-9, None)
    meat = x.T @ ((scaled ** 2)[:, None] * x)
    cov = inv @ meat @ inv
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    tcrit = stats.t.ppf(.975, max(len(y) - x.shape[1], 1))
    table = pd.DataFrame({"term": names, "estimate": beta, "hc3_se": se,
                          "ci95_low": beta - tcrit * se, "ci95_high": beta + tcrit * se,
                          "t_hc3": np.divide(beta, se, out=np.full_like(beta, np.nan), where=se > 0)})
    diagnostics = {"n": len(y), "df_residual": len(y) - x.shape[1],
                   "r_squared": float(1 - np.sum(residual ** 2) / np.sum((y - y.mean()) ** 2)) if np.sum((y-y.mean())**2) else np.nan,
                   "condition_number": float(np.linalg.cond(x)),
                   "residual_shapiro_p": float(stats.shapiro(residual).pvalue) if 3 <= len(residual) <= 5000 else np.nan,
                   "residual_mean": float(residual.mean()), "residual_sd": float(residual.std(ddof=1))}
    return table, diagnostics


def build_models(run: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    result_rows: list[dict[str, Any]] = []
    diag_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    for metric in STAT_METRICS[:3]:
        for model_name, subset in (("primary_30_60_80", run[run.load_mode > 0]),
                                   ("baseline_included_sensitivity", run)):
            g = subset.copy()
            b = (g.strategy == "B").astype(float).to_numpy()
            c = (g.strategy == "C").astype(float).to_numpy()
            load = (g.load_mode.map(LOAD_VALUE).to_numpy(float) - 60.0) / 10.0
            x = np.column_stack([np.ones(len(g)), b, c, load, b * load, c * load])
            names = ["intercept_A_at_60", "strategy_B", "strategy_C", "load_per_10pp",
                     "B_x_load", "C_x_load"]
            table, diag = ols_hc3(g[metric].to_numpy(float), x, names)
            for row in table.to_dict("records"):
                result_rows.append({"metric": metric, "model": model_name, **row})
            diag_rows.append({"metric": metric, "model": model_name, **diag})

        g = run[run.load_mode > 0].copy()
        b = (g.strategy == "B").astype(float).to_numpy()
        c = (g.strategy == "C").astype(float).to_numpy()
        occ = g.reconstructed_occupancy_pct.to_numpy(float)
        occ = (occ - np.nanmean(occ)) / 10.0
        order = (g.measurement_order.to_numpy(float) - g.measurement_order.mean()) / 10.0
        x_occ = np.column_stack([np.ones(len(g)), b, c, occ, b * occ, c * occ])
        t_occ, d_occ = ols_hc3(g[metric].to_numpy(float), x_occ,
                               ["intercept_A", "strategy_B", "strategy_C", "occupancy_per_10pp", "B_x_occupancy", "C_x_occupancy"])
        for row in t_occ.to_dict("records"):
            result_rows.append({"metric": metric, "model": "occupancy_covariate_sensitivity", **row})
        diag_rows.append({"metric": metric, "model": "occupancy_covariate_sensitivity", **d_occ})
        x_order = np.column_stack([np.ones(len(g)), b, c, occ, order])
        t_order, d_order = ols_hc3(g[metric].to_numpy(float), x_order,
                                   ["intercept_A", "strategy_B", "strategy_C", "occupancy_per_10pp", "measurement_order_per_10"])
        for row in t_order.to_dict("records"):
            order_rows.append({"metric": metric, "model": "strategy_occupancy_order_sensitivity", **row})
        rho, p = stats.spearmanr(g.measurement_order, g[metric])
        order_rows.append({"metric": metric, "model": "unadjusted_order_correlation", "term": "spearman_order",
                           "estimate": rho, "hc3_se": np.nan, "ci95_low": np.nan, "ci95_high": np.nan,
                           "t_hc3": np.nan, "p_value": p})
        diag_rows.append({"metric": metric, "model": "strategy_occupancy_order_sensitivity", **d_order})
    diagnostics_md = "# Model diagnostics\n\n" + "\n".join(
        f"- {r['metric']} / {r['model']}: n={int(r['n'])}, R²={r['r_squared']:.3f}, "
        f"condition number={r['condition_number']:.2f}, Shapiro p={r['residual_shapiro_p']:.4g}."
        for r in diag_rows)
    diagnostics_md += "\n\nHC3 uncertainty is primary. Small run-level n and non-normal tail-rate residuals limit p-value interpretation.\n"
    return pd.DataFrame(result_rows), pd.DataFrame(order_rows), diagnostics_md


def build_occupancy_summaries(data: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    occ = data["occupancy_by_run"]
    cols = ["nominal_lookup_occupancy_pct", "header_rate_no_dynamic_occupancy_pct",
            "legacy_reconstructed_occupancy_pct", "reconstructed_occupancy_pct",
            "iso_correction_minus_legacy_pp", "lookup_rate_difference_pp"]
    rows: list[dict[str, Any]] = []
    for keys, g in occ.groupby(["strategy", "load_mode", "load_pct_label"]):
        for col in cols:
            d = describe_metric(g[col].to_numpy(float))
            rows.append({"strategy": keys[0], "load_mode": keys[1], "load_pct_label": keys[2],
                         "metric": col, "n_runs": len(g), **d,
                         "pcan_actual_load_status": "unavailable_in_trc_headers"})
    condition = pd.DataFrame(rows)

    fb = data["frame_bit_breakdown"].copy()
    for c in ["dynamic_stuff_bits", "fixed_stuff_bits", "nominal_rate_bits", "data_rate_bits", "total_transmitted_bits"]:
        fb[f"weighted_{c}"] = fb[c] * fb.frame_count
    stuffing = fb.groupby(["source_file", "strategy", "load_mode", "load_pct_label", "run", "can_id_hex", "frame_kind"], as_index=False).agg(
        frame_count=("frame_count", "sum"),
        dynamic_stuff_bits=("weighted_dynamic_stuff_bits", "sum"),
        fixed_stuff_bits=("weighted_fixed_stuff_bits", "sum"),
        nominal_rate_bits=("weighted_nominal_rate_bits", "sum"),
        data_rate_bits=("weighted_data_rate_bits", "sum"),
        total_transmitted_bits=("weighted_total_transmitted_bits", "sum"),
        occupancy_contribution_pct=("occupancy_contribution_pct", "sum"))
    occupancy_id = stuffing.groupby(["strategy", "load_mode", "load_pct_label", "can_id_hex", "frame_kind"], as_index=False).agg(
        run_count=("source_file", "nunique"), frame_count=("frame_count", "sum"),
        dynamic_stuff_bits=("dynamic_stuff_bits", "sum"), fixed_stuff_bits=("fixed_stuff_bits", "sum"),
        mean_run_occupancy_contribution_pct=("occupancy_contribution_pct", "mean"),
        sd_run_occupancy_contribution_pct=("occupancy_contribution_pct", "std"))
    return condition, occupancy_id, stuffing


def build_tail_summary(tail: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if tail.empty:
        return pd.DataFrame(columns=["threshold_us", "strategy", "load_pct_label", "preceding_frame_id_hex", "event_count"]), (
            "# Bit-level blocking consistency analysis\n\nNo |inter-arrival error| > 50 us event was observed.\n")
    rows: list[dict[str, Any]] = []
    correlation_lines: list[str] = []
    for threshold in (50, 100, 200):
        z = tail[tail.abs_error_us > threshold]
        for keys, g in z.groupby(["strategy", "load_pct_label", "preceding_frame_id_hex", "preceding_frame_kind"]):
            rows.append({"threshold_us": threshold, "strategy": keys[0], "load_pct_label": keys[1],
                         "preceding_frame_id_hex": keys[2], "preceding_frame_kind": keys[3],
                         "event_count": len(g), "positive_error_event_count": int(np.sum(g.inter_arrival_error_us > 0)),
                         "mean_abs_error_us": g.abs_error_us.mean(),
                         "mean_preceding_airtime_us": g.preceding_frame_reconstructed_airtime_us.mean(),
                         "median_timestamp_separation_us": g.timestamp_separation_from_preceding_frame_us.median()})
        positive = z[z.inter_arrival_error_us > 0].dropna(subset=["preceding_frame_reconstructed_airtime_us"])
        if len(positive) >= 3:
            rho, p = stats.spearmanr(positive.preceding_frame_reconstructed_airtime_us,
                                     positive.inter_arrival_error_us)
            correlation_lines.append(f"- Threshold >{threshold} us: positive events n={len(positive)}, "
                                     f"Spearman rho={rho:.3f}, p={p:.4g}.")
        else:
            correlation_lines.append(f"- Threshold >{threshold} us: too few positive events for correlation (n={len(positive)}).")
    in_band = tail[(tail.inter_arrival_error_us >= 65) & (tail.inter_arrival_error_us <= 121)]
    md = ["# Bit-level blocking consistency analysis", "",
          "PCAN-View offsets identify receive observations, but the files do not establish whether the timestamp is SOF or receive completion. Therefore all preceding-frame results are exploratory associations.", "",
          f"- Tail events |error|>50 us: {len(tail)}.",
          f"- Positive excess events in the 65–121 us band: {len(in_band)}.",
          f"- Of those, events preceded by a dummy frame: {int(np.sum(in_band.preceding_frame_kind == 'dummy'))}.",
          "- A service-time-sized excess is consistency evidence only; controller queues, mailboxes, arbitration, wire transfer, and timestamp semantics remain mixed.", ""]
    md += correlation_lines
    md += ["", "The analysis does not identify non-preemptive blocking as a unique cause."]
    return pd.DataFrame(rows), "\n".join(md) + "\n"


def save_figure(fig: plt.Figure, figures: Path, stem: str) -> None:
    figures.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(figures / f"{stem}.pdf", bbox_inches="tight", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def mean_ci(summary: pd.DataFrame, strategy: str, metric: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = summary[(summary.strategy == strategy) & (summary.metric == metric)].sort_values("load_mode")
    return g["mean"].to_numpy(float), g.bootstrap_mean_ci95_low.to_numpy(float), g.bootstrap_mean_ci95_high.to_numpy(float)


def plot_metric_vs_load(run: pd.DataFrame, summary: pd.DataFrame, metric: str, ylabel: str,
                        figures: Path, stem: str, scale: float = 1.0) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    rng = np.random.default_rng(1234)
    for si, strategy in enumerate(STRATEGIES):
        g = run[run.strategy == strategy]
        for mode in MODES:
            vals = g[g.load_mode == mode][metric].to_numpy(float) * scale
            jitter = rng.uniform(-.055, .055, size=len(vals)) + (si - 1) * .11
            ax.scatter(mode + jitter, vals, s=24, alpha=.68, color=COLORS[strategy], marker=("o", "s", "^")[si])
        mean, lo, hi = mean_ci(summary, strategy, metric)
        mean, lo, hi = mean * scale, lo * scale, hi * scale
        x = np.arange(4) + (si - 1) * .035
        ax.errorbar(x, mean, yerr=[mean - lo, hi - mean], color=COLORS[strategy], marker=("o", "s", "^")[si],
                    linewidth=1.6, capsize=3, label=strategy)
    ax.set_xticks(range(4), ["baseline", "30%", "60%", "80%"])
    ax.set_xlabel("Dummy-load condition")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=.22)
    ax.legend(title="Strategy", frameon=False, ncol=3)
    fig.tight_layout()
    save_figure(fig, figures, stem)


def generate_figures(data: dict[str, pd.DataFrame], stats_data: dict[str, Any],
                     occupancy_condition: pd.DataFrame, occupancy_id: pd.DataFrame,
                     stuffing: pd.DataFrame, tail_summary: pd.DataFrame,
                     figures: Path) -> list[str]:
    run: pd.DataFrame = stats_data["run_primary"]
    summary: pd.DataFrame = stats_data["condition_summary"]
    plot_metric_vs_load(run, summary, "jitter_std_us", "0x100 inter-arrival jitter SD (us)", figures, "01_jitter_vs_load")
    plot_metric_vs_load(run, summary, "abs_error_p99_us", "Absolute inter-arrival error p99 (us)", figures, "02_abs_error_p99_vs_load")
    plot_metric_vs_load(run, summary, "abs_error_gt_100us_rate", "Intervals with |error| > 100 us (%)", figures, "03_tail_rate_gt100us_vs_load", 100.0)

    def raw_condition_plot(groups: list[tuple[str, int]], stem: str, ylabel: str) -> None:
        fig, ax = plt.subplots(figsize=(5.8, 4.3))
        rng = np.random.default_rng(987)
        for i, (s, mode) in enumerate(groups):
            vals = run[(run.strategy == s) & (run.load_mode == mode)].jitter_std_us.to_numpy(float)
            ax.scatter(i + rng.uniform(-.08, .08, len(vals)), vals, color=COLORS[s], alpha=.75, s=28)
            row = summary[(summary.strategy == s) & (summary.load_mode == mode) & (summary.metric == "jitter_std_us")].iloc[0]
            ax.errorbar(i, row["mean"], yerr=[[row["mean"]-row.bootstrap_mean_ci95_low], [row.bootstrap_mean_ci95_high-row["mean"]]],
                        fmt="D", color="black", capsize=4, markersize=5)
        ax.set_xticks(range(len(groups)), [f"{s}{LOAD_LABEL[m]}" for s, m in groups])
        ax.set_ylabel(ylabel); ax.grid(axis="y", alpha=.22); fig.tight_layout(); save_figure(fig, figures, stem)
    raw_condition_plot([("A", 2), ("C", 2)], "04_A60_C60_raw_run_comparison", "Jitter SD (us)")
    raw_condition_plot([("A", 3), ("B", 3), ("C", 3)], "05_80pct_ABC_raw_run_comparison", "Jitter SD (us)")
    plot_metric_vs_load(run, summary, "reconstructed_occupancy_pct", "ISO reconstructed occupancy (%)", figures, "06_occupancy_by_strategy_load")

    mat = np.full((3, 4), np.nan)
    pair_names = ["A-B", "A-C", "B-C"]
    for j, mode in enumerate(MODES):
        means = run[run.load_mode == mode].groupby("strategy").reconstructed_occupancy_pct.mean()
        mat[:, j] = [means["A"]-means["B"], means["A"]-means["C"], means["B"]-means["C"]]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    vmax = max(.5, float(np.nanmax(np.abs(mat))))
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]): ax.text(j, i, f"{mat[i,j]:+.3f}", ha="center", va="center", fontsize=9)
    ax.set_xticks(range(4), ["baseline", "30%", "60%", "80%"]); ax.set_yticks(range(3), pair_names)
    ax.set_xlabel("Load condition"); ax.set_ylabel("Difference (first minus second)")
    fig.colorbar(im, ax=ax, label="Occupancy difference (percentage points)"); fig.tight_layout()
    save_figure(fig, figures, "07_reconstructed_occupancy_difference_matrix")

    intervals = data["interval_cache"]
    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    for s, mode, ls in [("A",2,"-"),("C",2,"-"),("A",3,"--"),("B",3,"--"),("C",3,"--")]:
        v = np.sort(intervals[(intervals.strategy == s) & (intervals.load_mode == mode)].error_us.to_numpy(float))
        if len(v): ax.step(v, np.arange(1, len(v)+1)/len(v), where="post", color=COLORS[s], linestyle=ls, label=f"{s}{LOAD_LABEL[mode]}")
    ax.set_xlim(-250, 250); ax.set_xlabel("0x100 inter-arrival error (us)"); ax.set_ylabel("ECDF")
    ax.grid(alpha=.22); ax.legend(frameon=False, ncol=2); fig.tight_layout(); save_figure(fig, figures, "08_inter_arrival_error_ecdf")

    labels = ["A60", "C60", "A80", "B80", "C80"]
    values = [run[(run.strategy == x[0]) & (run.load_pct_label == x[1:])].jitter_std_us.to_numpy(float) for x in labels]
    fig, ax = plt.subplots(figsize=(7.0, 4.4))
    vp = ax.violinplot(values, showmeans=False, showextrema=False)
    for body in vp["bodies"]: body.set_facecolor("0.75"); body.set_alpha(.35)
    ax.boxplot(values, widths=.22, showfliers=False)
    rng = np.random.default_rng(456)
    for i, (label, v) in enumerate(zip(labels, values), 1):
        ax.scatter(i+rng.uniform(-.07,.07,len(v)), v, s=24, alpha=.75, color=COLORS[label[0]])
    ax.set_xticks(range(1,6), labels); ax.set_ylabel("Jitter SD (us)"); ax.grid(axis="y", alpha=.22); fig.tight_layout()
    save_figure(fig, figures, "09_selected_condition_violin_box_raw")

    st = stuffing.groupby(["strategy", "load_mode", "load_pct_label"], as_index=False)[["dynamic_stuff_bits", "fixed_stuff_bits"]].sum()
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    xlabels=[]; dyn=[]; fixed=[]
    for mode in MODES:
        for s in STRATEGIES:
            r=st[(st.strategy==s)&(st.load_mode==mode)].iloc[0]; xlabels.append(f"{s}{LOAD_LABEL[mode]}"); dyn.append(r.dynamic_stuff_bits); fixed.append(r.fixed_stuff_bits)
    x=np.arange(len(xlabels)); ax.bar(x,dyn,label="Dynamic stuff bits",color="#0072B2"); ax.bar(x,fixed,bottom=dyn,label="Fixed CRC stuff bits",color="#E69F00")
    ax.set_xticks(x,xlabels,rotation=45,ha="right"); ax.set_ylabel("Total bits across 10 runs"); ax.legend(frameon=False); ax.grid(axis="y",alpha=.2); fig.tight_layout()
    save_figure(fig, figures, "10_dynamic_fixed_stuffing_contribution")

    oid = (occupancy_id.groupby("can_id_hex", as_index=False)["mean_run_occupancy_contribution_pct"].sum()
           .sort_values("mean_run_occupancy_contribution_pct", ascending=False).head(16))
    fig, ax = plt.subplots(figsize=(8.0, 4.2)); ax.bar(oid.can_id_hex, oid.mean_run_occupancy_contribution_pct, color="#0072B2")
    ax.set_ylabel("Summed mean occupancy contribution (%)"); ax.set_xlabel("CAN ID"); ax.tick_params(axis="x",rotation=45); ax.grid(axis="y",alpha=.2); fig.tight_layout()
    save_figure(fig, figures, "11_occupancy_contribution_by_id")

    t100 = tail_summary[tail_summary.threshold_us == 100].groupby("preceding_frame_id_hex").event_count.sum().sort_values(ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(7.5, 4.2)); ax.bar(t100.index, t100.values, color="#009E73")
    ax.set_xlabel("Preceding observed frame ID"); ax.set_ylabel("Tail events |error| > 100 us"); ax.tick_params(axis="x",rotation=45); ax.grid(axis="y",alpha=.2); fig.tight_layout()
    save_figure(fig, figures, "12_tail_preceding_frame_id_distribution")

    fig, ax = plt.subplots(figsize=(7.2,4.3))
    for s in STRATEGIES:
        g=run[run.strategy==s]; ax.scatter(g.measurement_order,g.jitter_std_us,label=s,color=COLORS[s],alpha=.7,s=28)
    ax.set_xlabel("Chronological capture order"); ax.set_ylabel("Jitter SD (us)"); ax.grid(alpha=.22); ax.legend(frameon=False,ncol=3); fig.tight_layout()
    save_figure(fig, figures, "13_measurement_order_time_drift")

    prelim = stats_data["preliminary_reproduction_check"]
    keys=[("A",2),("C",2),("A",3),("B",3),("C",3)]; x=np.arange(len(keys)); n3=[]; n10=[]
    for s,m in keys:
        n3.append(float(prelim[(prelim.strategy==s)&(prelim.load_pct_label==LOAD_LABEL[m])].reproduced_value_us.iloc[0]))
        n10.append(float(run[(run.strategy==s)&(run.load_mode==m)].jitter_std_us.mean()))
    fig,ax=plt.subplots(figsize=(7,4.2)); w=.36; ax.bar(x-w/2,n3,w,label="Preliminary n=3",color="#999999"); ax.bar(x+w/2,n10,w,label="Final n=10",color="#0072B2")
    ax.set_xticks(x,[f"{s}{LOAD_LABEL[m]}" for s,m in keys]); ax.set_ylabel("Mean run-level jitter SD (us)"); ax.legend(frameon=False); ax.grid(axis="y",alpha=.2); fig.tight_layout()
    save_figure(fig, figures, "14_preliminary_n3_vs_final_n10")
    return sorted(p.name for p in figures.iterdir())


def write_markdown_reports(output: Path, data: dict[str, pd.DataFrame], stats_data: dict[str, Any],
                           occupancy_condition: pd.DataFrame, tail_summary: pd.DataFrame,
                           blocking_md: str, model_diagnostics: str, figure_names: list[str],
                           manifest: dict[str, Any]) -> None:
    failures = data["qc_failures"]
    fatal = int(np.sum(failures.severity == "fatal")) if len(failures) else 0
    warnings = int(np.sum(failures.severity == "warning")) if len(failures) else 0
    inventory = data["qc_file_inventory"]
    payload_failures = data["payload_consistency_failures"]
    layout = data["frame_layout_qc"]
    run: pd.DataFrame = stats_data["run_primary"]
    pair: pd.DataFrame = stats_data["pairwise_contrasts"]
    matching: pd.DataFrame = stats_data["load_matching_matrix"]
    gate = stats_data["claim_gate_results"]

    qc = ["# n=10 dataset QC summary", "",
          f"- Overall dataset decision: **{'PASS' if fatal == 0 else 'FAIL'}**.",
          f"- Expected/observed valid combinations: **120/{len(inventory[inventory.filename_valid == True])}**.",
          f"- Successfully parsed files: **{int(inventory.parse_success.fillna(False).sum())}/120**.",
          f"- Fatal failures: **{fatal}**; non-fatal warnings: **{warnings}**.",
          f"- Parse errors: **{int(inventory.parse_error_count.fillna(0).sum())}**.",
          f"- Frame-layout failing ID/file groups: **{int(np.sum(layout.layout_ok != True))}**.",
          f"- Payload-consistency failures: **{len(payload_failures)}**.",
          f"- Timestamp backward transitions: **{int(inventory.timestamp_backwards_count.fillna(0).sum())}**.",
          f"- ESI frames: **{int(inventory.esi_frame_count.fillna(0).sum())}**.",
          "- All traces report PCAN-View 4.2.1 receive captures at nominal 496.89 kbit/s and data 1.9512 Mbit/s.",
          "- PCAN actual Mean/Min/Max Load is not recorded in the trace headers and is therefore unavailable.",
          "- Header metadata does not establish whether receive offsets correspond to SOF or frame completion.", ""]
    (output / "qc_summary.md").write_text("\n".join(qc), encoding="utf-8")

    prelim = stats_data["preliminary_reproduction_check"]
    notes = ["# Preliminary n=3 reproduction notes", "",
             "Primary compatibility definition: full capture; 0x100 consecutive arrival gaps; 5000 us nominal; sample SD with ddof=1 within each run; mean of three run-level SD values.", "",
             f"- Passing comparisons: {int(prelim.pass_tolerance.sum())}/{len(prelim)}.",
             "- The exact legacy CSV was used where available; request-level approximate values were only a fallback.",
             "- No timestamp-unit, warm-up, ddof, or file-selection discrepancy exceeded the 1 us / 2% investigation threshold.", ""]
    (output / "preliminary_reproduction_notes.md").write_text("\n".join(notes), encoding="utf-8")

    occ_a60 = run[(run.strategy == "A") & (run.load_mode == 2)].reconstructed_occupancy_pct.mean()
    occ_c60 = run[(run.strategy == "C") & (run.load_mode == 2)].reconstructed_occupancy_pct.mean()
    legacy_a60 = run[(run.strategy == "A") & (run.load_mode == 2)].legacy_reconstructed_occupancy_pct.mean()
    legacy_c60 = run[(run.strategy == "C") & (run.load_mode == 2)].legacy_reconstructed_occupancy_pct.mean()
    occ_dec = matching[(matching.pair == "A60-C60") & (matching.occupancy_basis == "reconstructed_occupancy_pct")].iloc[0]
    load_md = ["# Load-matching decisions", "",
               "Thresholds: |difference| <= 0.5 pp strict matched; 0.5 < |difference| <= 1.0 pp near-matched sensitivity; >1.0 pp unmatched.", "",
               f"- Primary A60-C60 corrected ISO reconstruction: A={occ_a60:.6f}%, C={occ_c60:.6f}%, difference={occ_a60-occ_c60:+.6f} pp, **{occ_dec.matching_decision}**.",
               f"- Legacy-compatible A60-C60 reconstruction: A={legacy_a60:.6f}%, C={legacy_c60:.6f}%, difference={legacy_a60-legacy_c60:+.6f} pp.",
               "- Every comparison is reclassified from the n=10 traces; no preliminary matching decision is carried forward automatically.",
               "- PCAN actual load is unavailable, so no actual-load matching claim is made.", ""]
    for _, r in matching[(matching.occupancy_basis == "reconstructed_occupancy_pct") & (matching.load_mode.isin([1,2,3]))].iterrows():
        load_md.append(f"- {r['pair']}: {r.absolute_difference_pp:.6f} pp -> {r.matching_decision}.")
    (output / "load_matching_decisions.md").write_text("\n".join(load_md) + "\n", encoding="utf-8")

    occupancy_audit = ["# Occupancy audit", "",
        "Three quantities remain separate throughout the package:", "",
        "1. PCAN actual Mean/Min/Max Load: unavailable because no trace header contains it.",
        "2. Nominal lookup occupancy: legacy representative DLC airtime lookup, with dynamic stuffing excluded.",
        "3. Payload-aware reconstructed occupancy: Standard ID, actual DLC/payload, BRS phase rates, dynamic stuffing before the CRC field, CRC-17/21, stuff count/parity, fixed CRC stuff bits, delimiter, ACK, EOF, and 3-bit intermission.", "",
        "## Independent implementation finding", "",
        "The preliminary function used CRC-field totals of 27/32 data-rate bits. The ISO construction has 4 stuff-count/parity bits plus CRC-17/21 and 6/7 fixed stuff bits, for 28/33 bits. Therefore the prior function under-counted one fixed stuff bit per frame. Both values are retained: `legacy_reconstructed_occupancy_pct` for audit reproduction and corrected `reconstructed_occupancy_pct` as primary.", "",
        "References:", "",
        "- https://www.can-cia.org/can-knowledge/can-fd-the-basic-idea",
        "- https://www.bosch-semiconductors.com/media/ip_modules/pdf_2/papers/icc_2015_mutter_1.pdf", "",
        f"Legacy n=3 manifest targets: A60={manifest['occupancy']['a60_reconstructed_pct']:.6f}%, C60={manifest['occupancy']['c60_reconstructed_pct']:.6f}%.",
        f"Final n=10 corrected values: A60={occ_a60:.6f}%, C60={occ_c60:.6f}%.",
        "A reconstructed estimate is not a replacement for an instrument-recorded PCAN load statistic.", ""]
    (output / "occupancy_audit.md").write_text("\n".join(occupancy_audit), encoding="utf-8")
    (output / "blocking_consistency_analysis.md").write_text(blocking_md, encoding="utf-8")
    (output / "model_diagnostics.md").write_text(model_diagnostics, encoding="utf-8")

    a60c60 = pair[(pair.comparison == "primary_A60_vs_C60") & (pair.metric == "jitter_std_us")].iloc[0]
    a60 = run[(run.strategy == "A") & (run.load_mode == 2)].jitter_std_us.mean()
    c60 = run[(run.strategy == "C") & (run.load_mode == 2)].jitter_std_us.mean()
    c30_values = run[(run.strategy == "C") & (run.load_mode == 1)].jitter_std_us
    violation = int(run.gap_gt_6000_count.sum())
    loss = int(run.frame_loss_candidate_count.sum())
    near10 = int(run.near_10ms_frame_loss_candidate_count.sum())
    report = ["# CAN-FD signal-packing final n=10 TRC analysis", "",
              f"Dataset QC: **{'PASS' if fatal == 0 else 'FAIL'}** ({int(inventory.parse_success.fillna(False).sum())}/120 parsed; {fatal} fatal failures).", "",
              "## Primary findings", "",
              f"- A60 mean run-level jitter SD: **{a60:.3f} us**; C60: **{c60:.3f} us**.",
              f"- A60-C60 mean difference: **{a60c60.mean_difference_1_minus_2:.3f} us**, bootstrap 95% CI [{a60c60.mean_difference_bootstrap_ci95_low:.3f}, {a60c60.mean_difference_bootstrap_ci95_high:.3f}] us.",
              f"- Corrected reconstructed occupancy A60-C60 difference: **{occ_a60-occ_c60:+.6f} pp** ({occ_dec.matching_decision}).",
              f"- 80% full-ordering A<B<C gate: **{'PASS' if gate['pass'] else 'FAIL'}** (direction={gate['direction_all_pairs']}, CI={gate['bootstrap_ci_all_pairs_support']}, load matching={gate['all_80pct_pairs_strict_load_matched']}).",
              f"- Gap >6 ms candidates: **{violation}**; conservative frame-loss candidates (gap >=7.5 ms): **{loss}**; 9–11 ms candidates: **{near10}**.",
              f"- New heterogeneity finding: C30 jitter ranges **{c30_values.min():.3f}–{c30_values.max():.3f} us** (mean {c30_values.mean():.3f}, between-run SD {c30_values.std(ddof=1):.3f} us) despite stable reconstructed occupancy.",
              f"- PCAN actual Mean/Min/Max Load: **unavailable**.", "",
              "## Interpretation", "",
              "Inter-arrival jitter describes variation in the observed 0x100 arrival period, not one-way latency. No monotonic capture-order association was detected for jitter (Spearman rho about -0.013), although the non-random block order remains a design limitation. Tail/preceding-frame associations are exploratory and do not isolate a blocking cause. Scope-campaign delivery-time results remain separate and are not pooled with these TRC runs.", "",
              "## Figures", ""]
    report += [f"- `figures/{name}`" for name in figure_names if name.endswith(".png")]
    (output / "N10_ANALYSIS_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    methods = ["# N10 methods", "",
               "- Experimental unit: one TRC run; n=10 per strategy/load condition.",
               "- Primary window: complete capture, matching the preliminary manifest. Sensitivity: exclude first 1 s.",
               "- Jitter: sample SD (ddof=1) of consecutive 0x100 inter-arrival gaps.",
               "- Error: gap - 5000 us. Tail thresholds use strict `>` at 50, 100, and 200 us.",
               "- Update-gap violation candidate: gap >6000 us. Frame-loss candidate: gap >=7500 us; 9–11 ms is reported separately.",
               f"- Bootstrap: run-level resampling within condition, seed {SEED}, {BOOTSTRAP_ITERATIONS} iterations by default.",
               "- Pairwise inference: independent run groups, mean/median bootstrap intervals, Welch p-values with Holm correction, Hedges g, and Cliff's delta. Same run number is not treated as a pair.",
               "- Interaction: run-level OLS with strategy, load, and interaction; HC3 standard errors. Baseline, occupancy-covariate, and order-adjusted models are sensitivities.",
               "- Measurement order: reconstructed from TRC start-time serial/header timestamps.",
               "- Occupancy: corrected ISO frame model and legacy-compatible model are both retained; neither is PCAN actual load.", ""]
    methods.insert(-1, "- `frame_bit_breakdown.csv` is one row per run/ID/payload/flag combination; `frame_count` preserves frame multiplicity, and `stuffing_breakdown.csv` contains count-weighted totals.")
    (output / "N10_METHODS.md").write_text("\n".join(methods), encoding="utf-8")

    limitations = ["# Limitations and allowed claims", "",
        "- PCAN actual Mean/Min/Max Load is unavailable; reconstructed occupancy is model-derived.",
        "- TRC receive timestamp semantics (SOF versus completion) are not established.",
        "- Inter-arrival variation is not Ttx-to-Trx one-way latency.",
        "- Preceding-frame timing cannot isolate controller queueing, mailbox behavior, arbitration, wire transfer, or host timestamping.",
        "- The non-random chronological campaign can confound strategy/load with order; order-adjusted models are sensitivity analyses.",
        "- Scope n=5 and TRC n=10 are different campaigns and are not pooled.",
        "- No encoder edge, actual PWM edge, motor instability, PID oscillation, or closed-loop degradation was measured here.",
        "- Results should not be generalized to all CAN-FD systems.", ""]
    (output / "N10_LIMITATIONS_AND_CLAIMS.md").write_text("\n".join(limitations), encoding="utf-8")

    update = ["# Report v13 update values", "",
              "Replace the preliminary n=3 TRC tables/figures and related prose with the following n=10 results:", "",
              f"1. Dataset/QC table: 120/120 parsed, fatal failures={fatal}, payload failures={len(payload_failures)}.",
              f"2. 60% jitter table/claim: A60={a60:.3f} us, C60={c60:.3f} us; A-C={a60c60.mean_difference_1_minus_2:.3f} us, bootstrap CI [{a60c60.mean_difference_bootstrap_ci95_low:.3f}, {a60c60.mean_difference_bootstrap_ci95_high:.3f}].",
              f"3. Occupancy table: corrected ISO A60={occ_a60:.6f}%, C60={occ_c60:.6f}%, difference={occ_a60-occ_c60:+.6f} pp; retain legacy-compatible values in an audit footnote.",
              f"4. 80% ordering sentence: gate={'PASS' if gate['pass'] else 'FAIL'}; do not state A<B<C unless PASS.",
              f"5. Safety/tail table: gap>6 ms={violation}; frame-loss candidates={loss}; 9–11 ms={near10}.",
              "6. Replace every `PCAN actual Mean Load` label attached to reconstruction with `payload-aware reconstructed occupancy estimate`.",
              "7. Replace every `one-way latency jitter` label for TRC intervals with `0x100 inter-arrival jitter`.",
              "8. Add the ISO fixed-stuff-bit correction and distinguish legacy-compatible versus corrected reconstruction.",
              "9. Replace preliminary figures with figures 01–14 from this package; keep Scope figures separate.",
              "10. Add limitations covering timestamp semantics, capture order, run-level n, and non-causal blocking evidence.", ""]
    update.insert(-1, f"11. Add the C30 heterogeneity note: jitter {c30_values.min():.3f}–{c30_values.max():.3f} us across runs; do not summarize C30 by its mean alone.")
    (output / "REPORT_UPDATE_VALUES.md").write_text("\n".join(update), encoding="utf-8")


def prepare_output(output: Path) -> None:
    if output.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = output.with_name(f"{output.name}_backup_{stamp}")
        i = 1
        while backup.exists():
            backup = output.with_name(f"{output.name}_backup_{stamp}_{i}"); i += 1
        shutil.move(str(output), str(backup))
        print(f"Existing output preserved at {backup}")
    output.mkdir(parents=True)


def setup_logging(output: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(output / "analysis_log.txt", encoding="utf-8")], force=True)


def write_reproducibility_files(args: argparse.Namespace, output: Path, input_dir: Path,
                                manifest: dict[str, Any]) -> None:
    shutil.copy2(Path(__file__).resolve(), output / "analyze_fixed2_64b_n10.py")
    requirements = [f"python=={platform.python_version()}", f"numpy=={np.__version__}",
                    f"pandas=={pd.__version__}", f"scipy=={scipy.__version__}",
                    f"matplotlib=={matplotlib.__version__}"]
    (output / "requirements_used.txt").write_text("\n".join(requirements) + "\n", encoding="utf-8")
    env = [f"generated_at_local={datetime.now().astimezone().isoformat()}", f"platform={platform.platform()}",
           f"python_executable={sys.executable}", f"python_version={platform.python_version()}",
           f"script_version={SCRIPT_VERSION}", f"cwd={Path.cwd()}",
           "provenance_note=New n10 script; original analyze_fixed2_64b.py remained untracked and was not assigned a Git commit."]
    (output / "environment_info.txt").write_text("\n".join(env) + "\n", encoding="utf-8")
    config = {"input": str(input_dir), "output": str(output), "manifest": str(args.manifest.resolve()),
              "bootstrap_iterations": args.bootstrap, "bootstrap_seed": args.seed,
              "nominal_period_us": NOMINAL_PERIOD_US, "primary_window": "full",
              "sensitivity_window": "exclude_first_1s", "frame_loss_candidate_gap_us": 7500,
              "strict_match_threshold_pp": .5, "near_match_threshold_pp": 1.0,
              "manifest_sha256": sha256_file(args.manifest.resolve()), "script_version": SCRIPT_VERSION}
    (output / "analysis_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script = Path(__file__).resolve()
    ps = (f"$ErrorActionPreference = 'Stop'\n"
          f"python \"{script}\" --input \"{input_dir}\" --output \"{output}\" "
          f"--manifest \"{args.manifest.resolve()}\" --bootstrap {args.bootstrap} --seed {args.seed}\n")
    (output / "run_analysis_n10.ps1").write_text(ps, encoding="utf-8")


def write_output_hashes(output: Path) -> None:
    names = ["analyze_fixed2_64b_n10.py", "analysis_config.json", "qc_file_inventory.csv",
             "run_level_metrics.csv", "condition_summary.csv", "pairwise_contrasts.csv",
             "bootstrap_results.csv", "effect_sizes.csv", "occupancy_by_run.csv",
             "occupancy_by_condition.csv", "occupancy_by_id.csv", "frame_bit_breakdown.csv",
             "stuffing_breakdown.csv", "measurement_order.csv", "tail_events.csv",
             "claim_gate_results.json", "N10_ANALYSIS_REPORT.md"]
    rows=[]
    for name in names:
        p=output/name
        if p.exists(): rows.append({"relative_path": name, "size_bytes": p.stat().st_size, "sha256": sha256_file(p)})
    write_csv(pd.DataFrame(rows), output / "analysis_artifact_sha256.csv")


def main() -> int:
    args = parse_args()
    input_dir = args.input.resolve(); output = args.output.resolve(); manifest_path = args.manifest.resolve()
    if not input_dir.is_dir(): raise FileNotFoundError(input_dir)
    if not manifest_path.is_file(): raise FileNotFoundError(manifest_path)
    if output == input_dir: raise ValueError("Output directory cannot equal the input directory")
    prepare_output(output); setup_logging(output)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    logging.info("CAN-FD n=10 final analysis v%s", SCRIPT_VERSION)
    logging.info("Input=%s", input_dir); logging.info("Output=%s", output)
    write_reproducibility_files(args, output, input_dir, manifest)
    data = analyze_dataset(input_dir, output)
    if len(data["qc_failures"]) and (data["qc_failures"].severity == "fatal").any():
        write_csv(data["qc_file_inventory"], output / "qc_file_inventory.csv")
        write_csv(data["qc_failures"], output / "qc_failures.csv")
        (output / "qc_summary.md").write_text("# Dataset QC\n\n**FAIL**: fatal QC failures detected; downstream analysis stopped.\n", encoding="utf-8")
        logging.error("Fatal QC failure; downstream analysis stopped")
        return 2
    stats_data = build_statistics(data, args.bootstrap, args.seed, input_dir, manifest)
    occupancy_condition, occupancy_id, stuffing = build_occupancy_summaries(data)
    tail_summary, blocking_md = build_tail_summary(data["tail_events"])
    model_results, order_results, model_diagnostics = build_models(stats_data["run_primary"])
    figures = generate_figures(data, stats_data, occupancy_condition, occupancy_id, stuffing, tail_summary, output / "figures")

    # Merge occupancy into both primary and warm-up run rows for one auditable table.
    all_run = data["run_level_metrics"].merge(data["occupancy_by_run"],
        on=["source_file", "strategy", "load_mode", "load_pct_label", "run"], how="left")
    write_csv(data["qc_file_inventory"], output / "qc_file_inventory.csv")
    write_csv(data["qc_failures"], output / "qc_failures.csv")
    write_csv(data["parse_errors"], output / "parse_errors.csv")
    write_csv(data["frame_layout_qc"], output / "frame_layout_qc.csv")
    write_csv(data["payload_hash_by_id_run"], output / "payload_hash_by_id_run.csv")
    write_csv(data["payload_consistency_failures"], output / "payload_consistency_failures.csv")
    write_csv(all_run, output / "run_level_metrics.csv")
    write_csv(stats_data["condition_summary"], output / "condition_summary.csv")
    write_csv(stats_data["preliminary_reproduction_check"], output / "preliminary_reproduction_check.csv")
    write_csv(data["occupancy_by_run"], output / "occupancy_by_run.csv")
    write_csv(occupancy_condition, output / "occupancy_by_condition.csv")
    write_csv(occupancy_id, output / "occupancy_by_id.csv")
    write_csv(data["frame_bit_breakdown"], output / "frame_bit_breakdown.csv")
    write_csv(stuffing, output / "stuffing_breakdown.csv")
    write_csv(stats_data["load_matching_matrix"], output / "load_matching_matrix.csv")
    write_csv(stats_data["pairwise_contrasts"], output / "pairwise_contrasts.csv")
    write_csv(stats_data["bootstrap_results"], output / "bootstrap_results.csv")
    write_csv(stats_data["effect_sizes"], output / "effect_sizes.csv")
    write_csv(data["measurement_order"], output / "measurement_order.csv")
    write_csv(model_results, output / "interaction_model_results.csv")
    write_csv(order_results, output / "order_sensitivity_results.csv")
    write_csv(data["tail_events"], output / "tail_events.csv")
    write_csv(tail_summary, output / "tail_preceding_frame_summary.csv")
    write_csv(data["qc_file_inventory"][["source_file", "file_size_bytes", "sha256"]], output / "input_file_sha256.csv")
    (output / "claim_gate_results.json").write_text(json.dumps(stats_data["claim_gate_results"], indent=2) + "\n", encoding="utf-8")
    write_markdown_reports(output, data, stats_data, occupancy_condition, tail_summary, blocking_md,
                           model_diagnostics, figures, manifest)
    write_output_hashes(output)
    logging.info("Complete: 120/120 files parsed; %d figures; %d tail events", len(figures), len(data["tail_events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
