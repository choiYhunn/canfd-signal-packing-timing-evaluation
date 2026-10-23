# A-strategy gap-confirmation (238/240/244/250, 3 order-permuted runs)

Independent reset per run; auto-sweep order permuted (r1 238->250, r2 250->238, r3 244/238/250/240).
Marker 0x7F0 excluded. configured gap vs observed on-wire BG spacing kept separate. No causal claim.

## Acquisition — all 3 complete, QC 12/12 not-FAIL

| run | file | dur s | frames | markers | START | END | decoded sequence |
|---|---|--:|--:|--:|--:|--:|---|
| r1 | A_confirm_r1.trc | 135.6 | 626757 | 5 | 4 | 1 | 238/240/244/250 |
| r2 | A_confirm_r2.trc | 135.5 | 626753 | 5 | 4 | 1 | 250/244/240/238 |
| r3 | A_confirm_r3.trc | 136.3 | 627281 | 5 | 4 | 1 | 244/238/250/240 |

## Result — 0x100 jitter (us): gap x run

| gap | r1 | r2 | r3 | mean±SD | CV% | coarse(n=1) | 5000/gap |
|--:|--:|--:|--:|---|--:|--:|--:|
| 238 | 26.17 | 26.66 | 26.27 | 26.37±0.26 | 0.97 | 25.49 | 21.008 |
| 240 | 56.65 | 56.93 | 56.94 | 56.84±0.16 | 0.28 | 56.12 | 20.833 |
| 244 | 75.61 | 76.20 | 76.07 | 75.96±0.31 | 0.40 | 79.13 | 20.492 |
| 250 | 21.76 | 21.62 | 22.12 | 21.83±0.25 | 1.17 | 22.67 | 20.000 |

## Background / occupancy (configured vs observed), per gap (mean of 3 runs)

| gap | occ_total% | observed BG spacing median | observed mode | BG fps |
|--:|--:|--:|--:|--:|
| 238 | 63.69 | 237.0 | 236 | 4127 |
| 240 | 63.22 | 240.0 | 242 | 4092 |
| 244 | 62.42 | 242.0 | 242 | 4033 |
| 250 | 61.42 | 248.0 | 248 | 3958 |

## Reproducibility of the 238<240<244, 250-low pattern

- **r1**: 238=26.17, 240=56.65, 244=75.61, 250=21.76 -> 238<240 True, 240<244 True, 250<244 True, 250 lowest True
- **r2**: 238=26.66, 240=56.93, 244=76.20, 250=21.62 -> 238<240 True, 240<244 True, 250<244 True, 250 lowest True
- **r3**: 238=26.27, 240=56.94, 244=76.07, 250=22.12 -> 238<240 True, 240<244 True, 250<244 True, 250 lowest True

Each configured gap was observed at different sequence positions across the three reset runs, and the
within-gap run-to-run SD remained <=0.31 us. Thus the gap-dependent ordering was robust to the three
tested sweep orders, with no evidence of a large order/carry-over effect in these runs. (The 3 permuted
orders are not a full gap x position factorial, so this is a robustness check, not a variance-decomposition
estimate of a pure order effect; any between-position variance figure in the helper script is descriptive
only and not used as causal/statistical evidence.)

## Claim boundary

- Repeatable resonance-like timing pattern consistent with the relative timing/commensurability between
  the 5 ms control period and periodic background traffic. NOT proof of commensurability/arbitration/
  phase-resonance as cause. configured gap != exact wire period; reconstructed occupancy != PCAN load.
- inter-arrival jitter (= SD of d_k - d_{k-1} for arrival a_k = k*T + d_k) measures cycle-to-cycle delay
  variation, NOT absolute one-way latency. A jitter valley is NOT a "minimum response time" or best
  deadline performance; absolute latency was not measured here.

## Figures

- `figures/1_gap_vs_jitter_3runs.png`
- `figures/2_per_gap_run_scatter.png`
