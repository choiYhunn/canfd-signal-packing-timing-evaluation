#include "hal_data.h"
#include "canfd_signalset_64b.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

/*
 * EK-RA6M5 CAN-FD Signal Packing Strategy C / TX measurement
 *
 * Keep the verified CANFD1 path: R_IOPORT_Open(), P611 STBY LOW, CANFD1,
 * and the generated FSP pin/CAN settings. This file only schedules and packs
 * Strategy C FD+BRS DLC12 frames plus optional dummy load frames.
 *
 * Strategy C:
 *  - 0x100 all-pack every 5 ms: target_speed, dir_flag, seq_num,
 *    heartbeat, calibration, log_marker.
 */

#define USE_CANFD_FRAME          (1U)
#define USE_CANFD_BRS            (1U)
#define TX_TIMEOUT_US            (1200000U)
#define DUMMY_FRAME_DLC          (12U)
#define FIXED_TARGET_SPEED       (500)
#define FIXED_DIR_FLAG           (0x01U)
#define FIXED_SEQ_NUM            (0x1234U)
#define FIXED_HEARTBEAT          (0x5AU)
#define FIXED_CALIBRATION        (0xCA1B2468U)
#define FIXED_LOG_MARKER         (0x5AA5U)
#define FIXED_DUMMY_COUNTER      (0x0000U)
/* Bus-load targets 30 / 60 / 80 % (see strategy A). Macro names are legacy:
 * g_dummy_30/60/80_min_gap_us -> 30/60/80 %. Tune live:
 *   new_gap = old_gap * (measured%-base) / (target%-base), base ~= 2% for C. */
#define DUMMY_30_MIN_GAP_US      (517U)   /* RETUNE_REQUIRED placeholder */
#define DUMMY_60_MIN_GAP_US      (238U)   /* RETUNE_REQUIRED placeholder */
#define DUMMY_80_MIN_GAP_US      (170U)   /* RETUNE_REQUIRED placeholder */
#define DUMMY_FORCED_PERIOD_US   (10000U)
#define DUMMY_ID_BASE            (0x300U)
#define DUMMY_ID_MAX_COUNT       (16U)
#define CANFD_TX_MB_0X100        (0U)
#define CANFD_TX_MB_DUMMY        (1U)   /* first dummy mailbox (pool in g_dummy_mb_list) */
#define CANFD_TX_MB_DUMMY_COUNT  (2U)   /* dummy pool: MB 1,2 (2 mailboxes -> ~72% ceiling) */
#define CANFD_TX_MB_COUNT        (3U)   /* control 0, dummy 1,2 */
#define CANFD_TX_MB_INTERRUPT_MASK ((1ULL << CANFD_TX_MB_COUNT) - 1ULL)
#define CONTROL_ALL_PERIOD_US    (5000U)
#define CANFD_DIAG_DEFAULT       (0U)
#define CANFD_DIAG_NO_BRS        (1U)
#define CANFD_DIAG_DATA_1M       (2U)
#define DEBUG_GPIO_TOGGLE_ENABLE (0U)
#define DEBUG_GPIO_0X100_PIN     BSP_IO_PORT_04_PIN_00
#define DEBUG_GPIO_0X110_PIN     BSP_IO_PORT_04_PIN_01

extern canfd_extended_cfg_t g_canfd1_extended_cfg;
extern can_bit_timing_cfg_t g_canfd1_data_timing_cfg;

typedef enum
{
    DUMMY_LOAD_OFF = 0,
    DUMMY_LOAD_30  = 1,
    DUMMY_LOAD_60  = 2,
    DUMMY_LOAD_80  = 3,
} dummy_load_mode_t;

static can_bit_timing_cfg_t g_canfd1_data_timing_cfg_diag_1m =
{
    .baud_rate_prescaler = 1,
    .time_segment_1 = 24,
    .time_segment_2 = 8,
    .synchronization_jump_width = 4
};

const canfd_afl_entry_t p_canfd1_afl[CANFD_CFG_AFL_CH1_RULE_NUM] =
{
    {
        .id =
        {
            .id         = 0x00000000,
            .frame_type = CAN_FRAME_TYPE_DATA,
            .id_mode    = CAN_ID_MODE_STANDARD,
        },
        .mask =
        {
            .mask_id         = 0x00000000,
            .mask_frame_type = 0,
            .mask_id_mode    = 0,
        },
        .destination =
        {
            .minimum_dlc       = CANFD_MINIMUM_DLC_0,
            .rx_buffer         = CANFD_RX_MB_NONE,
            .fifo_select_flags = CANFD_RX_FIFO_0,
        },
    },
};

volatile fsp_err_t   g_ioport_open_err = FSP_SUCCESS;
volatile fsp_err_t   g_open_err        = FSP_SUCCESS;
volatile fsp_err_t   g_normal_err      = FSP_SUCCESS;
volatile fsp_err_t   g_close_err       = FSP_SUCCESS;
volatile fsp_err_t   g_write_err       = FSP_SUCCESS;
volatile fsp_err_t   g_info_err        = FSP_SUCCESS;

volatile bool        g_tx_pending = false;
volatile bool        g_tx_done    = false;
volatile bool        g_rx_flag    = false;
volatile bool        g_can_error  = false;
volatile can_event_t g_last_event = (can_event_t) 0;

