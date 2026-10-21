# 3-node CAN-FD timing-mechanism forensic analysis (timestamp-only)

> ## CORRECTION / CAUSAL AUDIT (2026-08-12, supersedes all causal claims below)
>
> This analysis's `BG gap` / `bg_gap_med` is **NOT a configured value**. It is
> `median(diff(timestamps of all 0x300-0x30F frames))` — an **observed, endogenous**
> spacing that CAN arbitration, serialization, and control-frame insertion themselves
> perturb. `beat_remainder` was mislabeled "5000 mod gap": it is actually the
> **distance to the nearest integer multiple of gap**, `min(5000 % gap, gap - 5000 % gap)`
> (for gap 240 that is 40, whereas 5000 mod 240 = 200), and it was computed on the
> endogenous median.
>
> **RETRACTED:** (a) that the user changed the A60 gap; (b) that "240<->238 live tuning
> caused the A60 run1 regime flip"; (c) that A60's cause is "confirmed"; (d) the
> commensurability-as-cause chain for A60. The user did **not** change the A60 gap
> (nominal 240). Provenance audit (`bg_gap_provenance_audit.csv`): the **mode** of
> observed BG spacing is **240 us for every run 1-8**; only the median differs (240 vs
> 237/238) because run2-8 carry slightly more sub-240 spacings (p10 168-170 vs run1 176;
> IQR 9-10 vs 6). That median shift is a symptom that co-varies with the jitter regime,
> not an independent cause. What survives is **association only**; see the "Surviving
> timestamp evidence" section appended at the end of this file. The commensurability
> paragraphs and answer 2 below are retained for transparency but are RETRACTED as causal.

Uses ONLY existing 3-node TRC. No new experiment / firmware / build / Shared Brain change.

**Metrics.** `phase_residual` = deviation of each 0x100 arrival from a robust absolute 5 ms grid (t0 = median(t_k - k*5000)); `inter-arrival error` = diff(t)-5000 (kept separate). `phi` = relative background phase = (t_100 - t_bg_prev)/(t_bg_next - t_bg_prev), computed only when the enclosing BG interval <= 1.6x the run's median BG gap (spans-a-missing-BG samples excluded).

**Claim boundary (enforced).** PCAN timestamps are bus-monitor arrival times, NOT proven SOF, NOT application release times. Everything below is an *alignment / association signature*; no mailbox waiting time or arbitration cause is directly measured.

## Per-run summary (commensurability + determinism)

`beat_remainder` = 5000 mod (median BG gap), folded to [0, gap/2]; `beat_cycles` = gap/remainder = how many 0x100 cycles to walk one full BG interval. Small beat_cycles -> fast phase sweep.

