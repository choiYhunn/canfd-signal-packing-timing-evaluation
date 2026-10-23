# FINAL CAN-FD timing experiment — evidence index / handoff (2026-08-12)

This is an **evidence index for reviewer/ChatGPT handoff**, not a paper draft. It points to the
compact CSV/report/figure evidence in this directory so the full study — from the first 2-node
campaign to the final independent-reset confirmation — can be re-reviewed with every number checkable.

- Raw TRC are **not** uploaded (large; local only). All numbers below are backed by the CSV/MD files here.
- `configured (dummy) min gap` is the firmware-set background inter-frame gap; it is **NOT** an exact
  wire-side period. Reports keep `configured_gap_us` and `observed_onwire_bg_spacing` separate.
- `reconstructed occupancy` = payload-aware ISO airtime estimate, **NOT** PCAN actual Mean Load
  (actual load was not recorded; `UNKNOWN`). `jitter` = SD of consecutive 0x100 inter-arrival gaps,
  **NOT** latency. `100 us` is an analysis threshold, not a control deadline.

## Directory map
- `01_2node_historical/` — Dataset A. Compact pivot `01_2node_summary.csv` + notes. Authoritative full
  tables already in repo: `analysis/summary_tables/{condition_summary,run_level_metrics,pairwise_contrasts,occupancy_by_condition}.csv`,
  script `analysis/scripts/analyze_fixed2_64b_n10.py`.
- `02_3node_matched_load_n5/` — Dataset B (3-node, strategy-specific gaps → matched load, n=5). Exploratory, has a background-cadence confound.
- `03_fixed_bg_confirmatory/` — Dataset C (same configured gap for A/B/C at each level; n=5).
- `04_full_gap_sweep/` — Dataset D (configured-gap response 230–250 µs, A/B/C).
- `05_gap_confirmation_n3/` — Dataset E (A only; 238/240/244/250 × 3 order-permuted independent-reset runs).
- `06_firmware_and_scripts/` — sweep + confirmation `hal_entry.c`, analysis drivers, and a README describing the sweep/marker/timing implementation.

## Research evolution
1. Dynamic-payload pilot — `g_seq` entered the CAN payload → per-strategy write-count changed payload
   bit patterns → dynamic bit-stuffing confound mixed with packing effect.
2. Fixed-payload correction — same-ID payload held byte-identical; dynamic set demoted to pilot.
3. **Dataset A**: 2-node fixed-payload **n=10** (120 TRC). Primary strict-matched result A60 vs C60.
4. 3-node external-background node added (CONTROL TX / BACKGROUND TX / RX-actuator) to separate
   same-MCU scheduling from bus contention.
5. **Dataset B**: 3-node matched-load exploratory **n=5** — background gap tuned *per strategy* to match total load.
6. Confound found: those per-strategy gaps mean A/B/C did not share the same configured external
   background cadence.
7. **Dataset C**: fixed-background confirmatory — **same configured external background-generator input**
   for A/B/C at each level (configured gap / mode / dummy set / firmware identical; realized on-wire
   throughput treated as an outcome, not forced equal).
8. **Dataset D**: full configured-gap response sweep 230–250 µs.
9. **Dataset E**: independent-reset, order-permuted **n=3** confirmation of the sweep extrema (A strategy).
10. Hardware experiment complete.

(An intermediate timestamp-only "phase/blocking" forensic on Dataset B used the **observed on-wire BG
spacing**, which is endogenous; its causal interpretation was **retracted** and superseded by the
controlled configured-gap sweep in Dataset D. It is intentionally not included here to avoid confusion.)

## Current supported findings (strict tiers)

### Strongly supported (measured, reproduced)
- **Packing bandwidth effect (real).** Control-frame airtime is a fixed per-strategy constant:
  reconstructed control occupancy **B 4.98 % < C 7.32 % < A 8.40 %** (identical across Datasets C/D).
- **A large and stable packing-strategy-specific timing separation did not reproduce under a common
  configured background input.** With the same configured background-generator input, A/B/C 0x100 jitter
  is close: BG-L ≈ **34.3 µs**, BG-M ≈ **58–61 µs** (with B/C showing some run-to-run variability — B-M
  SD ≈6.70, C-M SD ≈13.04, Dataset C), BG-H ≈ **69–72 µs**. Across the coarse sweep, **9 of 11 configured
  gaps showed an A/B/C jitter spread ≤4.5 µs**; isolated larger deviations occurred at 232 µs (spread
  ≈29.2 µs) and 250 µs (spread ≈11.1 µs) and were not independently replicated as packing effects
  (Dataset D `same_gap_strategy_spread.csv`). This bounds the packing timing effect as not large/stable;
  it does not assert the effect is exactly zero.