volatile uint32_t g_loop_count          = 0;
volatile uint32_t g_seq                 = 0;
volatile uint32_t g_write_success_count = 0;
volatile uint32_t g_write_fail_count    = 0;
volatile uint32_t g_tx_not_ready_count  = 0;
volatile uint32_t g_tx_callback_count   = 0;
volatile uint32_t g_tx_timeout_count    = 0;
volatile uint32_t g_reopen_count        = 0;
volatile uint32_t g_error_count         = 0;
volatile uint32_t g_ms_since_write      = 0;
volatile uint32_t g_dummy_load_mode            = DUMMY_LOAD_OFF;
volatile uint32_t g_dummy_service_call_count   = 0;
volatile uint32_t g_dummy_tx_attempt_count     = 0;
volatile uint32_t g_dummy_tx_success_count     = 0;
volatile uint32_t g_dummy_tx_fail_count        = 0;
volatile uint32_t g_dummy_tx_skip_count        = 0;
volatile uint32_t g_dummy_last_id              = 0;
volatile uint32_t g_dummy_tx_count             = 0;
volatile uint32_t g_dummy_write_fail_count     = 0;
volatile uint32_t g_dummy_target_fps           = 0;
volatile uint32_t g_dummy_actual_fps           = 0;
volatile uint32_t g_dummy_last_dt_us           = 0;
volatile uint32_t g_dummy_target_period_us     = 0;
volatile uint32_t g_dummy_forced_enable        = 0;
volatile uint32_t g_dummy_skip_pending_count   = 0;
volatile uint32_t g_total_write_success_count  = 0;
volatile uint32_t g_total_write_fail_count     = 0;
volatile uint32_t g_control_tx_count           = 0;
volatile uint32_t g_dummy_counter              = 0;
volatile uint32_t g_dummy_ms                   = 0;
volatile uint32_t g_dummy_id_index             = 0;
volatile uint32_t g_dummy_30_min_gap_us        = DUMMY_30_MIN_GAP_US;
volatile uint32_t g_dummy_60_min_gap_us        = DUMMY_60_MIN_GAP_US;
volatile uint32_t g_dummy_80_min_gap_us        = DUMMY_80_MIN_GAP_US;
volatile uint32_t g_dummy_min_gap_us_current   = 0U;
volatile uint32_t g_dummy_scheduler_tick       = 0;
volatile uint32_t g_dummy_due_count            = 0;
volatile uint32_t g_dummy_send_attempt_count   = 0;
volatile uint32_t g_dummy_send_success_count   = 0;
volatile uint32_t g_dummy_send_fail_count      = 0;
volatile uint32_t g_dummy_send_skip_pending_count     = 0;
volatile uint32_t g_dummy_send_skip_gap_count         = 0;
volatile uint32_t g_dummy_send_skip_control_due_count = 0;
volatile uint32_t g_dummy_send_skip_mode0_count       = 0;
volatile uint32_t g_last_dummy_tx_cycle        = 0;
volatile uint32_t g_last_dummy_tx_us           = 0;
volatile uint32_t g_last_dummy_interval_us     = 0;
volatile uint32_t g_dummy_rr_index             = 0;
volatile uint32_t g_dummy_mb_rr                = 0;
volatile uint32_t g_dummy_scheduler_mode       = DUMMY_LOAD_OFF;
volatile uint32_t g_dummy_scheduler_active_count = 0;
volatile uint32_t g_dummy_scheduler_gap_us     = 0;
volatile uint32_t g_dummy_next_due_cycle[DUMMY_ID_MAX_COUNT] = {0};
volatile uint32_t g_control_tx_per_sec         = 0;
volatile uint32_t g_dummy_tx_per_sec           = 0;
volatile uint32_t g_tx_callback_per_sec        = 0;
volatile uint32_t g_main_loop_per_sec          = 0;
volatile uint32_t g_tx_pending_since_cycle     = 0;
volatile uint32_t g_tx_complete_event_count    = 0;
volatile uint32_t g_tx_abort_event_count       = 0;
volatile uint32_t g_error_event_count          = 0;
volatile uint32_t g_error_warning_count        = 0;
volatile uint32_t g_error_passive_count        = 0;
volatile uint32_t g_bus_off_count              = 0;
volatile uint32_t g_bus_error_count            = 0;
volatile uint32_t g_last_can_event             = 0;
volatile uint32_t g_last_tx_mb                 = 0;
volatile bool     g_tx_mb_pending[CANFD_TX_MB_COUNT] = {false};
volatile uint32_t g_tx_mb_pending_since_cycle[CANFD_TX_MB_COUNT] = {0};
volatile uint32_t g_tx_mb_complete_count[CANFD_TX_MB_COUNT] = {0};
volatile uint32_t g_tx_mb_timeout_count[CANFD_TX_MB_COUNT] = {0};
volatile uint32_t g_tx_mb_write_success_count[CANFD_TX_MB_COUNT] = {0};
volatile uint32_t g_tx_mb_write_fail_count[CANFD_TX_MB_COUNT] = {0};
volatile uint32_t g_tx_mb_last_event_buffer    = 0;
volatile bool     g_bus_off_reopen_request     = false;

