# 3-node FULL gap-sweep response analysis (230-250 us)

Fresh read of the 6 overwritten full-sweep TRC in `3node_fixed_bg/`. No cached result reused.
Markers (0x7F0) decoded and excluded from all statistics. `configured_gap_us` (marker payload) and
`observed_onwire_bg_spacing` (TRC) are separate; configured gap never reverse-inferred.
Each point = one START marker; first 2 s settle dropped, next 20 s analysed. Auto-sweep points are
exploratory (NOT independent reset replicates); no inferential stats.

## Acquisition: all 6 files COMPLETE. QC 33/33 not-FAIL.

| file | markers | START | END | decoded gaps | dur s | frames |
|---|--:|--:|--:|---|--:|--:|
| A_gap230_240.trc | 7 | 6 | 1 | 230/232/234/236/238/240 | ~140+ | ~579058 |
| A_gap242_250.trc | 6 | 5 | 1 | 242/244/246/248/250 | ~116+ | ~466736 |
| B_gap230_240.trc | 7 | 6 | 1 | 230/232/234/236/238/240 | ~139+ | ~534214 |
| B_gap242_250.trc | 6 | 5 | 1 | 242/244/246/248/250 | ~116+ | ~427296 |
| C_gap230_240.trc | 7 | 6 | 1 | 230/232/234/236/238/240 | ~139+ | ~530204 |
| C_gap242_250.trc | 6 | 5 | 1 | 242/244/246/248/250 | ~117+ | ~425188 |

## Q1. gap -> jitter (us), all 11 gaps

| gap | A | B | C | mean | spread(max-min) |
|--:|--:|--:|--:|--:|--:|
| 230 | 67.92 | 68.21 | 69.54 | 68.56 | 1.62 |
| 232 | 44.46 | 73.62 | 48.13 | 55.40 | 29.15 |
| 234 | 68.73 | 70.06 | 67.96 | 68.91 | 2.10 |
| 236 | 49.98 | 49.52 | 49.30 | 49.60 | 0.67 |
| 238 | 25.49 | 24.10 | 26.58 | 25.39 | 2.49 |
| 240 | 56.12 | 51.66 | 53.44 | 53.74 | 4.46 |
| 242 | 73.57 | 72.05 | 73.89 | 73.17 | 1.84 |
| 244 | 79.13 | 78.98 | 75.12 | 77.74 | 4.00 |
| 246 | 67.42 | 65.48 | 66.92 | 66.61 | 1.94 |
| 248 | 48.50 | 47.79 | 45.63 | 47.31 | 2.87 |
| 250 | 22.67 | 24.64 | 33.72 | 27.01 | 11.06 |

## occupancy + BG (configured vs observed), per gap (mean of A/B/C)

| gap | obs spacing median | obs mode | bg fps | occ_total% | occ_ctrl% (A/B/C) | occ_bg% |
|--:|--:|--:|--:|--:|---|--:|
| 230 | 230.0 | 230 | 4299 | 64.48 | 8.40/4.98/7.32 | 57.59 |
| 232 | 231.0 | 230 | 4225 | 63.50 | 8.40/4.98/7.32 | 56.60 |
| 234 | 234.3 | 236 | 4230 | 63.56 | 8.40/4.98/7.32 | 56.66 |
| 236 | 236.0 | 236 | 4192 | 63.05 | 8.40/4.98/7.32 | 56.15 |
| 238 | 236.0 | 236 | 4164 | 62.68 | 8.40/4.98/7.32 | 55.78 |
| 240 | 239.7 | 242 | 4122 | 62.11 | 8.40/4.98/7.32 | 55.21 |
| 242 | 242.0 | 242 | 4095 | 61.75 | 8.40/4.98/7.32 | 54.86 |
| 244 | 242.3 | 242 | 4070 | 61.41 | 8.40/4.98/7.32 | 54.51 |
| 246 | 245.7 | 248 | 4037 | 60.98 | 8.40/4.98/7.32 | 54.08 |
| 248 | 248.0 | 248 | 4007 | 60.57 | 8.40/4.98/7.32 | 53.67 |
| 250 | 247.3 | 248 | 3978 | 60.18 | 8.40/4.98/7.32 | 53.28 |

## Q9. adjacent-gap deltas (largest jitter change per small occupancy change)

| strategy | gap | d_gap us | d_occ pp | d_jitter us |
|---|---|--:|--:|--:|
| A | 238->240 | 2 | -0.52 | 30.63 |
| B | 238->240 | 2 | -0.57 | 27.57 |
| C | 238->240 | 2 | -0.61 | 26.86 |
| A | 248->250 | 2 | -0.36 | -25.84 |
| B | 236->238 | 2 | -0.44 | -25.42 |
| A | 236->238 | 2 | -0.31 | -24.49 |
| A | 232->234 | 2 | 0.37 | 24.26 |
| A | 230->232 | 2 | -1.40 | -23.46 |

## Q8. similar-occupancy, different-jitter (|d_occ|<=1.0 pp), strongest first

| a | b | same_strat | occ a | occ b | d_occ pp | jit a | jit b | d_jit us |
|---|---|:--:|--:|--:|--:|--:|--:|--:|
| Ag244 | Cg238 | False | 62.49 | 63.26 | 0.77 | 79.13 | 26.58 | 52.54 |
| Ag250 | Cg244 | False | 61.33 | 62.02 | 0.697 | 22.67 | 75.12 | 52.46 |
| Ag238 | Ag242 | True | 63.75 | 62.8 | 0.946 | 25.49 | 73.57 | 48.08 |
| Bg238 | Bg242 | True | 61.02 | 60.1 | 0.912 | 24.1 | 72.05 | 47.95 |
| Ag250 | Bg234 | False | 61.33 | 61.88 | 0.557 | 22.67 | 70.06 | 47.39 |
| Cg238 | Cg242 | True | 63.26 | 62.36 | 0.906 | 26.58 | 73.89 | 47.31 |
| Bg232 | Cg238 | False | 62.33 | 63.26 | 0.933 | 73.62 | 26.58 | 47.03 |
| Ag242 | Cg238 | False | 62.8 | 63.26 | 0.46 | 73.57 | 26.58 | 46.98 |
| Bg234 | Bg238 | True | 61.88 | 61.02 | 0.867 | 70.06 | 24.1 | 45.96 |
| Ag246 | Ag250 | True | 62.1 | 61.33 | 0.772 | 67.42 | 22.67 | 44.76 |

## Claim boundary

- auto-sweep = exploratory (n=1/gap, phase may carry across points); confirm with independent resets.
- reconstructed occupancy != PCAN actual load; jitter != latency; observed BG spacing is endogenous;
  configured gap != exact wire period. No arbitration/phase-resonance causal claim.

## Figures

- `figures/1_gap_vs_jitter_ABC.png`
- `figures/2_gap_vs_occupancy_ABC.png`
- `figures/3_occupancy_vs_jitter.png`
- `figures/4_gap_vs_observed_bg_spacing.png`
- `figures/5_gap_vs_bg_fps.png`
- `figures/6_strategy_spread_by_gap.png`
- `figures/7_delta_occupancy_vs_delta_jitter.png`
- `figures/8_acf_extrema_A.png`
