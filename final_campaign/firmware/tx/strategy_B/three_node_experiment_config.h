#ifndef THREE_NODE_EXPERIMENT_CONFIG_H
#define THREE_NODE_EXPERIMENT_CONFIG_H

/*
 * 3-node external-background experiment configuration  (CONTROL TX node)
 * ---------------------------------------------------------------------
 * This header is the SINGLE place to switch a verified 2-node Control TX
 * project into its 3-node role. It changes NOTHING about the CAN-FD bit
 * timing, FSP/clock configuration, control signal layout, IDs, DLCs,
 * periods, payloads, or measurement markers. It only decides whether the
 * legacy same-node dummy / bus-load traffic is transmitted from THIS node.
 *
 *   USE_EXTERNAL_BACKGROUND_NODE == 1  (3-node, default here)
 *       The same-node dummy generator is NOT called. Zero dummy
 *       R_CANFD_Write() on this node. Bus-load / background traffic is
 *       produced by the dedicated external node (canfd_background_tx_3node).
 *       Control A/B/C scheduling is byte-for-byte the verified behavior.
 *
 *   USE_EXTERNAL_BACKGROUND_NODE == 0  (legacy 2-node)
 *       Restores the original same-node dummy traffic. Provided ONLY so the
 *       change is fully reversible; do not use it for 3-node measurements.
 *
 * The dummy generator code itself is intentionally left compiled (not
 * deleted) so this switch is reversible and diff-reviewable.
 */
#define USE_EXTERNAL_BACKGROUND_NODE (1)

#endif /* THREE_NODE_EXPERIMENT_CONFIG_H */