volatile uint32_t g_canfd_diag_mode            = CANFD_DIAG_DEFAULT;
volatile uint32_t g_canfd_diag_active_mode     = CANFD_DIAG_DEFAULT;
volatile uint32_t g_canfd_diag_reopen_count    = 0;
volatile uint32_t g_canfd_diag_close_err       = 0;
volatile uint32_t g_canfd_diag_open_err        = 0;
volatile uint32_t g_canfd_diag_normal_err      = 0;
volatile uint32_t g_canfd_nominal_prescaler    = 1U;
volatile uint32_t g_canfd_nominal_tseg1        = 49U;
volatile uint32_t g_canfd_nominal_tseg2        = 17U;
volatile uint32_t g_canfd_nominal_sjw          = 4U;
volatile uint32_t g_canfd_nominal_sample_point = 75U;
volatile uint32_t g_canfd_nominal_bitrate      = 497512U;
volatile uint32_t g_canfd_data_prescaler       = 1U;
volatile uint32_t g_canfd_data_tseg1           = 12U;
volatile uint32_t g_canfd_data_tseg2           = 4U;
volatile uint32_t g_canfd_data_sjw             = 1U;
volatile uint32_t g_canfd_data_sample_point    = 76U;
volatile uint32_t g_canfd_data_bitrate         = 1960784U;

volatile uint32_t g_tx_count_0x100 = 0;
volatile uint32_t g_tx_100_count = 0;
volatile uint32_t g_tx_100_last_dt_us = 0;
volatile uint32_t g_tx_100_last_success_cycle = 0;
volatile uint32_t g_skip_100_pending_count = 0;
volatile uint32_t g_gpio_100_toggle_count = 0;
volatile uint32_t g_gpio_110_toggle_count = 0;
volatile uint32_t g_gpio_100_level = 0;
volatile uint32_t g_gpio_110_level = 0;

volatile uint32_t g_ms_0x100 = 5U;
volatile uint32_t g_last_tx_cycle_0x100 = 0;

volatile uint32_t g_rx_count       = 0;
volatile uint32_t g_rx_count_total = 0;
volatile uint32_t g_rx_id  = 0;
volatile uint8_t  g_rx_dlc = 0;
volatile uint8_t  g_rx_d0  = 0;
volatile uint8_t  g_rx_d1  = 0;
volatile uint8_t  g_rx_d2  = 0;
volatile uint8_t  g_rx_d3  = 0;
volatile uint8_t  g_rx_d4  = 0;
volatile uint8_t  g_rx_d5  = 0;
volatile uint8_t  g_rx_d6  = 0;
volatile uint8_t  g_rx_d7  = 0;

volatile int16_t  g_motor_cmd     = 0;
volatile int16_t  g_target_speed  = 0;
volatile int16_t  g_encoder_speed = 0;
volatile int16_t  g_motor_current = 0;
volatile int16_t  g_temperature   = 0;
volatile uint32_t g_diagnostic    = 0;
volatile uint8_t  g_dir_flag      = 0;
volatile uint16_t g_seq_num       = 0;
volatile uint8_t  g_heartbeat     = 0;
volatile uint32_t g_calibration   = 0;
volatile uint16_t g_log_marker    = 0;

can_info_t        g_can_info;
volatile uint32_t g_can_status     = 0;
volatile uint32_t g_rx_fifo_status = 0;
volatile uint32_t g_error_code     = 0;
volatile uint8_t  g_tec            = 0;
volatile uint8_t  g_rec            = 0;

can_frame_t       g_tx_frame;
can_frame_t       g_rx_frame;

static uint32_t g_last_rate_cycle = 0;
static uint32_t g_last_rate_control_count = 0;
static uint32_t g_last_rate_dummy_count = 0;
static uint32_t g_last_rate_callback_count = 0;
static uint32_t g_last_rate_loop_count = 0;

static void dwt_timer_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static uint32_t ticks_per_us(void)
{
    const uint32_t ticks = SystemCoreClock / 1000000U;
    return (0U == ticks) ? 1U : ticks;
}

static uint32_t us_to_cycles(uint32_t us)
{
    return us * ticks_per_us();
}

static uint32_t cycle_delta_us(uint32_t now_cycle, uint32_t last_cycle)
{
    return (now_cycle - last_cycle) / ticks_per_us();
}

static bool cycle_elapsed_us(uint32_t now_cycle, uint32_t last_cycle, uint32_t period_us)
{
    if (0U == last_cycle)
    {
        return true;
    }

    return ((now_cycle - last_cycle) >= us_to_cycles(period_us));
}

static void tx_pending_refresh(void)
{
    bool any_pending = false;

    for (uint32_t mb = 0; mb < CANFD_TX_MB_COUNT; mb++)
    {
        if (g_tx_mb_pending[mb])
        {
            any_pending = true;
            break;
        }
    }

    g_tx_pending = any_pending;
}

static void clear_all_tx_pending(void)
{
    for (uint32_t mb = 0; mb < CANFD_TX_MB_COUNT; mb++)
    {
        g_tx_mb_pending[mb] = false;
        g_tx_mb_pending_since_cycle[mb] = 0;
    }

    g_tx_pending = false;
    g_tx_done = false;
}

static void debug_gpio_init(void)
{
#if DEBUG_GPIO_TOGGLE_ENABLE
    R_IOPORT_PinCfg(&g_ioport_ctrl,
                    DEBUG_GPIO_0X100_PIN,
                    (uint32_t) IOPORT_CFG_PORT_DIRECTION_OUTPUT | (uint32_t) IOPORT_CFG_PORT_OUTPUT_LOW);
    R_IOPORT_PinCfg(&g_ioport_ctrl,
                    DEBUG_GPIO_0X110_PIN,
                    (uint32_t) IOPORT_CFG_PORT_DIRECTION_OUTPUT | (uint32_t) IOPORT_CFG_PORT_OUTPUT_LOW);
#endif
}

static void debug_gpio_toggle_0x100(void)
{
#if DEBUG_GPIO_TOGGLE_ENABLE
    g_gpio_100_level ^= 1U;
    R_IOPORT_PinWrite(&g_ioport_ctrl,
                      DEBUG_GPIO_0X100_PIN,
                      g_gpio_100_level ? BSP_IO_LEVEL_HIGH : BSP_IO_LEVEL_LOW);
#endif
    g_gpio_100_toggle_count++;
}

