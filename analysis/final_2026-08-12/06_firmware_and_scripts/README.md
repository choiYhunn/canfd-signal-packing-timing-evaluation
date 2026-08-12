# Firmware + analysis scripts (reproducibility)

Background/traffic node firmware only. CONTROL A/B/C TX, RX-actuator, FSP generated code, CAN bit
timing, and clock config were **not** modified for the sweep work. Dummy ID/DLC/payload unchanged.
Both sweep files below are copies of the verified `canfd_background_tx_3node` generator with additions
marked `3NODE-SWEEP` / `3NODE-CONFIRM`; the DWT-paced dummy scheduler was not altered.

## Files
- `sweep_hal_entry.c` — coarse configured-gap sweep (Dataset D). `g_sweep_group`: 1 = 230/232/234/236/238/240,
  2 = 242/244/246/248/250. 2 s settle + 20 s measure = 22 s/point; auto-stop, no auto-repeat.
- `confirm_hal_entry.c` — independent-reset confirmation (Dataset E). Same engine; 4 gaps only,
  3 permuted orders: `g_sweep_group` 1 = [238,240,244,250], 2 = [250,244,240,238], 3 = [244,238,250,240].
  2 s settle + **30 s** measure = 32 s/point.
- `analyze_3node_n5.py`, `analyze_fixed_bg.py`, `analyze_gap_sweep_full.py`, `analyze_gap_confirm.py` —
  drivers for Datasets B/C/D/E. Each imports the verified metric module
  `analysis/scripts/analyze_fixed2_64b_n10.py` (interval_metrics / wire_breakdown / EXPECTED); no metric redefined.

## Marker (both sweeps, identical encoding)
- Standard ID **0x7F0** (unused: control 0x100–0x130, dummy 0x300–0x30F; 0x7F0 is far above, lowest priority),
  sent on idle control mailbox MB5. One START marker per gap; one END marker after the last gap.
- Payload: `[0..1]=A5 5A` magic, `[2]=group`, `[3]=index`, `[4:6]=configured gap µs (little-endian)`,
  `[6]=0x01 START / 0xEE END`, `[7]=active_count (8)`.
- **Analysis excludes 0x7F0** from occupancy / BG fps / total fps / jitter / ACF. Each point drops the
  first 2 s (settle) after its START marker and analyses the following measurement window.

## Gap application and timing
- The sweep sets `g_dummy_load_mode = DUMMY_LOAD_60` (active_count 8, the M regime) and writes the current
  gap into the existing live variable `g_dummy_60_min_gap_us`; the verified generator re-seeds on the change.
  `configured min gap` is the firmware input, **not** an exact wire period — analyses keep `configured_gap_us`
  and `observed_onwire_bg_spacing` separate.
- DWT->CYCCNT is 32-bit at 200 MHz (~21.5 s wrap), so a 22 s / 32 s dwell is **not** timed with a single
  cycle delta; the sweep accumulates small per-iteration µs deltas into a uint32 counter. Offline analysis
  segments strictly by the START/END markers, not by MCU dwell.
