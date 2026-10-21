# Firmware — 3-node

Only user-authored/custom `src` files from the 3-node measurement projects are included. Renesas FSP SDK sources, generated vendor trees (`ra/`, `ra_gen/`), build outputs, device binaries, and IDE/launch metadata are excluded. Project configuration and build instructions remain in the private reproducibility package pending license review.

## Role split

The 3-node topology is selected at compile time by `three_node_experiment_config.h`:

- **`tx/strategy_A|B|C/`** — Node1 Control TX. Fixed-payload A/B/C signal-packing frames (identical `canfd_signalset_64b.h` across strategies). No dummy/background traffic is generated here anymore.
- **`rx/strategy_A|B|C/`** — Node3 RX. Accept-all AFL; validates layout and fixed payloads.
- **`background_tx/`** — Node2 external Background TX. Generates the 0x300–0x30F load frames (12-byte CAN-FD, byte-identical payload) at a calibrated gap targeting 30 / 60 / 80 % total bus load.
- **`background_tx_gap_sweep/`**, **`background_tx_gap_confirm/`** — Background TX variants used for the gap-sweep and gap-confirmation sub-studies (`../analysis/gap_sweep/`).

## Fixed-payload rule

Every repeated frame of a given ID carries a byte-identical payload, so bit-stuffing pattern differences between strategies are controlled as far as possible. The sequence counter increments internally but is never written into the payload. This fixed-payload constraint is the defining property of this campaign and must not be reverted to a dynamic-payload design.

## Note

A host compile/link success (if reproduced from the private package) proves build correctness only, not hardware timing behavior. All bus-level claims come from PCAN traces, analyzed under `../analysis/`.
