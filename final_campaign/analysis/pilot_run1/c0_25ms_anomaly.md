# C0 baseline — 25 ms 0x100 inter-arrival anomaly (raw look)

Source: `3node/c0_1.trc` (C strategy, baseline, dummy OFF, PCAN Listen-Only, run1).
Raw file never modified. This is a descriptive raw-trace look only; no root cause
is asserted from a Listen-Only capture.

## The event
- Whole file: **6232 frames, all ID 0x100** (C is 1-pack: only 0x100 @5 ms, and
  baseline has dummy OFF → 0x100 is the *only* traffic present). Capture span ≈ 31.176 s.
- Exactly **one** inter-arrival gap > 6 ms in the whole file:
  **25.000 ms** between 0x100 message #867 @ 4.333059 s and #868 @ 4.358059 s.
- PCAN message **Number is contiguous across the gap: 867 → 868 (Δ=1)** — PCAN did
  not record/flag any frame in that window; it stored nothing, then resumed.
- Cadence before and after is clean ~5 ms; the post-gap frame lands back exactly on
  the original 5 ms phase grid (4.333059 + 25000 = 4.358059).

## Raw frame sequence, window ±50 ms around the gap (all IDs)
| PCAN Number | t (s) | Δt_prev (µs) | ID | DLC |
|---:|---:|---:|---|---:|
| 858 | 4.288059 | — | 0x100 | 64 |
| 859 | 4.293058 | 4999 | 0x100 | 64 |
| 860 | 4.298059 | 5001 | 0x100 | 64 |
| 861 | 4.303058 | 4999 | 0x100 | 64 |
| 862 | 4.308057 | 4999 | 0x100 | 64 |
| 863 | 4.313061 | 5004 | 0x100 | 64 |
| 864 | 4.318060 | 4999 | 0x100 | 64 |
| 865 | 4.323060 | 5000 | 0x100 | 64 |
| 866 | 4.328059 | 4999 | 0x100 | 64 |
| 867 | 4.333059 | 5000 | 0x100 | 64 |
| **868** | **4.358059** | **25000** | **0x100** | **64** | ← 25 ms gap |
| 869 | 4.363063 | 5004 | 0x100 | 64 |
| 870 | 4.368062 | 4999 | 0x100 | 64 |
| 871 | 4.373061 | 4999 | 0x100 | 64 |
| 872 | 4.378061 | 5000 | 0x100 | 64 |
| 873 | 4.383060 | 4999 | 0x100 | 64 |
| 874 | 4.388062 | 5002 | 0x100 | 64 |
| 875 | 4.393061 | 4999 | 0x100 | 64 |
| 876 | 4.398061 | 5000 | 0x100 | 64 |
| 877 | 4.403060 | 4999 | 0x100 | 64 |

Normal 0x100 interval across the file: mean 5000.2 µs, median 5000.0 µs, min 4899, max 5101.
No error frame / ESI / bus-off indication anywhere near the event.

## Questions asked
- **A. Was only 0x100 empty for 25 ms?** 0x100 is absent for the 25 ms window — but
  in this trace 0x100 is the *only* ID, so "only 0x100" and "all traffic" are the
  same set here.
- **B. Did 0x110 / other C control frames continue during the gap?** N/A by design —
  C baseline transmits **no** other control frame; the entire file contains only
  0x100 (0 non-0x100 frames). So there is no second control stream to have continued.
- **C. Were all CAN frames absent in the same window?** Yes. Since 0x100 is the sole
  traffic, the observed bus shows **no frame at all for 25 ms**.
- **D. Is there a capture-wide timestamp gap?** Yes — a 25 ms span with zero recorded
  frames, PCAN Number contiguous (867→868), i.e. PCAN observed/stored nothing in that
  window rather than dropping numbered frames.

## What the 25 ms span means (carefully)
The 25 ms interval spans **five** nominal 5 ms periods. If the source kept releasing
0x100 on its normal 5 ms schedule, then **four expected intermediate 0x100 arrivals
are absent** from the trace and the stream re-aligns exactly on the original phase.
(We deliberately do **not** phrase this as "5 missed frames".)

## How far root cause can be narrowed (and where it stops)
Narrowed:
- It is a **single, isolated** 25.000 ms event — the only >6 ms gap in the file.
- It is **bus-wide** (0x100 is the only traffic), so **arbitration / bus contention
  is not a plausible cause**: at baseline there is a single periodic talker and
  nothing to arbitrate against.
- No error frame / ESI / bus-off around it; cadence is otherwise clean 5 ms and
  resumes exactly on the prior phase grid.

Cannot be determined from this Listen-Only trace:
- Whether the bus was genuinely idle for 25 ms (control-node TX paused / inhibited /
  transient at the sender) **or** whether 0x100 frames were on the wire but the PCAN
  host capture (USB scheduling / driver buffer) silently missed ~25 ms. PCAN Number
  continuity does **not** disambiguate, because PCAN numbers only what it stores.
- Disambiguation needs a **second simultaneous observation channel** (e.g. a scope/GPIO
  marker on the control-node TX pin, or an independent logger) — a follow-up item, not
  a claim from this pilot.

Bottom line: a single isolated bus-wide 25 ms silence in one baseline trace; not
arbitration-related; host-capture-stall vs sender-side-pause is **unresolved** and
must not be asserted from Listen-Only data.
