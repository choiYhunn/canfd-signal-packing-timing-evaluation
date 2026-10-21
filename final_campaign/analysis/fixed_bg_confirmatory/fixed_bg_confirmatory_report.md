# Fixed external-background CONFIRMATORY analysis (A/B/C x L/M/H x n=5)

- Raw: `<private>/3node_fixed_bg` (48 TRC: 45 main + 3 BG-OFF baseline a0/b0/c0). Original TRC unmodified; outputs only in this folder.
- **Same configured external BG gap for all strategies at each level** (L=630, M=240, H=170 us) - this removes the earlier strategy-specific dummy-gap tuning confound.
- Background-only PCAN load reference (calibration only, NOT the A/B/C total load): 630->~9%, 240->~52%, 170->~75%.
- Metrics reuse verified n=10 module (`interval_metrics`, `wire_breakdown`, `EXPECTED` layout). Replicate unit = run (n=5); no frame-level pseudo-replication. jitter = SD of consecutive 0x100 inter-arrival gaps (NOT latency). reconstructed occupancy != PCAN actual Mean Load (actual = UNKNOWN, not recorded).

## 1. Mapping (verified, filename -> condition; observed-mode is a MAPPING CHECK, not a configured value)

| strategy | BG level | configured gap us | runs | obs BG spacing mode us |
|---|---|--:|---|--:|
| A | H | 170 | 1|2|3|4|5 | 168 |
| A | L | 630 | 1|2|3|4|5 | 577 |
| A | M | 240 | 1|2|3|4|5 | 240 |
| B | H | 170 | 1|2|3|4|5 | 174 |
| B | L | 630 | 1|2|3|4|5 | 611 |
| B | M | 240 | 1|2|3|4|5 | 240 |
| C | H | 170 | 1|2|3|4|5 | 168 |
| C | L | 630 | 1|2|3|4|5 | 577 |
| C | M | 240 | 1|2|3|4|5 | 240 |

## 2. QC: main {'PASS': np.int64(44), 'PASS_WITH_TIMING_NOTE': np.int64(1)}

Control layout verified against source module `EXPECTED` (A: 0x100/0x101/0x102 + 50ms 0x110/0x120/0x130; B: 0x100(32B)+0x110(32B); C: 0x100(64B)). Per-file detail in `file_qc.csv`.

Timing-note / fail files:
- c2_4.trc (C-M run4): PASS_WITH_TIMING_NOTE; gap>6ms=1, gap>10ms=1, max 10.0 ms.

## 3. Background common-input check (configured vs observed on-wire)

| condition | configured gap | obs mode | obs median | obs IQR | bg fps mean+-sd | occ_bg% |
|---|--:|--:|--:|--:|--|--:|
| A-L | 630 | 577 | 616.6 | 277.2 | 1586+-0 | 21.2 |
| A-M | 240 | 240 | 240.0 | 6.2 | 4101+-1 | 54.9 |
| A-H | 170 | 168 | 168.0 | 8.0 | 5628+-0 | 74.9 |
| B-L | 630 | 611 | 623.8 | 71.0 | 1586+-0 | 21.2 |
| B-M | 240 | 240 | 243.0 | 28.2 | 4148+-11 | 55.6 |
| B-H | 170 | 174 | 169.0 | 10.0 | 5808+-1 | 77.2 |
| C-L | 630 | 577 | 611.4 | 158.8 | 1586+-0 | 21.2 |
| C-M | 240 | 240 | 239.8 | 98.8 | 4153+-3 | 55.6 |
| C-H | 170 | 168 | 168.0 | 7.0 | 5675+-0 | 75.5 |

## 4/5. 0x100 jitter by condition (n=5 run-level)