| cond | run | jitter us | bg_gap_med us | beat_rem us | beat_cycles | ACF lag1 | dom lag | dom ACF | occ% |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| A30 | 2 | 13.73 | 617.0 | 64.0 | 9.64 | -0.008 | 113 | 0.054 | 29.78 |
| A30 | 3 | 13.60 | 621.0 | 32.0 | 19.41 | -0.009 | 93 | 0.056 | 29.78 |
| A60 | 1 | 58.88 | 240.0 | 40.0 | 6.00 | -0.121 | 5 | 0.583 | 63.34 |
| A60 | 2 | 22.93 | 238.0 | 2.0 | 119.00 | -0.189 | 50 | 0.237 | 63.74 |
| A60 | 3 | 22.53 | 238.0 | 2.0 | 119.00 | -0.169 | 50 | 0.199 | 63.74 |
| A60 | 4 | 23.34 | 237.0 | 23.0 | 10.30 | -0.225 | 50 | 0.209 | 63.74 |
| A60 | 5 | 23.45 | 238.0 | 2.0 | 119.00 | -0.229 | 50 | 0.233 | 63.75 |
| A60 | 6 | 23.50 | 238.0 | 2.0 | 119.00 | -0.234 | 50 | 0.238 | 63.74 |
| A60 | 7 | 22.93 | 238.0 | 2.0 | 119.00 | -0.200 | 50 | 0.246 | 63.75 |
| A60 | 8 | 23.69 | 238.0 | 2.0 | 119.00 | -0.233 | 50 | 0.222 | 63.75 |
| A80 | 2 | 71.00 | 168.0 | 40.0 | 4.20 | -0.590 | 19 | 0.875 | 83.29 |
| A80 | 3 | 71.70 | 168.0 | 40.0 | 4.20 | -0.590 | 19 | 0.892 | 83.29 |
| B30 | 2 | 40.23 | 617.0 | 64.0 | 9.64 | -0.240 | 115 | 0.709 | 26.66 |
| B30 | 3 | 43.94 | 617.0 | 64.0 | 9.64 | -0.374 | 148 | 0.770 | 26.74 |
| B60 | 1 | 62.03 | 234.0 | 86.0 | 2.72 | -0.211 | 29 | 0.838 | 61.70 |
| B60 | 2 | 61.47 | 234.0 | 86.0 | 2.72 | -0.214 | 29 | 0.833 | 61.69 |
| B60 | 3 | 61.27 | 234.0 | 86.0 | 2.72 | -0.213 | 29 | 0.843 | 61.70 |
| B60 | 4 | 61.69 | 234.0 | 86.0 | 2.72 | -0.214 | 29 | 0.835 | 61.70 |
| B60 | 5 | 61.60 | 234.0 | 86.0 | 2.72 | -0.212 | 29 | 0.841 | 61.69 |
| B80 | 2 | 67.03 | 167.0 | 10.0 | 16.70 | -0.381 | 7 | 0.955 | 83.11 |
| B80 | 3 | 66.68 | 167.0 | 10.0 | 16.70 | -0.379 | 7 | 0.967 | 83.11 |
| C30 | 2 | 40.38 | 608.0 | 136.0 | 4.47 | -0.253 | 75 | 0.823 | 29.00 |
| C30 | 3 | 41.04 | 613.0 | 96.0 | 6.39 | -0.238 | 38 | 0.909 | 29.00 |
| C60 | 1 | 24.76 | 236.0 | 44.0 | 5.36 | -0.282 | 264 | 0.073 | 63.31 |
| C60 | 2 | 24.90 | 236.0 | 44.0 | 5.36 | -0.257 | 6 | 0.063 | 63.30 |
| C60 | 3 | 23.69 | 236.0 | 44.0 | 5.36 | -0.221 | 211 | 0.098 | 63.31 |
| C60 | 4 | 25.30 | 236.0 | 44.0 | 5.36 | -0.284 | 213 | 0.081 | 63.30 |
| C60 | 5 | 25.23 | 236.0 | 44.0 | 5.36 | -0.282 | 54 | 0.067 | 63.30 |
| C80 | 2 | 71.34 | 168.0 | 40.0 | 4.20 | -0.610 | 8 | 0.819 | 82.82 |
| C80 | 3 | 71.14 | 168.0 | 40.0 | 4.20 | -0.611 | 8 | 0.816 | 82.82 |

## Predecessor / blocking context (does big error follow background?)

| cond | %prev=BG | mean|iaErr| after BG | mean|iaErr| after control | mean bg burst len |
|---|--:|--:|--:|--:|
| A60 | 100.0 | 11.0 | nan | 20.6 |
| B60 | 100.0 | 49.2 | nan | 21.2 |
| C60 | 100.0 | 10.3 | nan | 20.9 |
| A30 | 100.0 | 3.6 | nan | 8.0 |
| B30 | 100.0 | 23.0 | nan | 8.1 |
| C30 | 100.0 | 21.5 | nan | 8.1 |
| A80 | 100.0 | 67.8 | nan | 28.1 |
| B80 | 100.0 | 59.7 | nan | 29.4 |
| C80 | 100.0 | 67.9 | nan | 28.4 |

