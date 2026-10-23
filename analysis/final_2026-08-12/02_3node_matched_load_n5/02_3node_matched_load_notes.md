# Dataset B — 3-node matched-load exploratory n=5 (with background-cadence confound)

**Status: valid exploratory system-level data with a background-cadence confound.** These runs are NOT
wrong data and are NOT deleted; they must simply not be read as packing-alone causal evidence.

**Files:** `02_3node_matched_load_summary.csv` (= condition_summary_n5, 12 conditions, run=replicate n=5),
`run_level_metrics.csv` (per run), `load_matching_n5.csv`, `3node_n5_analysis.md` (full report).

## Design
- Real 3-node bus: Node1 CONTROL TX / Node2 external BACKGROUND TX / Node3 RX-actuator; PCAN Listen-Only.
- A/B/C × baseline/30/60/80 × run1–5 = 60 balanced TRC (+1 extra A30 run6 sensitivity only).
- Replicate unit = run (n=5). Within-trace frames are not independent replicates.

## Key numbers (jitter mean ± SD, µs)
- 30-target: A30 15.68 ± 4.52, B30 40.96 ± 1.74, C30 40.43 ± 0.46.
- 60-target: **A60 30.22 ± 16.02** (median 23.3; run1 anomaly high, run2–5 ≈23), **B60 61.61 ± 0.28**,
  **C60 24.78 ± 0.65**.
- 80-target: A80 71.32 ± 0.27, B80 66.86 ± 0.17, C80 71.26 ± 0.20.
- Reconstructed control occupancy (packing bandwidth, fixed per strategy): A 8.40 % / B 4.98 % / C 7.32 %.

## The confound
To make total bus load similar across strategies, the background dummy gap was tuned **per strategy**
(60-target: A ≈ 240, B ≈ 235, C ≈ 238 µs; 30/80 similar per-strategy tuning). So A/B/C did **not** share
the same external background cadence. The later configured-gap response (Dataset D) shows jitter depends
strongly and non-monotonically on that gap, and these particular per-strategy gaps land on different points
of that response curve — e.g. C60's gap 238 sits at a jitter valley (5000/238 ≈ 21.008, near-integer) while
B60's gap ≈235 sits near a peak. Therefore the large B60-vs-C60 contrast here **cannot** be attributed to
packing alone; the shared-gap re-test (Dataset C) and the sweep (Dataset D) are the clean comparisons.

## Also noted
- Baseline single-event long-gap anomalies (Cbaseline run1 ≈25 ms, Abaseline run3 ≈30 ms) inflate only
  that run's jitter SD; the baseline median jitter is ≈5.5 µs. Raw TRC left unchanged.
- `reconstructed occupancy` ≠ PCAN actual Mean Load (not recorded). `jitter` ≠ latency.