| condition | jitter mean+-SD us | median [min,max] | p99 mean | >100us% mean | occ_total% mean+-SD |
|---|--|--|--:|--:|--|
| A-L | 34.35+-0.22 | 34.24 [34.14,34.65] | 125.0 | 4.84 | 29.61+-0.00 |
| B-L | 34.30+-0.38 | 34.32 [33.86,34.89] | 124.2 | 4.92 | 26.19+-0.00 |
| C-L | 34.32+-0.26 | 34.41 [33.91,34.55] | 124.0 | 4.97 | 28.52+-0.00 |
| A-M | 58.67+-0.38 | 58.73 [58.16,59.22] | 131.5 | 10.90 | 63.34+-0.01 |
| B-M | 58.34+-6.70 | 61.40 [46.76,62.75] | 116.2 | 12.67 | 60.54+-0.15 |
| C-M | 61.24+-13.04 | 60.20 [50.66,82.83] | 127.8 | 6.96 | 62.94+-0.04 |
| A-H | 71.29+-0.08 | 71.28 [71.19,71.37] | 111.4 | 11.45 | 83.29+-0.00 |
| B-H | 69.03+-0.07 | 69.02 [68.92,69.11] | 107.0 | 13.73 | 82.20+-0.01 |
| C-H | 71.66+-0.16 | 71.64 [71.48,71.83] | 106.0 | 5.40 | 82.82+-0.00 |

### Per-level strategy ordering (ascending jitter)
- **BG-L**: B(34.30) < C(34.32) < A(34.35)
- **BG-M**: B(58.34) < A(58.67) < C(61.24)
- **BG-H**: B(69.03) < A(71.29) < C(71.66)

## 6. Occupancy / bandwidth (same BG input, strategy differs)

| condition | occ_total% | occ_ctrl% | occ_bg% | jitter us |
|---|--:|--:|--:|--:|
| A-L | 29.61 | 8.40 | 21.21 | 34.35 |
| B-L | 26.19 | 4.98 | 21.21 | 34.30 |
| C-L | 28.52 | 7.32 | 21.21 | 34.32 |
| A-M | 63.34 | 8.40 | 54.94 | 58.67 |
| B-M | 60.54 | 4.98 | 55.56 | 58.34 |
| C-M | 62.94 | 7.31 | 55.62 | 61.24 |
| A-H | 83.29 | 8.40 | 74.88 | 71.29 |
| B-H | 82.20 | 4.98 | 77.22 | 69.03 |
| C-H | 82.82 | 7.32 | 75.50 | 71.66 |

## 7. OLD (strategy-specific tuned gap, confounded) vs NEW (fixed gap)

| strat | level | new gap | old target | old jitter | new jitter | old occ% | new occ% |
|---|---|--:|---|--|--|--:|--:|
| A | L | 630 | A30 | 15.68+-4.52 | 34.35+-0.22 | 29.8 | 29.6 |
| A | M | 240 | A60 | 30.22+-16.02 | 58.67+-0.38 | 63.7 | 63.3 |
| A | H | 170 | A80 | 71.32+-0.27 | 71.29+-0.08 | 83.3 | 83.3 |
| B | L | 630 | B30 | 40.96+-1.74 | 34.30+-0.38 | 26.7 | 26.2 |
| B | M | 240 | B60 | 61.61+-0.28 | 58.34+-6.70 | 61.7 | 60.5 |
| B | H | 170 | B80 | 66.86+-0.17 | 69.03+-0.07 | 83.1 | 82.2 |
| C | L | 630 | C30 | 40.43+-0.46 | 34.32+-0.26 | 29.0 | 28.5 |
| C | M | 240 | C60 | 24.78+-0.65 | 61.24+-13.04 | 63.3 | 62.9 |
| C | H | 170 | C80 | 71.26+-0.20 | 71.66+-0.16 | 82.8 | 82.8 |

(OLD A-M corresponds to old A60 whose n=5 mean includes the run1 anomaly ~59us; old A60 run2-8 ~23us.)

## 10. Baseline (reference only; NOT new n=5)

| file | dur s | 0x100 | jitter us | median|err| us | max interval ms | note |
|---|--:|--:|--:|--:|--:|---|
| a0.trc | 30.4 | 6071 | 6.0 | 1.0 | 5.1 |  |
| b0.trc | 31.2 | 6231 | 5.2 | 2.0 | 5.1 |  |
| c0.trc | 30.4 | 6089 | 5.2 | 1.0 | 5.1 |  |

Robust baseline: median |error| column is the robust summary (jitter SD can be inflated by a single rare silence; known C0/A0 anomalies from the exploratory set are preserved there, not here).

## Figures

- `figures/bg_fps_by_condition.png`
- `figures/jitter_by_fixed_bg_strategy.png`
- `figures/jitter_vs_occupancy.png`
- `figures/mid_240us_acf_comparison.png`
- `figures/occupancy_by_fixed_bg_strategy.png`
- `figures/old_vs_new_comparison.png`
