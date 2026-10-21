# 3-node gap-sweep response analysis (marker-segmented)

> ## ACQUISITION QC — CRITICAL: the sweep captures are INCOMPLETE
>
> Each of the 6 TRC is only ~28-31 s long and contains only **2 markers** (START idx0 + START idx1),
> no END. The sweep firmware dwells 22 s/point (2 s settle + 20 s), so a full GROUP1 needs ~132 s and
> GROUP2 ~110 s. At ~30 s only the **first gap of each group** has a full 20 s window; the 2nd point is
> truncated (<1 s after settle) and gaps 232-240 / 244-250 and the END marker were never captured.
> **Usable points = 6** (A/B/C x gap230 from _gap230_240, gap242 from _gap242_250). The intended
> 230-250 gap-response curve CANNOT be built from this capture; re-capture at 132 s / 110 s is required.

Markers (0x7F0) decoded and excluded from all statistics. `configured_gap_us` (from marker payload) and
`observed_onwire_bg_spacing` (from TRC) are kept separate; configured gap is never reverse-inferred.

## 1. Marker reconstruction (`marker_segments.csv`)

| file | group | index | configured gap | type | t (ms) |
|---|--:|--:|--:|---|--:|
| A_gap230_240.trc | 1 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 230 | START | 2115.941 |
| A_gap230_240.trc | 1 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 232 | START | 24973.884 |
| A_gap242_250.trc | 2 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 242 | START | 1966.403 |
| A_gap242_250.trc | 2 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 244 | START | 24813.033 |
| B_gap230_240.trc | 1 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 230 | START | 4916.345 |
| B_gap230_240.trc | 1 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 232 | START | 27766.156 |
| B_gap242_250.trc | 2 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 242 | START | 2501.818 |
| B_gap242_250.trc | 2 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 244 | START | 25335.928 |
| C_gap230_240.trc | 1 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 230 | START | 2106.081 |
| C_gap230_240.trc | 1 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 232 | START | 24960.235 |
| C_gap242_250.trc | 2 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 242 | START | 2946.928 |
| C_gap242_250.trc | 2 | Index(['file', 'strategy', 'group', 'index', 'configured_gap_us',
       'marker_type', 'marker_t_ms', 'active_count'],
      dtype='str') | 244 | START | 25787.865 |

## 2/3. Point QC (33 intended points; only 6 usable)

| strategy | configured gap | usable window s | enough(>=20s) | QC |
|---|--:|--:|:--:|---|
| A | 230 | 20.0 | True | PASS |
| A | 232 | 0.795 | False | FAIL |
| A | 242 | 20.0 | True | PASS |
| A | 244 | 1.024 | False | FAIL |
| B | 230 | 20.0 | True | PASS |
| B | 232 | 1.205 | False | FAIL |
| B | 242 | 20.0 | True | PASS |
| B | 244 | 1.648 | False | FAIL |
| C | 230 | 20.0 | True | PASS |
| C | 232 | 1.616 | False | FAIL |
| C | 242 | 20.0 | True | PASS |
| C | 244 | 2.525 | False | FAIL |

All intended gaps 232-240 and 244-250 are absent (never captured), not FAILed points.

## 4. 0x100 timing on the usable 20 s points

| strategy | gap | jitter us | p99 us | >100us% | median interval | max interval ms |
|---|--:|--:|--:|--:|--:|--:|
| A | 230 | 68.03 | 130.0 | 12.13 | 5024.0 | 5.15 |
| B | 230 | 68.33 | 129.0 | 13.08 | 5018.0 | 5.10 |
| C | 230 | 69.47 | 130.0 | 13.88 | 5031.0 | 5.17 |
| A | 242 | 73.55 | 128.0 | 12.95 | 5015.0 | 5.19 |
| B | 242 | 72.09 | 128.0 | 14.53 | 5017.0 | 5.19 |
| C | 242 | 74.01 | 129.0 | 11.53 | 5013.0 | 5.18 |

## 5/6. Background structure + occupancy (usable points; configured vs observed)

| strategy | conf gap | obs spacing median | obs mode | bg fps | occ_total% | occ_ctrl% | occ_bg% |
|---|--:|--:|--:|--:|--:|--:|--:|
| A | 230 | 230.0 | 230 | 4265 | 65.53 | 8.40 | 57.13 |
| B | 230 | 230.0 | 230 | 4320 | 62.84 | 4.98 | 57.86 |
| C | 230 | 230.0 | 230 | 4312 | 65.07 | 7.31 | 57.76 |
| A | 242 | 242.0 | 242 | 4061 | 62.80 | 8.40 | 54.39 |
| B | 242 | 242.0 | 242 | 4115 | 60.10 | 4.98 | 55.12 |
| C | 242 | 242.0 | 242 | 4109 | 62.36 | 7.32 | 55.04 |

## 7-9. Mini gap-response (usable 230, 242 + confirmatory 240 n=5)

Only 3 configured gaps have data (230, 240, 242); 240 is the confirmatory n=5 mean. This is a sparse
3-point set, NOT a resolved 230-250 curve.

| strategy | gap230 jitter | gap240 jitter (n=5) | gap242 jitter |
|---|--:|--:|--:|
| A | 68.03 | 58.67 | 73.55 |
| B | 68.33 | 58.34 | 72.09 |
| C | 69.47 | 61.24 | 74.01 |

## Similar-occupancy comparisons (<=2 pp apart)

| pair | occ a | occ b | dpp | jitter a | jitter b | djit us |
|---|--:|--:|--:|--:|--:|--:|
| Bg240_vs_Cg242 | 60.54 | 62.36 | 1.82 | 58.34 | 74.01 | 15.67 |
| Ag240_vs_Cg242 | 63.34 | 62.36 | 0.98 | 58.67 | 74.01 | 15.34 |
| Ag242_vs_Cg240 | 62.8 | 62.94 | 0.14 | 73.55 | 61.24 | 12.32 |
| Ag240_vs_Cg230 | 63.34 | 65.07 | 1.73 | 58.67 | 69.47 | 10.8 |
| Ag240_vs_Bg230 | 63.34 | 62.84 | 0.5 | 58.67 | 68.33 | 9.66 |
| Bg230_vs_Cg240 | 62.84 | 62.94 | 0.1 | 68.33 | 61.24 | 7.09 |
| Bg230_vs_Cg242 | 62.84 | 62.36 | 0.48 | 68.33 | 74.01 | 5.68 |
| Ag242_vs_Bg230 | 62.8 | 62.84 | 0.04 | 73.55 | 68.33 | 5.23 |
| Ag240_vs_Cg240 | 63.34 | 62.94 | 0.4 | 58.67 | 61.24 | 2.56 |
| Ag230_vs_Cg230 | 65.53 | 65.07 | 0.46 | 68.03 | 69.47 | 1.44 |
| Ag242_vs_Cg242 | 62.8 | 62.36 | 0.44 | 73.55 | 74.01 | 0.46 |

## Claim boundary

- Auto-sweep points are NOT independent reset replicates; treat as exploratory only. No inferential stats.
- The 230-250 response curve is NOT resolved (only 3 gaps have data). No peak/valley/monotonicity claim
  can be made across 230-250 from this capture.
- reconstructed occupancy != PCAN actual load; jitter != latency; observed BG spacing is endogenous.

## Figures

- `figures/1_gap_vs_jitter.png`
- `figures/2_gap_vs_occupancy.png`
- `figures/3_occupancy_vs_jitter.png`
- `figures/4_gap_vs_observed_bg_spacing.png`
- `figures/5_gap_vs_bg_fps.png`
