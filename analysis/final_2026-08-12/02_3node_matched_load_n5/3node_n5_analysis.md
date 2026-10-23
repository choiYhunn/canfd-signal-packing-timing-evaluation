# 3-node external-background CAN-FD repeated dataset (n=5)

- Raw TRC: `C:\Users\yhch0\Documents\프로젝트\2026 하계 URP(CAN-FD Signal packing 효율 연구)\3node` (61 files, never modified): 12 conditions x run1..5 = 60 balanced + 1 extra `a1_6.trc` (A, 30-target, run6).
- 3-node: Node1 CONTROL TX / Node2 external BACKGROUND TX / Node3 RX-PWM; PCAN Listen-Only.
- Same background firmware as run1 (no firmware change this campaign).
- Metrics reuse the verified n=10 module `trace_fixed2/analysis_n10/analyze_fixed2_64b_n10.py` (`interval_metrics`, `wire_breakdown`, `expected_kind`, `EXPECTED`, `EXPECTED_PAYLOAD`). No metric was redefined.
- **Replicate unit = run (n=5).** Within-trace frames are NOT independent replicates; no p-value-centric inference is drawn from n=5. Effect size + run-to-run consistency are primary.
- `reconstructed occupancy` = payload-aware ISO airtime estimate, **NOT** PCAN actual Mean Load (actual load was not saved this campaign). `jitter` = SD of consecutive 0x100 inter-arrival gaps, **NOT** one-way / end-to-end latency.
- Dummy gap: nominal calibration values (A 627/240/170, B 616/235/168, C 617/238/170 us for 30/60/80); live-adjusted by approximately +/-1 us on some runs; exact per-run value not recorded. This is target-load calibration, not measurement error.

## 1. Inventory / completeness

| condition | runs present | primary n | complete | extra |
|---|---|---:|:--:|---|
| Abaseline | 1|2|3|4|5 | 5 | YES | - |
| A30 | 1|2|3|4|5|6 | 5 | YES | 6 |
| A60 | 1|2|3|4|5 | 5 | YES | - |
| A80 | 1|2|3|4|5 | 5 | YES | - |
| Bbaseline | 1|2|3|4|5 | 5 | YES | - |
| B30 | 1|2|3|4|5 | 5 | YES | - |
| B60 | 1|2|3|4|5 | 5 | YES | - |
| B80 | 1|2|3|4|5 | 5 | YES | - |
| Cbaseline | 1|2|3|4|5 | 5 | YES | - |
| C30 | 1|2|3|4|5 | 5 | YES | - |
| C60 | 1|2|3|4|5 | 5 | YES | - |
| C80 | 1|2|3|4|5 | 5 | YES | - |

Total TRC = 61 (balanced 60 + 1 extra). Extra replicate = `a1_6.trc` (A, 30-target, run6), excluded from all primary n=5 statistics.

## 2. QC: 61/61 PASS

Per-file QC (n=10 definitions, applied unchanged): parse success, capture duration, frame count, timestamp monotonicity, duplicate timestamps, expected CAN IDs, Standard-ID, CAN-FD/BRS, per-ID DLC/layout, fixed-payload byte-identity, unexpected IDs, ESI/error frames, 0x100 count, gap>6 ms, 9-11 ms loss candidates, background 0x300-0x30F presence, baseline dummy-absence, 300k-frame ceiling. Naming<->content verified: letter by observed 0x100 DLC (A 8B / B 32B / C 64B), number by dummy presence + monotonic occupancy. Details: `qc_by_file.csv`.

### Baseline long-gap / anomaly recurrence check (known C0 run1 25 ms issue)

- **a0_3.trc** (Abaseline): gap>6ms=1, 9-11ms cand=0, max interval 30.0 ms. Reported, raw TRC unchanged.
- **c0_1.trc** (Cbaseline): gap>6ms=1, 9-11ms cand=0, max interval 25.0 ms. Reported, raw TRC unchanged.

## 3. Acquisition duration / 300k buffer

PCAN buffer raised to 300000 frames; new runs ~30 s. Any 300k ceiling hit is flagged in `run_manifest_n5.csv` (`hit_300k_ceiling`). run1 high-load captures were shorter (old 100k cap), so absolute counts are compared as rates; a 15 s common-window jitter sensitivity is in `run_level_metrics.csv` (`jitter_std_us_win15s`).