static void can_status_update(void)
{
    can_info_t info;
    memset(&info, 0, sizeof(info));

    g_info_err = R_CANFD_InfoGet(&g_canfd1_ctrl, &info);
    if (FSP_SUCCESS == g_info_err)
    {
        g_can_info       = info;
        g_can_status     = info.status;
        g_rx_fifo_status = info.rx_fifo_status;
        g_error_code     = info.error_code;
        g_tec            = info.error_count_transmit;
        g_rec            = info.error_count_receive;
    }
}

static void transceiver_normal_mode(void)
{
    R_IOPORT_PinWrite(&g_ioport_ctrl, BSP_IO_PORT_06_PIN_11, BSP_IO_LEVEL_LOW);
    R_BSP_SoftwareDelay(5, BSP_DELAY_UNITS_MILLISECONDS);
}

static uint32_t sanitize_diag_mode(uint32_t mode)
{
    return (mode > CANFD_DIAG_DATA_1M) ? CANFD_DIAG_DEFAULT : mode;
}

static void apply_canfd_diag_timing(uint32_t mode)
{
    const uint32_t selected_mode = sanitize_diag_mode(mode);

    if (CANFD_DIAG_DATA_1M == selected_mode)
    {
        g_canfd1_extended_cfg.p_data_timing = &g_canfd1_data_timing_cfg_diag_1m;
        g_canfd_data_prescaler = 1U;
        g_canfd_data_tseg1 = 24U;
        g_canfd_data_tseg2 = 8U;
        g_canfd_data_sjw = 4U;
        g_canfd_data_sample_point = 76U;
        g_canfd_data_bitrate = 1010101U;
    }
    else
    {
        g_canfd1_extended_cfg.p_data_timing = &g_canfd1_data_timing_cfg;
        g_canfd_data_prescaler = 1U;
        g_canfd_data_tseg1 = 12U;
        g_canfd_data_tseg2 = 4U;
        g_canfd_data_sjw = 1U;
        g_canfd_data_sample_point = 76U;
        g_canfd_data_bitrate = 1960784U;
    }

    g_canfd_diag_active_mode = selected_mode;
}

static void canfd_diag_reopen(uint32_t mode)
{
    clear_all_tx_pending();
    g_canfd_diag_close_err = (uint32_t) R_CANFD_Close(&g_canfd1_ctrl);
    R_BSP_SoftwareDelay(20, BSP_DELAY_UNITS_MILLISECONDS);

    transceiver_normal_mode();
    apply_canfd_diag_timing(mode);

    g_canfd1_extended_cfg.txmb_txi_enable = CANFD_TX_MB_INTERRUPT_MASK;
    g_canfd_diag_open_err = (uint32_t) R_CANFD_Open(&g_canfd1_ctrl, &g_canfd1_cfg);
    if (FSP_SUCCESS == (fsp_err_t) g_canfd_diag_open_err)
    {
        g_canfd_diag_normal_err = (uint32_t) R_CANFD_ModeTransition(&g_canfd1_ctrl,
                                                                    CAN_OPERATION_MODE_NORMAL,
                                                                    CAN_TEST_MODE_DISABLED);
        if (FSP_SUCCESS == (fsp_err_t) g_canfd_diag_normal_err)
        {
            g_canfd_diag_reopen_count++;
            g_can_error = false;
        }
    }
}

static void service_canfd_diag_mode(void)
{
    const uint32_t requested_mode = sanitize_diag_mode(g_canfd_diag_mode);

    if (requested_mode != g_canfd_diag_mode)
    {
        g_canfd_diag_mode = requested_mode;
    }

    if (requested_mode == g_canfd_diag_active_mode)
    {
        return;
    }

    if ((CANFD_DIAG_DATA_1M == requested_mode) || (CANFD_DIAG_DATA_1M == g_canfd_diag_active_mode))
    {
        canfd_diag_reopen(requested_mode);
    }
    else
    {
        g_canfd_diag_active_mode = requested_mode;
    }
}

static void can_reopen(void)
{
    g_close_err = R_CANFD_Close(&g_canfd1_ctrl);
    R_BSP_SoftwareDelay(20, BSP_DELAY_UNITS_MILLISECONDS);

    transceiver_normal_mode();
    apply_canfd_diag_timing(g_canfd_diag_mode);

    /* Preserve TX completion callbacks if support-file extraction rewrites ra_gen. */
    g_canfd1_extended_cfg.txmb_txi_enable = CANFD_TX_MB_INTERRUPT_MASK;
    g_open_err = R_CANFD_Open(&g_canfd1_ctrl, &g_canfd1_cfg);
    if (FSP_SUCCESS == g_open_err)
    {
        g_normal_err = R_CANFD_ModeTransition(&g_canfd1_ctrl,
                                              CAN_OPERATION_MODE_NORMAL,
                                              CAN_TEST_MODE_DISABLED);
        g_reopen_count++;
        clear_all_tx_pending();
        g_ms_since_write = 0;
    }
}

