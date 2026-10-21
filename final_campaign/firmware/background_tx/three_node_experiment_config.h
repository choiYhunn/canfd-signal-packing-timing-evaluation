#ifndef THREE_NODE_EXPERIMENT_CONFIG_H
#define THREE_NODE_EXPERIMENT_CONFIG_H

/*
 * 3-node external-background experiment configuration  (BACKGROUND TX node)
 * ------------------------------------------------------------------------
 * This node is the dedicated external bus-load generator for the 3-node
 * CAN-FD Signal Packing experiment. It reproduces EXACTLY the same-node
 * dummy / bus-load traffic that used to be generated inside each Control TX
 * project (ID 0x300+index, DLC 12, fixed payload, round-robin gap pacing),
 * but from its own independent RA6M5 CAN controller.
 *
 * It NEVER transmits any control frame (0x100/0x101/0x102/0x110/0x120/0x130).
 *
 * The only experiment knob for a run is BG_PROFILE below: change this ONE
 * line, rebuild, flash. Everything else (bit timing, FSP config, dummy frame
 * bytes, scheduler) is the verified path carried over from the TX projects.
 */

/* ---- Background profile selection (edit this one line per run) ---------- */
typedef enum
{
    BG_OFF = 0,   /* zero background CAN write (baseline)                    */

    BG_A_30,      /* Strategy-A companion load, target 30 % total bus load  */
    BG_A_60,      /* Strategy-A companion load, target 60 %                  */
    BG_A_80,      /* Strategy-A companion load, target 80 %                  */

    BG_B_30,      /* Strategy-B companion load, target 30 %                  */
    BG_B_60,      /* Strategy-B companion load, target 60 %                  */
    BG_B_80,      /* Strategy-B companion load, target 80 %                  */

    BG_C_30,      /* Strategy-C companion load, target 30 %                  */
    BG_C_60,      /* Strategy-C companion load, target 60 %                  */
    BG_C_80,      /* Strategy-C companion load, target 80 %                  */
} bg_profile_t;

/* Default = BG_OFF so a freshly built image is bus-safe (zero writes).
 * Set to the profile you want before a measurement run. */
#define BG_PROFILE (BG_OFF)

/*
 * ---- Per-profile gap values (microseconds) ------------------------------
 * Transplanted VERBATIM from the verified same-node TX projects
 * (canfd_strategy_{A,B,C}_tx_meas_64b_fixed). They are the original
 * RETUNE_REQUIRED placeholders: the true target bus load will be re-matched
 * on the PCAN bus-load meter with the 3-node wiring. DO NOT auto-optimize
 * these numbers here. Retune live:
 *     new_gap = old_gap * (measured% - base) / (target% - base)
 *
 * active_count per load level is 4 / 8 / 16 dummy IDs (identical across
 * strategies in the originals); only the gap differs by strategy.
 */
#define BG_GAP_A_30_US (630U)   /* RETUNE_REQUIRED (from Strategy-A TX) */
#define BG_GAP_A_60_US (240U)   /* RETUNE_REQUIRED */
#define BG_GAP_A_80_US (170U)   /* RETUNE_REQUIRED */

#define BG_GAP_B_30_US (475U)   /* RETUNE_REQUIRED (from Strategy-B TX) */
#define BG_GAP_B_60_US (234U)   /* RETUNE_REQUIRED */
#define BG_GAP_B_80_US (170U)   /* RETUNE_REQUIRED */

#define BG_GAP_C_30_US (517U)   /* RETUNE_REQUIRED (from Strategy-C TX) */
#define BG_GAP_C_60_US (238U)   /* RETUNE_REQUIRED */
#define BG_GAP_C_80_US (170U)   /* RETUNE_REQUIRED */

/* ---- Diagnostics -------------------------------------------------------- */
/* Minimal volatile counters for the debugger Expressions view. No printf /
 * UART is added to the transmit loop (that would pollute timing). */
#define BG_ENABLE_DEBUG_COUNTERS (1)

/*
 * ---- Optional scope marker (NOT enabled) --------------------------------
 * A BG_WRITE_MARKER GPIO toggle around R_CANFD_Write() would need a dedicated
 * FSP pin that is not configured in this carried-over project. Enabling it
 * here would require new FSP pin configuration / Generate Project Content and
 * risks clashing with the existing debug-marker pins. Left as a TODO so the
 * build stays stable; add it only after the pin is provisioned in FSP.
 */
#define BG_WRITE_MARKER (0)   /* TODO: needs dedicated FSP pin; do not enable yet */

#endif /* THREE_NODE_EXPERIMENT_CONFIG_H */
