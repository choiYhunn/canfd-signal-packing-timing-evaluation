
# CAN-FD Signal Packing Timing Evaluation

This release candidate studies how frame packing changes CAN-FD RX inter-arrival jitter under a fixed 64-byte mixed-period workload.

Key results: A60 59.764 us, C60 22.098 us, difference 37.667 us; reconstructed occupancy difference -0.091382 pp (strict matched); 120/120 files passed QC; no >6 ms gap or frame-loss candidate was found.

The TRC metric is not one-way latency, reconstructed occupancy is not measured PCAN actual load, and the Scope marker study is a separate campaign. See `README_KO.md` for the full method, claims, limitations, and repository structure.

License status: **LICENSE PENDING**.