static void reset_runtime_debug_state(void)
{
    g_tx_pending = false;
    g_tx_done = false;
    g_can_error = false;
    g_last_event = (can_event_t) 0;
    g_last_can_event = 0;
    g_seq = 0;
    g_write_success_count = 0;
    g_write_fail_count = 0;
    g_tx_not_ready_count = 0;
    g_tx_callback_count = 0;
    g_tx_complete_event_count = 0;
    g_tx_abort_event_count = 0;
    g_tx_timeout_count = 0;
    g_reopen_count = 0;
    g_error_count = 0;
    g_error_event_count = 0;
    g_error_warning_count = 0;
    g_error_passive_count = 0;
    g_bus_off_count = 0;
    g_bus_error_count = 0;
    g_total_write_success_count = 0;
    g_total_write_fail_count = 0;
    g_control_tx_count = 0;
    g_dummy_load_mode = DUMMY_LOAD_OFF;
    g_dummy_service_call_count = 0;
    g_dummy_tx_attempt_count = 0;
    g_dummy_tx_success_count = 0;
    g_dummy_tx_fail_count = 0;
    g_dummy_tx_skip_count = 0;
    g_dummy_last_id = 0;
    g_dummy_tx_count = 0;
    g_dummy_write_fail_count = 0;
    g_dummy_target_fps = 0;
    g_dummy_actual_fps = 0;
    g_dummy_last_dt_us = 0;
    g_dummy_target_period_us = 0;
    g_dummy_forced_enable = 0;
    g_dummy_skip_pending_count = 0;
    g_dummy_counter = 0;
    g_dummy_id_index = 0;
    g_dummy_send_attempt_count = 0;
    g_dummy_send_success_count = 0;
    g_dummy_send_fail_count = 0;
    g_tx_count_0x100 = 0;
    g_tx_100_count = 0;
    g_tx_100_last_dt_us = 0;
    g_tx_100_last_success_cycle = 0;
    g_last_tx_cycle_0x100 = 0;
    clear_all_tx_pending();
}

static void update_signal_values(void)
{
    g_target_speed = (int16_t) FIXED_TARGET_SPEED;
    g_dir_flag     = (uint8_t) FIXED_DIR_FLAG;
    g_seq_num      = (uint16_t) FIXED_SEQ_NUM;
    g_heartbeat    = (uint8_t) FIXED_HEARTBEAT;
    g_calibration  = FIXED_CALIBRATION;
    g_log_marker   = (uint16_t) FIXED_LOG_MARKER;
}

static void frame_init(uint32_t id, uint8_t payload_length)
{
    memset(&g_tx_frame, 0, sizeof(g_tx_frame));

    g_tx_frame.id               = id;
    g_tx_frame.id_mode          = CAN_ID_MODE_STANDARD;
    g_tx_frame.type             = CAN_FRAME_TYPE_DATA;
    g_tx_frame.data_length_code = payload_length;

#if USE_CANFD_FRAME
    g_tx_frame.options = CANFD_FRAME_OPTION_FD;
 #if USE_CANFD_BRS
    if (CANFD_DIAG_NO_BRS != g_canfd_diag_mode)
    {
        g_tx_frame.options |= CANFD_FRAME_OPTION_BRS;
    }
 #endif
#else
    g_tx_frame.options = 0;
#endif
    g_canfd_diag_active_mode = g_canfd_diag_mode;
}

static void put_u16(uint32_t index, uint16_t value)
{
    g_tx_frame.data[index]      = (uint8_t) (value & 0x00FFU);
    g_tx_frame.data[index + 1U] = (uint8_t) ((value >> 8) & 0x00FFU);
}

static void tx_count_update(uint32_t id, uint32_t now_cycle)
{
    if (0x100U == id)
    {
        g_tx_count_0x100++;
        g_tx_100_count++;
        if (g_tx_100_last_success_cycle)
        {
            g_tx_100_last_dt_us = cycle_delta_us(now_cycle, g_tx_100_last_success_cycle);
        }
        g_tx_100_last_success_cycle = now_cycle;
    }
}

static bool write_current_frame(bool is_control_frame, uint32_t tx_mb, uint32_t now_cycle)
{
    if (tx_mb >= CANFD_TX_MB_COUNT)
    {
        g_write_err = FSP_ERR_INVALID_ARGUMENT;
        return false;
    }

    if (g_tx_mb_pending[tx_mb])
    {
        return false;
    }

    g_last_tx_mb = tx_mb;
    g_write_err = R_CANFD_Write(&g_canfd1_ctrl, tx_mb, &g_tx_frame);
    if (FSP_SUCCESS == g_write_err)
    {
        g_total_write_success_count++;
        g_tx_mb_pending[tx_mb] = true;
        g_tx_mb_pending_since_cycle[tx_mb] = now_cycle;
        g_tx_mb_write_success_count[tx_mb]++;
        tx_pending_refresh();
        g_tx_done = false;
        g_ms_since_write = 0;
        g_tx_pending_since_cycle = now_cycle;

        if (is_control_frame)
        {
            g_write_success_count++;
            g_control_tx_count++;
            tx_count_update(g_tx_frame.id, now_cycle);
            g_seq++;
        }
        else
        {
            g_dummy_tx_count++;
            g_dummy_counter++;
            g_dummy_send_success_count++;
        }

        return true;
    }

    g_total_write_fail_count++;
    g_tx_mb_write_fail_count[tx_mb]++;
    if (is_control_frame)
    {
        g_write_fail_count++;
    }
    else
    {
        g_dummy_write_fail_count++;
    }

    if (FSP_ERR_CAN_TRANSMIT_NOT_READY == g_write_err)
    {
        g_tx_not_ready_count++;
    }
    else
    {
        g_can_error = true;
    }

    return false;
}

