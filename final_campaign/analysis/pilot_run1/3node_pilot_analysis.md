# 3-node external-background CAN-FD pilot (run1, n=1)

- Acquired 2026-08-11. Raw TRC: `<private>/3node` (12 files, never modified).
- 3-node: Node1 CONTROL TX / Node2 external BACKGROUND TX / Node3 RX-PWM; PCAN Listen-Only.
- Metrics reuse the verified n=10 module `trace_fixed2/analysis_n10/analyze_fixed2_64b_n10.py` (`interval_metrics`, `wire_breakdown`, `expected_kind`, `EXPECTED`, `EXPECTED_PAYLOAD`).
- `reconstructed occupancy` is a payload-aware ISO airtime estimate, **not** PCAN actual Mean Load (not saved this campaign).
- `jitter` = SD of consecutive 0x100 inter-arrival gaps. It is NOT one-way / end-to-end latency.

## A. QC: 12/12 PASS

Naming-vs-content mapping was verified, not assumed:
- Letter (A/B/C) confirmed by observed 0x100 DLC = A:8B / B:32B / C:64B (`qc_letter_mapping_ok`).
- Number (0/1/2/3) confirmed by dummy presence: baseline dummy-OFF vs 30/60/80 dummy-ON (`qc_number_dummy_mapping_ok`), plus monotonic occupancy ordering:
  - A: occupancy baseline<30<60<80 monotonic = True (8.40, 29.71, 63.34, 83.29)
  - B: occupancy baseline<30<60<80 monotonic = True (4.98, 26.66, 61.70, 83.11)
  - C: occupancy baseline<30<60<80 monotonic = True (7.31, 28.98, 63.31, 82.82)

Per-file QC covered: parse success, duration, frame count, timestamp monotonicity, Standard-ID, CAN-FD/BRS, per-ID count/DLC, control layout vs A/B/C expected, 0x300-0x30F presence, baseline dummy-absence, fixed-payload byte-identity, unexpected IDs, ESI/error frames, 0x100 count, gap>6ms, 9-11ms loss candidates. Details: `qc_by_file.csv`.

### Data-quality note (single-event anomalies)

- **Cbaseline**: 1 inter-arrival gap>6 ms (max interval 25.0 ms). This single event dominates `Cbaseline` jitter SD (253.4 us); removing it leaves an SD in line with the other baselines (~6 us). Reported, not discarded; the raw TRC is unchanged. Cause (host-side capture hiccup vs control-node stall) cannot be identified from a Listen-Only trace and is a follow-up item.

## B/C. 12-condition pilot summary

| cond | dummy_gap_us | occupancy% | bg_fps | jitter_us | p99_us | >100us% | gap>6ms | 9-11ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Abaseline |  | 8.40 | 0.0 | 5.25 | 5.0 | 0.05 | 0 | 0 |
| Bbaseline |  | 4.98 | 0.0 | 5.54 | 3.0 | 0.11 | 0 | 0 |
| Cbaseline |  | 7.31 | 0.0 | 253.44 | 4.7 | 0.06 | 1 | 0 |
| A30 | 627 | 29.71 | 1593.6 | 23.76 | 124.0 | 3.24 | 0 | 0 |
| B30 | 616 | 26.66 | 1620.8 | 40.67 | 125.0 | 5.11 | 0 | 0 |
| C30 | 617 | 28.98 | 1620.0 | 40.70 | 125.0 | 5.66 | 0 | 0 |
| A60 | 240 | 63.34 | 4101.6 | 58.88 | 132.0 | 11.03 | 0 | 0 |
| B60 | 235 | 61.70 | 4234.5 | 62.03 | 129.0 | 12.56 | 0 | 0 |
| C60 | 238 | 63.31 | 4180.2 | 24.76 | 126.0 | 3.24 | 0 | 0 |
| A80 | 170 | 83.29 | 5627.8 | 71.46 | 112.0 | 11.89 | 0 | 0 |
| B80 | 168 | 83.11 | 5877.1 | 66.97 | 117.0 | 16.68 | 0 | 0 |
| C80 | 170 | 82.82 | 5674.7 | 71.41 | 106.0 | 4.58 | 0 | 0 |