## Relative BG phase (phi) response

`phase_mod_amplitude` = peak-to-trough of binned median |inter-arrival error| across phi. Large amplitude = 0x100 timing is strongly modulated by where it lands in the BG cycle (alignment/blocking-sensitive); ~flat = insensitive to BG phase.

| group | n valid | median |iaErr| us | phase_mod_amplitude us | phase_res_std us |
|---|--:|--:|--:|--:|
| B60 | 28382 | 51.0 | 1.0 | 290.8 |
| C60 | 27569 | 3.0 | 0.0 | 285.4 |
| A60_run1 | 3398 | 42.0 | 2.5 | 230.6 |
| A60_run2to8 | 36006 | 2.0 | 0.0 | 317.9 |
| A30 | 12267 | 1.0 | 0.0 | 368.5 |
| B30 | 12221 | 2.0 | 0.0 | 306.8 |
| C30 | 12155 | 1.0 | 0.0 | 363.8 |
| A80 | 1 | 105.0 | 0.0 | 0.0 |
| B80 | 10961 | 47.0 | 0.0 | 291.6 |

## Figures

- `figures/1_b60_c60_phi_phaseresidual.png`
- `figures/2_b60_c60_phi_iaerror.png`
- `figures/3_a60_run1_vs_rest_phasemap.png`
- `figures/4_load_strategy_phase_response.png`
- `figures/5_acf_comparison.png`
- `figures/6_event_centered_timeline.png`

## Interpretation and answers (timestamp-only forensic)

**Two regimes, cleanly separated by the ACF (Fig5), NOT by instantaneous BG phase.** The instantaneous relative BG phase phi does NOT gate per-frame error (phase-response amplitude ~0-2.5 us for every condition; Fig1-3 medians are flat in phi). The real signature is a *multi-cycle deterministic beat* in the 0x100 inter-arrival error:
- **Beat regime (high jitter):** B60 (all runs) ACF ~0.84 at a stable lag (29), reproduced across 5 runs; A60 run1 ACF ~0.58. Median |error| 42-51 us; |error| after a background frame 49 us (B60).
- **Quiet regime (low jitter):** C60 (all runs) ACF ~0.07 (near white noise); A60 run2-8 ACF ~0.22. Median |error| 2-3 us; |error| after background 10 us.