static void prepare_compact_all_pack(void)
{
    uint32_t offset = 0U;

    frame_init(0x100U, 64U);
    memcpy(&g_tx_frame.data[offset], g_u1_payload, sizeof(g_u1_payload));
    offset += (uint32_t) sizeof(g_u1_payload);
    memcpy(&g_tx_frame.data[offset], g_u2_payload, sizeof(g_u2_payload));
    offset += (uint32_t) sizeof(g_u2_payload);
    memcpy(&g_tx_frame.data[offset], g_u3_payload, sizeof(g_u3_payload));
    offset += (uint32_t) sizeof(g_u3_payload);
    memcpy(&g_tx_frame.data[offset], g_n1_payload, sizeof(g_n1_payload));
    offset += (uint32_t) sizeof(g_n1_payload);
    memcpy(&g_tx_frame.data[offset], g_n2_payload, sizeof(g_n2_payload));
    offset += (uint32_t) sizeof(g_n2_payload);
    memcpy(&g_tx_frame.data[offset], g_n3_payload, sizeof(g_n3_payload));
}

static uint32_t dummy_active_count(void)
{
    switch (g_dummy_load_mode)
    {
        case DUMMY_LOAD_30:
            return 4U;
        case DUMMY_LOAD_60:
            return 8U;
        case DUMMY_LOAD_80:
            return DUMMY_ID_MAX_COUNT;
        default:
            return 0U;
    }
}

static uint32_t dummy_min_gap_us(void)
{
    switch (g_dummy_load_mode)
    {
        case DUMMY_LOAD_30:
            return g_dummy_30_min_gap_us;
        case DUMMY_LOAD_60:
            return g_dummy_60_min_gap_us;
        case DUMMY_LOAD_80:
            return g_dummy_80_min_gap_us;
        default:
            return 0U;
    }
}

static uint8_t dummy_marker(void)
{
    switch (g_dummy_load_mode)
    {
        case DUMMY_LOAD_30:
            return 0x30U;
        case DUMMY_LOAD_60:
            return 0x60U;
        case DUMMY_LOAD_80:
            return 0x80U;
        default:
            return 0x00U;
    }
}

static void prepare_dummy_frame(uint32_t index)
{
    frame_init(DUMMY_ID_BASE + index, DUMMY_FRAME_DLC);
    g_tx_frame.data[0] = 0xDEU;
    g_tx_frame.data[1] = 0xADU;
    g_tx_frame.data[2] = 0xBEU;
    g_tx_frame.data[3] = 0xEFU;
    put_u16(4U, (uint16_t) FIXED_DUMMY_COUNTER);
    g_tx_frame.data[6] = (uint8_t) (index & 0x0FU);
    g_tx_frame.data[7] = dummy_marker();
    g_tx_frame.data[8] = 0xFDU;
    g_tx_frame.data[9] = 0x12U;
    g_tx_frame.data[10] = 0x00U;
    g_tx_frame.data[11] = 0x00U;
    g_tx_frame.data_length_code = DUMMY_FRAME_DLC;
}

/* Dummy TX mailbox pool (2 mailboxes) so dummy frames can go back-to-back and
 * reach the ~72% load ceiling; identical scheme to strategy A. */
static const uint32_t g_dummy_mb_list[CANFD_TX_MB_DUMMY_COUNT] = { 1U, 2U };

static bool cycle_reached(uint32_t now_cycle, uint32_t due_cycle)
{
    return ((now_cycle - due_cycle) < 0x80000000U);
}

/* Seed per-ID due times, phase-distributed across the active dummy IDs so the
 * background traffic is evenly spread (not gap-fitted to signal frames). Called
 * on mode change to reset scheduler state cleanly (no carried-over backlog).
 * Identical scheme to strategies A and B. */
static void dummy_scheduler_seed(uint32_t base_cycle, uint32_t active_count, uint32_t min_gap_us)
{
    const uint32_t gap_cycles = us_to_cycles(min_gap_us);

    for (uint32_t i = 0; i < DUMMY_ID_MAX_COUNT; i++)
    {
        if (i < active_count)
        {
            g_dummy_next_due_cycle[i] = base_cycle + (gap_cycles * i);
        }
        else
        {
            g_dummy_next_due_cycle[i] = 0;
        }
    }

    g_dummy_rr_index = 0U;
    g_dummy_mb_rr = 0U;
    g_last_dummy_tx_cycle = base_cycle;
    g_dummy_scheduler_mode = g_dummy_load_mode;
    g_dummy_scheduler_active_count = active_count;
    g_dummy_scheduler_gap_us = min_gap_us;
}