| condition | dur run1 (s) | dur run2-5 mean (s) |
|---|---:|---:|
| Abaseline | 30.6 | 30.7 |
| Bbaseline | 30.9 | 31.8 |
| Cbaseline | 31.2 | 30.8 |
| A30 | 32.2 | 30.7 |
| B30 | 31.0 | 30.6 |
| C30 | 30.5 | 30.5 |
| A60 | 21.0 | 30.6 |
| B60 | 22.4 | 31.2 |
| C60 | 22.8 | 30.7 |
| A80 | 15.9 | 30.5 |
| B80 | 16.4 | 30.7 |
| C80 | 17.0 | 30.4 |

## 4/6. Condition-level n=5 summary (run = replicate)

jitter/p99/occupancy/bg-fps are per-run values aggregated over run1-5.

| cond | gap_us | jitter mean+-SD | jitter med [min,max] | p99 mean | >100us% mean | occ% mean+-SD | bg fps mean |
|---|---|---|---|---:|---:|---|---:|
| Abaseline | OFF | 68.16+-140.11 | 5.49 [5.16,318.79] | 5.2 | 0.09 | 8.40+-0.00 | 0.0 |
| Bbaseline | OFF | 6.03+-0.61 | 5.79 [5.47,6.85] | 3.0 | 0.11 | 4.98+-0.00 | 0.0 |
| Cbaseline | OFF | 55.08+-110.88 | 5.61 [5.04,253.44] | 4.1 | 0.07 | 7.32+-0.00 | 0.0 |
| A30 | 627 | 15.68+-4.52 | 13.73 [13.59,23.76] | 105.2 | 1.46 | 29.76+-0.03 | 1597.3 |
| B30 | 616 | 40.96+-1.74 | 40.56 [39.41,43.94] | 124.2 | 4.79 | 26.67+-0.04 | 1622.1 |
| C30 | 617 | 40.43+-0.46 | 40.38 [39.88,41.04] | 125.0 | 5.12 | 28.99+-0.01 | 1620.5 |
| A60 | 240 | 30.22+-16.02 | 23.34 [22.53,58.88] | 129.2 | 4.60 | 63.66+-0.18 | 4125.5 |
| B60 | 235 | 61.61+-0.28 | 61.60 [61.27,62.03] | 128.4 | 12.10 | 61.70+-0.00 | 4234.4 |
| C60 | 238 | 24.78+-0.65 | 24.90 [23.69,25.30] | 126.4 | 3.28 | 63.31+-0.00 | 4180.0 |
| A80 | 170 | 71.32+-0.27 | 71.24 [71.00,71.70] | 110.9 | 11.52 | 83.29+-0.00 | 5627.9 |
| B80 | 168 | 66.86+-0.17 | 66.93 [66.67,67.03] | 117.2 | 16.18 | 83.11+-0.00 | 5877.2 |
| C80 | 170 | 71.26+-0.20 | 71.34 [70.96,71.45] | 106.0 | 4.81 | 82.82+-0.00 | 5674.7 |

## 5/8. PRIMARY: 60-target run-level jitter (A60 / B60 / C60)

| run | A60 jitter | B60 jitter | C60 jitter |
|---:|---:|---:|---:|
| 1 | 58.88 | 62.03 | 24.76 |
| 2 | 22.93 | 61.47 | 24.90 |
| 3 | 22.53 | 61.27 | 23.69 |
| 4 | 23.34 | 61.69 | 25.30 |
| 5 | 23.45 | 61.60 | 25.23 |

- **A60 jitter mean +- SD = 30.22 +- 16.02 us** (median 23.34, range [22.53, 58.88]).

- **B60 jitter mean +- SD = 61.61 +- 0.28 us** (median 61.60, range [61.27, 62.03]).

- **C60 jitter mean +- SD = 24.78 +- 0.65 us** (median 24.90, range [23.69, 25.30]).

### A60 - C60 matched-index descriptive comparison (NOT a formal paired test)

Run i of A and run i of C were not physically simultaneous trials, so this is a matched-index descriptive difference only.

| run | A60 | C60 | A60-C60 |
|---:|---:|---:|---:|
| 1 | 58.88 | 24.76 | 34.11 |
| 2 | 22.93 | 24.90 | -1.97 |
| 3 | 22.53 | 23.69 | -1.17 |
| 4 | 23.34 | 25.30 | -1.96 |
| 5 | 23.45 | 25.23 | -1.78 |