## C. 60-target load-matching quality (A2 / B2 / C2)

| cond | dummy_gap_us | reconstructed occupancy% | jitter_us | p99_us | >100us% |
|---|---:|---:|---:|---:|---:|
| A60 | 240 | 63.3437 | 58.88 | 132.0 | 11.03 |
| B60 | 235 | 61.6972 | 62.03 | 129.0 | 12.56 |
| C60 | 238 | 63.3082 | 24.76 | 126.0 | 3.24 |

Occupancy spread across 60-target A/B/C = 1.6465 pp (min 61.6972, max 63.3437).

## D. Comparison vs 2-node fixed-payload n=10 (Shared Brain source of truth)

2-node n=10 is the canonical prior; the key result was A60 vs C60. Values below are descriptive only.

| cond | 3node n=1 jitter | 2node n=10 jitter | 3node >100us% | 2node >100us% | 3node occ% | 2node occ% |
|---|---:|---:|---:|---:|---:|---:|
| A60 | 58.88 | 59.8 | 11.03 | 13.50 | 63.34 | 63.25 |
| B60 | 62.03 | 61.8 | 12.56 | 8.33 | 61.70 | 61.92 |
| C60 | 24.76 | 22.1 | 3.24 | 2.75 | 63.31 | 63.34 |
| A80 | 71.46 | 67.0 | 11.89 | 2.05 | 83.29 | 83.34 |
| B80 | 66.97 | 69.5 | 16.68 | 10.11 | 83.11 | 82.26 |
| C80 | 71.41 | 73.8 | 4.58 | 18.98 | 82.82 | 82.82 |
| A30 | 23.76 | 36.2 | 3.24 | 4.98 | 29.71 | 29.58 |
| B30 | 40.67 | 51.6 | 5.11 | 10.55 | 26.66 | 33.13 |
| C30 | 40.70 | 36.1 | 5.66 | 5.45 | 28.98 | 33.17 |

### A60 vs C60 verdict (single trace)

n=1 pilot: **reproduction candidate consistent with the prior direction** (A60 jitter 58.9 vs C60 24.8 us, A60-C60=+34.1 us; 2-node n=10 was +37.7 us).

## E. External-background exploratory: 0x100 predecessor class

Frame immediately preceding each 0x100 is classified (background 0x300-0x30F / other_control / other) and inter-arrival error is described per class. PCAN timestamps do not reveal application release time, so this is association only — NOT proof of non-preemptive blocking.

| cond | predecessor | n | share% | mean|err| | p95|err| | >100us% |
|---|---|---:|---:|---:|---:|---:|
| A60 | background | 4199 | 100.0 | 44.3 | 126.0 | 11.0 |
| B60 | background | 4489 | 100.0 | 49.5 | 120.0 | 12.6 |
| C60 | background | 4565 | 100.0 | 10.3 | 31.0 | 3.2 |

## F. Claim boundaries (n=1)

- MUST NOT say: reproduced / significant / cause proven / C is superior / arbitration confirmed.
- No bootstrap / CI / significance test is applied to a single run. Thousands of frames within one trace are NOT independent experimental replicates.
- `reconstructed occupancy` != PCAN actual bus load. `jitter` != latency.
- Next: repeat 60-target (and 30/80) for n>=5-10 with per-run actual PCAN Mean/Min/Max Load recorded.

## Figures

- `figures/01_jitter_12conditions.png`
- `figures/02_jitter_by_target_ABC.png`
- `figures/03_60target_A2B2C2.png`
- `figures/04_interarrival_error_ecdf.png`
- `figures/05_reconstructed_occupancy_12conditions.png`
- `figures/06_timeseries_A60.png`
- `figures/06_timeseries_C60.png`