static bool canfd_dummy_load_service(uint32_t now_cycle)
{
    uint32_t active_count = dummy_active_count();
    uint32_t min_gap_us = dummy_min_gap_us();

    g_dummy_service_call_count++;
    g_dummy_scheduler_tick++;

    if (0U != g_dummy_forced_enable)
    {
        active_count = 1U;
        min_gap_us = DUMMY_FORCED_PERIOD_US;
        g_dummy_rr_index = 0U;
    }

    g_dummy_min_gap_us_current = min_gap_us;
    g_dummy_target_period_us = min_gap_us;

    if ((g_dummy_scheduler_mode != g_dummy_load_mode) ||
        (g_dummy_scheduler_active_count != active_count) ||
        (g_dummy_scheduler_gap_us != min_gap_us))
    {
        dummy_scheduler_seed(now_cycle, active_count, min_gap_us);
    }

    if (0U == active_count)
    {
        g_dummy_target_fps = 0;
        g_dummy_target_period_us = 0;
        g_dummy_tx_skip_count++;
        g_dummy_send_skip_mode0_count++;
        dummy_scheduler_seed(now_cycle, 0U, 0U);
        return false;
    }

    g_dummy_target_fps = (min_gap_us > 0U) ? (1000000U / min_gap_us) : 0U;

    uint32_t dummy_index = 0U;
    bool dummy_due = false;
    for (uint32_t i = 0; i < active_count; i++)
    {
        const uint32_t index = (g_dummy_rr_index + i) % active_count;
        if ((0U != g_dummy_next_due_cycle[index]) &&
            cycle_reached(now_cycle, g_dummy_next_due_cycle[index]))
        {
            dummy_index = index;
            dummy_due = true;
            break;
        }
    }

    if (!dummy_due)
    {
        if (0U != g_last_dummy_tx_cycle)
        {
            g_last_dummy_interval_us = cycle_delta_us(now_cycle, g_last_dummy_tx_cycle);
        }
        g_dummy_tx_skip_count++;
        g_dummy_send_skip_gap_count++;
        return false;
    }

    /* Pick a free mailbox from the dummy pool (round-robin over g_dummy_mb_list). */
    uint32_t dummy_mb = g_dummy_mb_list[0];
    uint32_t dummy_slot = 0;
    bool dummy_mb_free = false;
    for (uint32_t i = 0; i < CANFD_TX_MB_DUMMY_COUNT; i++)
    {
        const uint32_t slot = (g_dummy_mb_rr + i) % CANFD_TX_MB_DUMMY_COUNT;
        if (!g_tx_mb_pending[g_dummy_mb_list[slot]])
        {
            dummy_mb = g_dummy_mb_list[slot];
            dummy_slot = slot;
            dummy_mb_free = true;
            break;
        }
    }
    if (!dummy_mb_free)
    {
        g_dummy_tx_skip_count++;
        g_dummy_skip_pending_count++;
        g_dummy_send_skip_pending_count++;
        dummy_scheduler_seed(now_cycle + us_to_cycles(min_gap_us), active_count, min_gap_us);
        return false;
    }

    g_dummy_due_count++;
    g_dummy_tx_attempt_count++;
    g_dummy_send_attempt_count++;
    prepare_dummy_frame(dummy_index);
    if (write_current_frame(false, dummy_mb, now_cycle))
    {
        g_dummy_ms = 0;
        g_dummy_id_index = dummy_index;
        g_last_dummy_interval_us = cycle_delta_us(now_cycle, g_last_dummy_tx_cycle);
        g_dummy_last_dt_us = g_last_dummy_interval_us;
        g_dummy_last_id = DUMMY_ID_BASE + dummy_index;
        g_dummy_tx_success_count++;
        g_last_dummy_tx_cycle = now_cycle;
        g_last_dummy_tx_us = now_cycle / ticks_per_us();
        g_dummy_next_due_cycle[dummy_index] = now_cycle + us_to_cycles(min_gap_us * active_count);
        g_dummy_rr_index = (dummy_index + 1U) % active_count;
        g_dummy_mb_rr = (dummy_slot + 1U) % CANFD_TX_MB_DUMMY_COUNT;
        return true;
    }

    g_dummy_tx_fail_count++;
    g_dummy_send_fail_count++;
    return false;
}

static void update_period_anchor(volatile uint32_t * p_last_cycle, uint32_t now_cycle, uint32_t period_us)
{
    const uint32_t period_cycles = us_to_cycles(period_us);

    if (0U == *p_last_cycle)
    {
        *p_last_cycle = now_cycle;
        return;
    }

    *p_last_cycle += period_cycles;
    if ((now_cycle - *p_last_cycle) >= period_cycles)
    {
        *p_last_cycle = now_cycle;
    }
}

static void service_tx_timeout(uint32_t now_cycle)
{
    uint32_t max_pending_ms = 0;

    if (g_bus_off_reopen_request)
    {
        g_bus_off_reopen_request = false;
        g_can_error = true;
        clear_all_tx_pending();
        can_reopen();
        g_ms_since_write = 0;
        return;
    }

    for (uint32_t mb = 0; mb < CANFD_TX_MB_COUNT; mb++)
    {
        if (!g_tx_mb_pending[mb])
        {
            continue;
        }

        const uint32_t pending_us = cycle_delta_us(now_cycle, g_tx_mb_pending_since_cycle[mb]);
        const uint32_t pending_ms = pending_us / 1000U;
        if (pending_ms > max_pending_ms)
        {
            max_pending_ms = pending_ms;
        }

        if (pending_us >= TX_TIMEOUT_US)
        {
            g_tx_timeout_count++;
            g_tx_mb_timeout_count[mb]++;
            g_tx_mb_pending[mb] = false;
            g_tx_mb_pending_since_cycle[mb] = 0;
        }
    }

    g_ms_since_write = max_pending_ms;
    tx_pending_refresh();
}

static void update_rate_counters(uint32_t now_cycle)
{
    if (0U == g_last_rate_cycle)
    {
        g_last_rate_cycle = now_cycle;
        return;
    }

    if ((now_cycle - g_last_rate_cycle) >= SystemCoreClock)
    {
        g_control_tx_per_sec = g_control_tx_count - g_last_rate_control_count;
        g_dummy_tx_per_sec = g_dummy_tx_count - g_last_rate_dummy_count;
        g_dummy_actual_fps = g_dummy_tx_per_sec;
        g_tx_callback_per_sec = g_tx_callback_count - g_last_rate_callback_count;
        g_main_loop_per_sec = g_loop_count - g_last_rate_loop_count;

        g_last_rate_control_count = g_control_tx_count;
        g_last_rate_dummy_count = g_dummy_tx_count;
        g_last_rate_callback_count = g_tx_callback_count;
        g_last_rate_loop_count = g_loop_count;
        g_last_rate_cycle = now_cycle;
    }
}