- **Repeatable non-monotonic jitter response to the configured background gap.** Over 230–250 µs the
  0x100 jitter changes strongly and non-monotonically, whereas reconstructed occupancy shows a gradual
  overall downward trend as configured gap increases, with small local deviations (i.e. not strictly
  monotonic; e.g. A 232 ≈64.14 → 234 ≈64.51 %, C 232 ≈64.03 → 234 ≈64.27 %) over the ≈64.5 → 60.2 % range.
  Extrema reproduce under independent reset and permuted order (Dataset E, n=3, SD ≤0.31 µs).
- **Mean bus utilization alone does not characterize the timing response.** Points with nearly equal
  reconstructed occupancy differ greatly in jitter (Dataset D `similar_load_comparisons.csv`); e.g.
  A gap238 (occ ≈63.8 %, jitter ≈25) vs A gap242 (occ ≈62.8 %, jitter ≈74).

### Supported association / bounded interpretation
- The jitter response shows a **repeatable resonance-like pattern consistent with the relative
  timing / commensurability between the 5 ms control period and the periodic background traffic**.
  Alignment (using 5000 / configured_gap): near-integer gaps sit at jitter valleys
  (5000 / 238 ≈ **21.008** near-integer; 5000 / 250 = **20** exact integer), the near-half-integer gap
  sits at a jitter peak (5000 / 244 ≈ **20.492** near-half-integer). This is an association/consistency
  statement only.
- Why `configured gap` is a meaningful scheduler input (mechanism plausibility, not proof): in the M mode
  the generator uses `active_count = 8`, initially staggers the dummy IDs by the configured min gap, and
  reschedules a transmitted dummy ID to be next due after `min_gap × active_count` — so the configured gap
  sets the aggregate background release cadence. It is still **not** an exact wire period: mailbox
  availability, arbitration/contention, and scheduler reseeding make the realized on-wire spacing differ
  from the configured gap.

### Interpretation boundary — inter-arrival jitter is not latency
Model each 0x100 arrival as `a_k = k·T + d_k` (T = 5 ms). The measured inter-arrival error is
`(a_k − a_{k−1}) − T = d_k − d_{k−1}`. So a **low inter-arrival jitter means small cycle-to-cycle delay
variation, NOT small absolute one-way latency**: a constant per-cycle blocking delay cancels in the
difference and yields low jitter even if a real latency exists. Therefore do **not** read a jitter valley
as "minimum response time" or "best deadline performance". This study did not measure absolute one-way
latency (`Tpwm_sw` is a software-update request time, not a measured PWM edge / actuator response).

### Not proven (do NOT state as established)
- CAN arbitration is the direct cause; commensurability/resonance is proven.
- Exact phase-resonance causal proof.
- `configured min gap` = exact wire-side period.
- Packing timing effect is exactly zero; A/B/C are always identical; strategy has no timing effect.
- Any one A/B/C strategy is always optimal.
- Low jitter = low latency; a valley = minimum response time / best deadline performance.
- Any motor / actuator stability impact.

## Key numeric tables (all checkable against the CSVs here)

### Dataset A — 2-node fixed-payload n=10 (`01_2node_historical/01_2node_summary.csv`)
| cond | jitter µs | p99 µs | >100µs % | occ % |
|---|---:|---:|---:|---:|
| A60 | 59.76 | 132.0 | 13.50 | 63.25 |
| B60 | 61.79 | 124.8 | 8.32 | 61.92 |
| C60 | 22.10 | 124.3 | 2.75 | 63.34 |
(full 12 conditions in the CSV; primary strict-matched contrast A60−C60 = +37.67 µs, bootstrap CI
[37.47, 37.86] in `analysis/summary_tables/pairwise_contrasts.csv`).