**Commensurability governs the beat-susceptible strategies.** beat_remainder = 5000 mod (BG gap): A60 gap 240 us -> rem 40 -> strong beat (jitter 59); A60 gap 237/238 us -> rem 23/2 -> beat frozen (jitter 23); B60 gap 234 us -> rem 86 -> strong beat (jitter 62). For strategy A the small ~2 us live gap change (240->238) crosses the boundary at fixed occupancy (63.3 vs 63.7 %). BUT C60 gap 236 us -> rem 44 (comparable to A's 240) yet stays quiet -> single-frame packing (C, one 64 B 0x100) is intrinsically beat-immune, while multi-frame packing (A, B) is beat-susceptible and then modulated by commensurability. Combined: jitter ~ (strategy beat-susceptibility) x (gap commensurability); C susceptibility ~ 0.

**Answers to the core questions:**
1. *B60 vs C60 explained by phase/blocking signature?* Partly and specifically: at matched occupancy and near-equal BG gap, B60 carries a strong DETERMINISTIC, run-reproducible control x background beat (large |error| after BG, high ACF) that single-frame C suppresses. Consistent with non-preemptive control x background interaction. It is a multi-cycle beat, not a per-frame phi gate, and it is association from bus-monitor timestamps, not arbitration proof.
2. *A60 run1 different alignment?* Yes - concretely a BG-gap commensurability regime: run1 gap 240 us (rem 40, fast beat, jitter 59) vs run2-8 gap 237-238 us (rem <=23, frozen beat, jitter 23), same occupancy. The earlier 'random relative-phase' guess is refined to a deterministic gap-setting (the live +/-1 us tuning) effect.
3. *80 % convergence explained by microstructure?* Yes, consistent with blocking saturation: at occupancy ~83 % all strategies converge to 67-71 us with strongly deterministic ACF (0.80-0.97) and near-identical |error|-after-BG (60-68 us). Near-saturation every 0x100 is displaced by ~maximal BG blocking regardless of packing, swamping the strategy beat.
4. *How far can a paper claim go on existing traces?* CAN state: packing strategy changes control inter-arrival regularity via a deterministic, repeating control x background alignment (beat) that is strong for multi-frame packing and suppressed for single-frame packing; for beat-susceptible strategies jitter is governed by BG-gap commensurability with the 5 ms period (A60 240<->238 flip at fixed occupancy); strategies converge at ~80 % (saturation); all as timestamp association consistent with non-preemptive blocking. CANNOT state: measured release/mailbox waiting time; PCAN timestamp = SOF; arbitration proven as cause; single-factor (frame-length or write-count) causation; C universally superior.
5. *Is a phase-sweep experiment needed?* Yes, and now sharply specified. Existing traces confound gap x strategy x phase (the 240/238 flip was accidental, uncontrolled live tuning), and the uncontrolled gap points are not perfectly monotonic in the remainder, so causality is not pinned. A controlled BG-gap/commensurability sweep at 60-target (step BG gap ~1-2 us across ~230-245 us for A, B and control C, occupancy matched) should show a jitter resonance with minima near commensurate gaps (5000 mod gap ~ 0, e.g. 238) and maxima at incommensurate gaps - for A/B but not C. Adding CONTROL-TX / BG-TX GPIO or TXD scope would convert the timestamp beat/blocking association into a directly observed release-vs-blocking measurement and remove the SOF/release caveat.

## Surviving timestamp evidence (causal interpretation removed)

**A. Directly observed in the traces (facts):**
- B60 inter-arrival-error ACF is strong and REPRODUCED across all 5 runs: dominant lag 29, ACF 0.833-0.843 (jitter 61.3-62.0 us).
- C60 ACF is low across all 5 runs: 0.063-0.098 (jitter 23.7-25.3 us), i.e. near-white-noise inter-arrival error.
- A60 run1 differs from run2-8: jitter 58.9 vs 22.5-23.7 us; ACF 0.58 @ lag 5 (run1) vs ~0.20-0.25 @ lag 50 (run2-8).
- A60 observed BG-spacing distribution differs slightly by run (run1: median 240, IQR 6, p10 176; run2-8: median 237/238, IQR 9-10, p10 168-170) while the **mode is 240 us for all 8 runs**.
- occupancy is matched across the compared runs (A60 63.3-63.8 %, B60 61.7 %, C60 63.3 %).

**B. Hypotheses the traces are CONSISTENT WITH (not established):**
- A deterministic control x background *beat/alignment* could produce the high-jitter, high-ACF regime for multi-frame packing (A, B), which single-frame packing (C) appears to suppress.
- A60 run1's different inter-arrival sequence is *associated* with a different observed BG temporal structure; a shared latent alignment/relative-phase state on that acquisition could drive both. Direction of causation is unknown.

**C. NOT sayable from these traces:**
- That any configured gap changed (it did not for A60), or that a gap change caused the A60 flip.
- That observed BG spacing is an independent cause of jitter — it is endogenous (arbitration/serialization/control-insertion perturb it), so it cannot be used as a cause without a controlled input.
- Application release / mailbox waiting time; arbitration as proven cause; PCAN timestamp = SOF; C universally superior; any single-factor causation.

**Methodological point (unchanged in value):** per-run BG gap and, ideally, the actual configured background-node gap must be logged, and only a controlled BG-gap / relative-phase sweep (independent input) can turn the above association into a causal statement.