static void transmit_due_frame(uint32_t now_cycle)
{
    bool control_due_or_sent = false;

    update_signal_values();

    if (cycle_elapsed_us(now_cycle, g_last_tx_cycle_0x100, CONTROL_ALL_PERIOD_US))
    {
        control_due_or_sent = true;
        if (g_tx_mb_pending[CANFD_TX_MB_0X100])
        {
            g_skip_100_pending_count++;
        }
        else
        {
            prepare_compact_all_pack();
            debug_gpio_toggle_0x100();
            g_dummy_send_skip_control_due_count++;
            if (write_current_frame(true, CANFD_TX_MB_0X100, now_cycle))
            {
                update_period_anchor(&g_last_tx_cycle_0x100, now_cycle, CONTROL_ALL_PERIOD_US);
            }
        }
    }

    (void) control_due_or_sent;
}

void canfd1_callback(can_callback_args_t * p_args)
{
    g_last_event = p_args->event;
    g_last_can_event = (uint32_t) p_args->event;
    g_tx_mb_last_event_buffer = p_args->buffer;

    switch (p_args->event)
    {
        case CAN_EVENT_TX_COMPLETE:
            if (p_args->buffer < CANFD_TX_MB_COUNT)
            {
                g_tx_mb_pending[p_args->buffer] = false;
                g_tx_mb_pending_since_cycle[p_args->buffer] = 0;
                g_tx_mb_complete_count[p_args->buffer]++;
            }
            g_tx_done = true;
            tx_pending_refresh();
            g_tx_callback_count++;
            g_tx_complete_event_count++;
            g_can_error = false;
            g_ms_since_write = 0;
            break;

        case CAN_EVENT_RX_COMPLETE:
            g_rx_frame = p_args->frame;
            g_rx_id    = p_args->frame.id;
            g_rx_dlc   = p_args->frame.data_length_code;
            g_rx_d0    = p_args->frame.data[0];
            g_rx_d1    = p_args->frame.data[1];
            g_rx_d2    = p_args->frame.data[2];
            g_rx_d3    = p_args->frame.data[3];
            g_rx_d4    = p_args->frame.data[4];
            g_rx_d5    = p_args->frame.data[5];
            g_rx_d6    = p_args->frame.data[6];
            g_rx_d7    = p_args->frame.data[7];
            g_rx_count++;
            g_rx_count_total++;
            g_rx_flag = true;
            break;

        case CAN_EVENT_ERR_WARNING:
            g_can_error = true;
            g_error_count++;
            g_error_event_count++;
            g_error_warning_count++;
            break;

        case CAN_EVENT_ERR_PASSIVE:
            g_can_error = true;
            g_error_count++;
            g_error_event_count++;
            g_error_passive_count++;
            break;

        case CAN_EVENT_ERR_BUS_OFF:
            g_can_error = true;
            g_error_count++;
            g_error_event_count++;
            g_bus_off_count++;
            g_bus_error_count++;
            g_bus_off_reopen_request = true;
            clear_all_tx_pending();
            break;

        case CAN_EVENT_ERR_CHANNEL:
        case CAN_EVENT_ERR_GLOBAL:
        case CAN_EVENT_BUS_RECOVERY:
            g_can_error = true;
            g_error_count++;
            g_error_event_count++;
            g_bus_error_count++;
            break;

        case CAN_EVENT_TX_ABORTED:
            g_can_error = true;
            g_error_count++;
            g_error_event_count++;
            g_tx_abort_event_count++;
            if (p_args->buffer < CANFD_TX_MB_COUNT)
            {
                g_tx_mb_pending[p_args->buffer] = false;
                g_tx_mb_pending_since_cycle[p_args->buffer] = 0;
                tx_pending_refresh();
            }
            break;

        default:
            break;
    }
}

void hal_entry(void)
{
    g_ioport_open_err = R_IOPORT_Open(&g_ioport_ctrl, &g_bsp_pin_cfg);
    if ((FSP_SUCCESS != g_ioport_open_err) && (FSP_ERR_ALREADY_OPEN != g_ioport_open_err))
    {
        while (1)
        {
            __NOP();
        }
    }

    reset_runtime_debug_state();
    debug_gpio_init();
    transceiver_normal_mode();
    apply_canfd_diag_timing(g_canfd_diag_mode);

    g_canfd1_extended_cfg.txmb_txi_enable = CANFD_TX_MB_INTERRUPT_MASK;
    g_open_err = R_CANFD_Open(&g_canfd1_ctrl, &g_canfd1_cfg);
    if (FSP_SUCCESS != g_open_err)
    {
        while (1)
        {
            __NOP();
        }
    }

    g_normal_err = R_CANFD_ModeTransition(&g_canfd1_ctrl,
                                          CAN_OPERATION_MODE_NORMAL,
                                          CAN_TEST_MODE_DISABLED);
    if (FSP_SUCCESS != g_normal_err)
    {
        while (1)
        {
            can_status_update();
            __NOP();
        }
    }

    dwt_timer_init();

    while (1)
    {
        const uint32_t now_cycle = DWT->CYCCNT;

        g_loop_count++;
        can_status_update();
        service_tx_timeout(now_cycle);
        service_canfd_diag_mode();
        transmit_due_frame(now_cycle);
        (void) canfd_dummy_load_service(now_cycle);
        update_rate_counters(now_cycle);
    }
}