Matched-index mean A60-C60 = **5.45 +- 16.03 us** (all runs same sign: False). 2-node n=10 reference A60-C60 = +37.7 us.

## 6b. Comparison vs 2-node fixed-payload n=10 (descriptive)

| cond | 3node n=5 jitter mean+-SD | 2node n=10 jitter | 3node >100us% | 2node >100us% | 3node occ% | 2node occ% |
|---|---|---:|---:|---:|---:|---:|
| A60 | 30.22+-16.02 | 59.8 | 4.60 | 13.50 | 63.66 | 63.25 |
| B60 | 61.61+-0.28 | 61.8 | 12.10 | 8.33 | 61.70 | 61.92 |
| C60 | 24.78+-0.65 | 22.1 | 3.28 | 2.75 | 63.31 | 63.34 |
| A30 | 15.68+-4.52 | 36.2 | 1.46 | 4.98 | 29.76 | 29.58 |
| B30 | 40.96+-1.74 | 51.6 | 4.79 | 10.55 | 26.67 | 33.13 |
| C30 | 40.43+-0.46 | 36.1 | 5.12 | 5.45 | 28.99 | 33.17 |
| A80 | 71.32+-0.27 | 67.0 | 11.52 | 2.05 | 83.29 | 83.34 |
| B80 | 66.86+-0.17 | 69.5 | 16.18 | 10.11 | 83.11 | 82.26 |
| C80 | 71.26+-0.20 | 73.8 | 4.81 | 18.98 | 82.82 | 82.82 |

## 7. Load matching (reconstructed occupancy, proxy only)

| target | A occ mean+-SD | B occ mean+-SD | C occ mean+-SD | max spread pp |
|---|---|---|---|---:|
| baseline | 8.40+-0.00 | 4.98+-0.00 | 7.32+-0.00 | 3.42 |
| 30 | 29.76+-0.03 | 26.67+-0.04 | 28.99+-0.01 | 3.09 |
| 60 | 63.66+-0.18 | 61.70+-0.00 | 63.31+-0.00 | 1.97 |
| 80 | 83.29+-0.00 | 83.11+-0.00 | 82.82+-0.00 | 0.47 |

Actual PCAN Mean/Min/Max Load was NOT saved; occupancy is a reconstructed proxy. Pairwise pp differences and spreads per target are in `load_matching_n5.csv`.

## 9. Strategy x load ordering (descriptive interaction)

- **30-target** jitter (A=15.68, B=40.96, C=40.43) -> ascending order A < C < B.
- **60-target** jitter (A=30.22, B=61.61, C=24.78) -> ascending order C < A < B.
- **80-target** jitter (A=71.32, B=66.86, C=71.26) -> ascending order B < C < A.

See figure 01 (strategy x load interaction). n=5, descriptive; no factorial ANOVA is forced.

## 11. Extra a1 run6 sensitivity

| condition | metric | n5 mean+-SD | run6 value | n6 mean+-SD | mean shift |
|---|---|---|---:|---|---:|
| A30 | jitter | 15.68+-4.52 | 13.16 | 15.26+-4.17 | -0.42 |
| A30 | p99 | 105.20+-10.55 | 88.88 | 102.48+-11.55 | -2.72 |
| A30 | gt100_rate | 1.46+-1.00 | 0.89 | 1.36+-0.92 | -0.09 |
| A30 | occ | 29.76+-0.03 | 29.78 | 29.77+-0.03 | 0.00 |

The extra replicate does not materially alter the descriptive conclusion for its condition.

## 13. Claim boundary

**Supportable:** repeated independent-run pattern; whether the 60-target ordering/magnitude holds under an external-background 3-node; load-dependent strategy ordering; same-MCU background confound is harder to invoke as sole cause.

**NOT yet supportable:** pure arbitration proven as cause; frame-length-alone or write-count-alone causal effect; motor-stability improvement; C optimal in all conditions. `reconstructed occupancy` != PCAN actual load; `jitter` != latency; 100 us is an analysis threshold, not a deadline.

## Figures

- `figures/01_strategy_x_load_jitter_interaction.png`
- `figures/02_60target_run_level_scatter.png`
- `figures/03_all_condition_run_level_jitter.png`
- `figures/04_reconstructed_occupancy_by_condition.png`
- `figures/05_60target_jitter_vs_occupancy.png`
- `figures/06_gt100us_rate_strategy_x_load.png`
- `figures/07_p99_strategy_x_load.png`