### Dataset B — 3-node matched-load exploratory n=5 (`02_.../02_3node_matched_load_summary.csv`)
Jitter mean ± SD (µs): A30 15.68±4.52, B30 40.96±1.74, C30 40.43±0.46; **A60 30.22±16.02 (median 23.3;
run1 anomaly high, run2–5 ≈23), B60 61.61±0.28, C60 24.78±0.65**; A80 71.32, B80 66.86, C80 71.26.
Per-strategy gaps differed (A60 240 / B60 235 / C60 238 µs) → background-cadence confound.
Exploratory BG-OFF A/C aggregate jitter means are **not** used for the main inference because individual
traces contain previously documented rare bus-wide / capture-wide silences (Cbaseline run1 ≈25 ms,
Abaseline run3 ≈30 ms) that inflate that run's SD; the clean fixed-BG baseline sanity traces are treated
only as reference. Raw traces and outliers are retained, not removed.

### Dataset C — fixed-background confirmatory n=5 (`03_.../condition_summary.csv`)
Here A/B/C shared the **same configured external background-generator input** (same configured gap, same
generator mode, same dummy ID set/payload, same background-node firmware). The generator input was
controlled identically across A/B/C; the realized on-wire background throughput was treated as an outcome
of bus interaction rather than forced to be identical. Jitter mean ± SD (µs): BG-L A34.35/B34.30/C34.32;
BG-M A58.67/B58.34/C61.24; BG-H A71.29/B69.03/C71.66. Old strategy contrast (B60≫C60) does **not**
reproduce when the configured background input is shared.

### Dataset D — full gap sweep, jitter µs (`04_.../same_gap_strategy_spread.csv`)
| gap | A | B | C | 5000/gap |
|---:|---:|---:|---:|---:|
| 230 | 67.9 | 68.2 | 69.5 | 21.739 |
| 232 | 44.5 | 73.6 | 48.1 | 21.552 |
| 234 | 68.7 | 70.1 | 68.0 | 21.368 |
| 236 | 50.0 | 49.5 | 49.3 | 21.186 |
| 238 | 25.5 | 24.1 | 26.6 | 21.008 (near-integer, valley) |
| 240 | 56.1 | 51.7 | 53.4 | 20.833 |
| 242 | 73.6 | 72.0 | 73.9 | 20.661 |
| 244 | 79.1 | 79.0 | 75.1 | 20.492 (near-half-integer, peak) |
| 246 | 67.4 | 65.5 | 66.9 | 20.325 |
| 248 | 48.5 | 47.8 | 45.6 | 20.161 |
| 250 | 22.7 | 24.6 | 33.7 | 20.000 (exact integer, valley) |
Reconstructed total occupancy shows a gradual overall downward trend (≈64.5 → 60.2 %) with small local
deviations (not strictly monotonic); jitter changes strongly and non-monotonically.

### Dataset E — independent-reset, order-permuted confirmation n=3 (`05_.../gap_jitter_n3_summary.csv`)
| gap | r1 | r2 | r3 | mean ± SD |
|---:|---:|---:|---:|---|
| 238 | 26.17 | 26.66 | 26.27 | 26.37 ± 0.26 |
| 240 | 56.65 | 56.93 | 56.94 | 56.84 ± 0.16 |
| 244 | 75.61 | 76.20 | 76.07 | 75.96 ± 0.31 |
| 250 | 21.76 | 21.62 | 22.12 | 21.83 ± 0.25 |
Sequences: r1 238→240→244→250, r2 250→244→240→238, r3 244→238→250→240. Each configured gap was observed
at different sequence positions across the three reset runs, and within-gap run-to-run SD remained
≤0.31 µs. Thus the gap-dependent ordering was **robust to the three tested sweep orders, with no evidence
of a large order/carry-over effect in these runs**. (These 3 permuted orders are not a full factorial of
gap × position, so this is a robustness check, not a variance-decomposition estimate of a pure order effect.)

Accurate change wording: **238 → 240** raises jitter ≈ **26.4 → 56.8 µs (≈ +30 µs)**; **240 → 244**
rises further to ≈ **76.0 µs**; **250** returns to ≈ **21.8 µs**. (Do not phrase this as "a 2 µs change
makes jitter 22 → 76".)

## What a reviewer can reproduce from this repo alone
Datasets A–E are all present as compact CSV + report + key figures, plus the analysis drivers and the
modified `hal_entry.c` for the sweep and confirmation firmware. The 2-node authoritative tables and the
verified metric module are already in `analysis/summary_tables/` and `analysis/scripts/`. Raw TRC are
excluded by design; every headline number above is traceable to a file in this directory.
