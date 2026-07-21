#include "hal_data.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

/*
 * EK-RA6M5 CAN-FD Signal Packing Strategy B / RX
 *
 * This project is a copy of the verified CANFD1 external communication project.
 * Keep FSP 5.7.0 generated CANFD1 configuration, CANFD1 pins, RX FIFO 0 AFL,
 * R_IOPORT_Open(), and P611 STBY LOW exactly on the proven path.
 *
 * Selector-based Strategy B unpack policy, CAN-FD DLC 12:
 *  - 0x100 urgent_pack updates target_speed, dir_flag, seq_num.
 *  - 0x110 normal_pack updates heartbeat, calibration, log_marker.
 */

#define LOOP_DELAY_MS (1U)
#define CANFD_DIAG_DEFAULT  (0U)
#define CANFD_DIAG_NO_BRS   (1U)
#define CANFD_DIAG_DATA_1M  (2U)
#define DEBUG_GPIO_TOGGLE_ENABLE (0U)
#define DEBUG_GPIO_0X100_PIN BSP_IO_PORT_04_PIN_00
#define DEBUG_GPIO_0X110_PIN BSP_IO_PORT_04_PIN_01

extern canfd_extended_cfg_t g_canfd1_extended_cfg;
extern can_bit_timing_cfg_t g_canfd1_data_timing_cfg;

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
volatile fsp_err_t   g_info_err        = FSP_SUCCESS;

volatile bool        g_rx_flag    = false;
volatile bool        g_can_error  = false;
volatile can_event_t g_last_event = (can_event_t) 0;

volatile uint32_t g_loop_count  = 0;
volatile uint32_t g_rx_count    = 0;
volatile uint32_t g_error_count = 0;
volatile uint32_t g_last_can_event = 0;
volatile uint32_t g_error_warning_count = 0;
volatile uint32_t g_error_passive_count = 0;
volatile uint32_t g_bus_off_count = 0;
volatile uint32_t g_bus_error_count = 0;

#define CANFD_STS_EPSTS  (0x08U)
#define CANFD_STS_BOSTS  (0x10U)
#define CANFD_STS_COMSTS (0x80U)

volatile uint32_t g_error_state          = 0;
volatile uint32_t g_error_state_max      = 0;
volatile uint32_t g_ep_status_flag       = 0;
volatile uint32_t g_bo_status_flag       = 0;
volatile uint32_t g_error_passive_seen   = 0;
volatile uint32_t g_bus_off_seen         = 0;
volatile uint32_t g_tec_max              = 0;
volatile uint32_t g_rec_max              = 0;

volatile uint32_t g_canfd_diag_mode = CANFD_DIAG_DEFAULT;
volatile uint32_t g_canfd_diag_active_mode = CANFD_DIAG_DEFAULT;
volatile uint32_t g_canfd_diag_reopen_count = 0;
volatile uint32_t g_canfd_diag_close_err = 0;
volatile uint32_t g_canfd_diag_open_err = 0;
volatile uint32_t g_canfd_diag_normal_err = 0;
volatile uint32_t g_canfd_nominal_prescaler = 1U;
volatile uint32_t g_canfd_nominal_tseg1 = 49U;
volatile uint32_t g_canfd_nominal_tseg2 = 17U;
volatile uint32_t g_canfd_nominal_sjw = 4U;
volatile uint32_t g_canfd_nominal_sample_point = 75U;
volatile uint32_t g_canfd_nominal_bitrate = 497512U;
volatile uint32_t g_canfd_data_prescaler = 1U;
volatile uint32_t g_canfd_data_tseg1 = 12U;
volatile uint32_t g_canfd_data_tseg2 = 4U;
volatile uint32_t g_canfd_data_sjw = 1U;
volatile uint32_t g_canfd_data_sample_point = 76U;
volatile uint32_t g_canfd_data_bitrate = 1960784U;
volatile uint32_t g_gpio_100_toggle_count = 0;
volatile uint32_t g_gpio_110_toggle_count = 0;
volatile uint32_t g_gpio_100_level = 0;
volatile uint32_t g_gpio_110_level = 0;

volatile uint32_t g_last_rx_0x100_time_us      = 0;
volatile uint32_t g_rx_0x100_interval_us       = 0;
volatile uint32_t g_rx_0x100_interval_min_us   = 0xFFFFFFFFU;
volatile uint32_t g_rx_0x100_interval_max_us   = 0;
volatile uint64_t g_rx_0x100_interval_sum_us   = 0;
volatile uint32_t g_rx_0x100_interval_count    = 0;
volatile uint32_t g_rx_0x100_jitter_us         = 0;
volatile uint32_t g_deadline_us_0x100          = 6000;
volatile uint32_t g_deadline_miss_count_0x100  = 0;
volatile uint32_t g_deadline_miss_rate_x1000   = 0;
volatile bool     g_rx_0x100_seen              = false;
volatile uint32_t g_last_rx_0x100_cycle        = 0;
volatile uint32_t g_rx_0x100_last_cycle        = 0;
volatile uint32_t g_rx_0x100_has_last_cycle    = 0;
volatile uint32_t g_measure_reset_request      = 0;
volatile uint32_t g_measure_reset_count        = 0;
volatile uint32_t g_measure_sample_count       = 0;
volatile uint32_t g_measure_active             = 0;
volatile uint32_t g_measure_start_ts_us        = 0;
volatile uint32_t g_measure_elapsed_ms         = 0;

volatile uint32_t g_dummy_load_mode            = 0;
volatile uint32_t g_dummy_forced_enable        = 0;
volatile uint32_t g_dummy_gap_live_us          = 0;
volatile uint32_t g_dummy_tx_count             = 0;
volatile uint32_t g_dummy_write_success_count  = 0;
volatile uint32_t g_dummy_write_fail_count     = 0;

volatile uint32_t g_total_write_success_count  = 0;
volatile uint32_t g_total_write_fail_count     = 0;

volatile uint32_t g_rx_count_total = 0;
volatile uint32_t g_rx_count_urgent = 0;
volatile uint32_t g_rx_count_feedback = 0;
volatile uint32_t g_rx_count_normal = 0;
volatile uint32_t g_rx_count_all = 0;
volatile uint32_t g_rx_count_dummy = 0;
volatile uint32_t g_rx_dummy_count = 0;
volatile uint32_t g_rx_dummy_last_id = 0;
volatile uint32_t g_rx_dummy_last_dt_us = 0;
volatile uint32_t g_rx_dummy_last_cycle = 0;
volatile uint32_t g_rx_count_unknown = 0;
volatile uint32_t g_rx_count_0x100 = 0;
volatile uint32_t g_rx_count_0x101 = 0;
volatile uint32_t g_rx_count_0x102 = 0;
volatile uint32_t g_rx_count_0x110 = 0;
volatile uint32_t g_rx_count_0x120 = 0;
volatile uint32_t g_rx_count_0x130 = 0;
volatile uint32_t g_rx_100_count = 0;
volatile uint32_t g_rx_101_count = 0;
volatile uint32_t g_rx_102_count = 0;
volatile uint32_t g_rx_110_count = 0;
volatile uint32_t g_rx_120_count = 0;
volatile uint32_t g_rx_130_count = 0;
volatile uint32_t g_rx_100_last_dt_us = 0;
volatile uint32_t g_rx_101_last_dt_us = 0;
volatile uint32_t g_rx_102_last_dt_us = 0;
volatile uint32_t g_rx_110_last_dt_us = 0;
volatile uint32_t g_rx_120_last_dt_us = 0;
volatile uint32_t g_rx_130_last_dt_us = 0;
volatile uint32_t g_rx_100_last_ts_us = 0;
volatile uint32_t g_rx_101_last_ts_us = 0;
volatile uint32_t g_rx_102_last_ts_us = 0;
volatile uint32_t g_rx_110_last_ts_us = 0;
volatile uint32_t g_rx_120_last_ts_us = 0;
volatile uint32_t g_rx_130_last_ts_us = 0;
volatile uint32_t g_rx_100_interval_min_us = 0xFFFFFFFFU;
volatile uint32_t g_rx_101_interval_min_us = 0xFFFFFFFFU;
volatile uint32_t g_rx_102_interval_min_us = 0xFFFFFFFFU;
volatile uint32_t g_rx_110_interval_min_us = 0xFFFFFFFFU;
volatile uint32_t g_rx_120_interval_min_us = 0xFFFFFFFFU;
volatile uint32_t g_rx_130_interval_min_us = 0xFFFFFFFFU;
volatile uint32_t g_rx_100_interval_max_us = 0;
volatile uint32_t g_rx_101_interval_max_us = 0;
volatile uint32_t g_rx_102_interval_max_us = 0;
volatile uint32_t g_rx_110_interval_max_us = 0;
volatile uint32_t g_rx_120_interval_max_us = 0;
volatile uint32_t g_rx_130_interval_max_us = 0;
volatile uint32_t g_rx_100_jitter_std_us = 0;
volatile uint32_t g_rx_101_jitter_std_us = 0;
volatile uint32_t g_rx_102_jitter_std_us = 0;
volatile uint32_t g_rx_110_jitter_std_us = 0;
volatile uint32_t g_rx_120_jitter_std_us = 0;
volatile uint32_t g_rx_130_jitter_std_us = 0;
volatile uint32_t g_rx_100_jitter_pp_us = 0;
volatile uint32_t g_rx_101_jitter_pp_us = 0;
volatile uint32_t g_rx_102_jitter_pp_us = 0;
volatile uint32_t g_rx_110_jitter_pp_us = 0;
volatile uint32_t g_rx_120_jitter_pp_us = 0;
volatile uint32_t g_rx_130_jitter_pp_us = 0;
volatile uint32_t g_rx_110_last_cycle = 0;
volatile uint32_t g_rx_110_has_last_cycle = 0;

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
volatile uint32_t g_rx_last_id      = 0;
volatile uint8_t  g_rx_last_dlc     = 0;
volatile uint32_t g_invalid_length_count = 0;
volatile uint32_t g_invalid_length_last_id = 0;
volatile uint32_t g_invalid_length_last_expected = 0;
volatile uint32_t g_invalid_length_last_actual = 0;
volatile uint32_t g_invalid_length_count_0x100 = 0;
volatile uint32_t g_invalid_length_count_0x110 = 0;
volatile uint32_t g_invalid_length_count_dummy = 0;
volatile uint32_t g_rx_last_options = 0;
volatile uint32_t g_rx_last_ts_us   = 0;

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

can_frame_t       g_rx_frame;

static void dwt_timer_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static uint32_t ticks_per_us(void)
{
    const uint32_t ticks_per_us = SystemCoreClock / 1000000U;

    return (0U == ticks_per_us) ? 1U : ticks_per_us;
}

static uint32_t cycles_to_us(uint32_t cycles)
{
    return cycles / ticks_per_us();
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

static void error_state_update(void)
{
    const uint32_t ep = (0U != (g_can_status & CANFD_STS_EPSTS)) ? 1U : 0U;
    const uint32_t bo = (0U != (g_can_status & CANFD_STS_BOSTS)) ? 1U : 0U;
    uint32_t state = 0U;

    if ((g_tec >= 96U) || (g_rec >= 96U))
    {
        state = 1U;
    }
    if (ep)
    {
        state = 2U;
    }
    if (bo)
    {
        state = 3U;
    }

    g_ep_status_flag = ep;
    g_bo_status_flag = bo;
    g_error_state    = state;

    if (ep)
    {
        g_error_passive_seen = 1U;
    }
    if (bo)
    {
        g_bus_off_seen = 1U;
    }
    if (state > g_error_state_max)
    {
        g_error_state_max = state;
    }
    if ((uint32_t) g_tec > g_tec_max)
    {
        g_tec_max = g_tec;
    }
    if ((uint32_t) g_rec > g_rec_max)
    {
        g_rec_max = g_rec;
    }
}

static void transceiver_normal_mode(void)
{
    /* EK-RA6M5 TJA1042T/3 STBY pin. LOW = Normal mode. */
    R_IOPORT_PinWrite(&g_ioport_ctrl,
                      BSP_IO_PORT_06_PIN_11,
                      BSP_IO_LEVEL_LOW);
    R_BSP_SoftwareDelay(5, BSP_DELAY_UNITS_MILLISECONDS);
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

static void debug_gpio_toggle_0x110(void)
{
#if DEBUG_GPIO_TOGGLE_ENABLE
    g_gpio_110_level ^= 1U;
    R_IOPORT_PinWrite(&g_ioport_ctrl,
                      DEBUG_GPIO_0X110_PIN,
                      g_gpio_110_level ? BSP_IO_LEVEL_HIGH : BSP_IO_LEVEL_LOW);
#endif
    g_gpio_110_toggle_count++;
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
    g_canfd_diag_close_err = (uint32_t) R_CANFD_Close(&g_canfd1_ctrl);
    R_BSP_SoftwareDelay(20, BSP_DELAY_UNITS_MILLISECONDS);

    transceiver_normal_mode();
    apply_canfd_diag_timing(mode);

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

static int16_t read_i16_le(uint8_t low, uint8_t high)
{
    const uint16_t value = (uint16_t) low | ((uint16_t) high << 8);
    return (int16_t) value;
}

static void store_last_frame(can_frame_t const * p_frame)
{
    const uint32_t now_us = cycles_to_us(DWT->CYCCNT);

    g_rx_frame = *p_frame;
    g_rx_id    = p_frame->id;
    g_rx_dlc   = p_frame->data_length_code;
    g_rx_last_id = p_frame->id;
    g_rx_last_dlc = p_frame->data_length_code;
    g_rx_last_options = p_frame->options;
    g_rx_last_ts_us = now_us;
    g_rx_d0    = p_frame->data[0];
    g_rx_d1    = p_frame->data[1];
    g_rx_d2    = p_frame->data[2];
    g_rx_d3    = p_frame->data[3];
    g_rx_d4    = p_frame->data[4];
    g_rx_d5    = p_frame->data[5];
    g_rx_d6    = p_frame->data[6];
    g_rx_d7    = p_frame->data[7];
}

static void measurement_mark_active(uint32_t now_us)
{
    if (0U == g_measure_start_ts_us)
    {
        g_measure_start_ts_us = now_us;
    }

    g_measure_active = 1U;
    g_measure_elapsed_ms = (now_us - g_measure_start_ts_us) / 1000U;
}

static void update_interval_pp(uint32_t id)
{
    volatile uint32_t * p_last_ts = NULL;
    volatile uint32_t * p_last_dt = NULL;
    volatile uint32_t * p_min = NULL;
    volatile uint32_t * p_max = NULL;
    volatile uint32_t * p_std = NULL;
    volatile uint32_t * p_pp = NULL;
    const uint32_t now_us = cycles_to_us(DWT->CYCCNT);

    switch (id)
    {
        case 0x110U:
            p_last_ts = &g_rx_110_last_ts_us; p_last_dt = &g_rx_110_last_dt_us;
            p_min = &g_rx_110_interval_min_us; p_max = &g_rx_110_interval_max_us;
            p_std = &g_rx_110_jitter_std_us; p_pp = &g_rx_110_jitter_pp_us;
            break;
        default:
            break;
    }

    if (NULL == p_last_ts)
    {
        return;
    }

    measurement_mark_active(now_us);
    if (0U == *p_last_ts)
    {
        *p_last_ts = now_us;
        *p_last_dt = 0U;
        *p_min = 0xFFFFFFFFU;
        *p_max = 0U;
        *p_std = 0U;
        *p_pp = 0U;
        return;
    }

    const uint32_t dt_us = now_us - *p_last_ts;
    *p_last_ts = now_us;
    *p_last_dt = dt_us;
    if (dt_us < *p_min)
    {
        *p_min = dt_us;
    }
    if (dt_us > *p_max)
    {
        *p_max = dt_us;
    }
    *p_std = 0U;
    *p_pp = *p_max - *p_min;
    g_measure_sample_count++;
}

static void reset_interval_pp_measurements(void)
{
    g_measure_sample_count = 0;
    g_measure_active = 0;
    g_measure_start_ts_us = 0;
    g_measure_elapsed_ms = 0;

    g_rx_100_count = 0; g_rx_101_count = 0; g_rx_102_count = 0;
    g_rx_110_count = 0; g_rx_120_count = 0; g_rx_130_count = 0;
    g_rx_count_0x100 = 0; g_rx_count_0x101 = 0; g_rx_count_0x102 = 0;
    g_rx_count_0x110 = 0; g_rx_count_0x120 = 0; g_rx_count_0x130 = 0;

    g_rx_100_last_ts_us = 0; g_rx_101_last_ts_us = 0; g_rx_102_last_ts_us = 0;
    g_rx_110_last_ts_us = 0; g_rx_120_last_ts_us = 0; g_rx_130_last_ts_us = 0;
    g_rx_100_last_dt_us = 0; g_rx_101_last_dt_us = 0; g_rx_102_last_dt_us = 0;
    g_rx_110_last_dt_us = 0; g_rx_120_last_dt_us = 0; g_rx_130_last_dt_us = 0;

    g_rx_100_interval_min_us = 0xFFFFFFFFU; g_rx_101_interval_min_us = 0xFFFFFFFFU; g_rx_102_interval_min_us = 0xFFFFFFFFU;
    g_rx_110_interval_min_us = 0xFFFFFFFFU; g_rx_120_interval_min_us = 0xFFFFFFFFU; g_rx_130_interval_min_us = 0xFFFFFFFFU;
    g_rx_100_interval_max_us = 0; g_rx_101_interval_max_us = 0; g_rx_102_interval_max_us = 0;
    g_rx_110_interval_max_us = 0; g_rx_120_interval_max_us = 0; g_rx_130_interval_max_us = 0;
    g_rx_100_jitter_std_us = 0; g_rx_101_jitter_std_us = 0; g_rx_102_jitter_std_us = 0;
    g_rx_110_jitter_std_us = 0; g_rx_120_jitter_std_us = 0; g_rx_130_jitter_std_us = 0;
    g_rx_100_jitter_pp_us = 0; g_rx_101_jitter_pp_us = 0; g_rx_102_jitter_pp_us = 0;
    g_rx_110_jitter_pp_us = 0; g_rx_120_jitter_pp_us = 0; g_rx_130_jitter_pp_us = 0;
}

static void expression_symbol_keepalive_service(void)
{
    volatile uint32_t sink = 0U;

    sink ^= g_dummy_load_mode;
    sink ^= g_dummy_forced_enable;
    sink ^= g_dummy_gap_live_us;
    sink ^= g_dummy_tx_count;
    sink ^= g_dummy_write_success_count;
    sink ^= g_dummy_write_fail_count;
    sink ^= g_total_write_success_count;
    sink ^= g_total_write_fail_count;

    if (0xFFFFFFFFU == sink)
    {
        g_total_write_fail_count = sink;
    }
}

static void update_0x100_measurement(void)
{
    const uint32_t now_cycle = DWT->CYCCNT;
    const uint32_t now_us = cycles_to_us(now_cycle);

    measurement_mark_active(now_us);

    if (g_rx_0x100_has_last_cycle)
    {
        const uint32_t delta_cycle = now_cycle - g_last_rx_0x100_cycle;
        const uint32_t interval_us = cycles_to_us(delta_cycle);

        g_rx_0x100_interval_us = interval_us;
        g_rx_100_last_dt_us = interval_us;
        if (interval_us < g_rx_0x100_interval_min_us)
        {
            g_rx_0x100_interval_min_us = interval_us;
        }
        if (interval_us > g_rx_0x100_interval_max_us)
        {
            g_rx_0x100_interval_max_us = interval_us;
        }

        g_rx_0x100_interval_sum_us += interval_us;
        g_rx_0x100_interval_count++;
        g_rx_0x100_jitter_us = g_rx_0x100_interval_max_us - g_rx_0x100_interval_min_us;
        g_rx_100_interval_min_us = g_rx_0x100_interval_min_us;
        g_rx_100_interval_max_us = g_rx_0x100_interval_max_us;
        g_rx_100_jitter_pp_us = g_rx_0x100_jitter_us;
        g_rx_100_jitter_std_us = 0U;
        g_measure_sample_count++;

        if (interval_us > g_deadline_us_0x100)
        {
            g_deadline_miss_count_0x100++;
        }

        g_deadline_miss_rate_x1000 = (uint32_t) (((uint64_t) g_deadline_miss_count_0x100 * 1000ULL) /
                                                  (uint64_t) g_rx_0x100_interval_count);
    }
    else
    {
        g_rx_0x100_seen = true;
        g_rx_0x100_has_last_cycle = 1U;
        g_rx_100_last_dt_us = 0U;
        g_rx_100_interval_min_us = 0xFFFFFFFFU;
        g_rx_100_interval_max_us = 0U;
        g_rx_100_jitter_pp_us = 0U;
        g_rx_100_jitter_std_us = 0U;
    }

    g_last_rx_0x100_cycle = now_cycle;
    g_rx_0x100_last_cycle = now_cycle;
    g_last_rx_0x100_time_us = now_us;
    g_rx_100_last_ts_us = now_us;
}

static void measurement_reset_service(void)
{
    if (0U == g_measure_reset_request)
    {
        return;
    }

    g_rx_0x100_interval_us = 0;
    g_rx_0x100_interval_min_us = 0xFFFFFFFFU;
    g_rx_0x100_interval_max_us = 0;
    g_rx_0x100_jitter_us = 0;
    g_rx_0x100_interval_sum_us = 0;
    g_rx_0x100_interval_count = 0;
    g_deadline_miss_count_0x100 = 0;
    g_deadline_miss_rate_x1000 = 0;
    g_last_rx_0x100_time_us = 0;
    g_last_rx_0x100_cycle = 0;
    g_rx_0x100_last_cycle = 0;
    g_rx_0x100_has_last_cycle = 0;
    g_rx_0x100_seen = false;
    g_measure_reset_count++;
    reset_interval_pp_measurements();
    g_measure_reset_request = 0;
}

static bool is_dummy_id(uint32_t id)
{
    return ((id >= 0x300U) && (id <= 0x30FU));
}

static bool frame_length_is_valid(can_frame_t const * p_frame)
{
    uint8_t expected = 0U;
    volatile uint32_t * p_id_count = NULL;

    if (is_dummy_id(p_frame->id))
    {
        expected = 12U;
        p_id_count = &g_invalid_length_count_dummy;
    }
    else if (0x100U == p_frame->id)
    {
        expected = 32U;
        p_id_count = &g_invalid_length_count_0x100;
    }
    else if (0x110U == p_frame->id)
    {
        expected = 32U;
        p_id_count = &g_invalid_length_count_0x110;
    }

    if ((0U != expected) && (p_frame->data_length_code != expected))
    {
        g_invalid_length_count++;
        g_invalid_length_last_id = p_frame->id;
        g_invalid_length_last_expected = expected;
        g_invalid_length_last_actual = p_frame->data_length_code;
        (*p_id_count)++;
        return false;
    }

    return true;
}

static void unpack_frame(can_frame_t const * p_frame)
{
    if (!frame_length_is_valid(p_frame))
    {
        return;
    }

    if (is_dummy_id(p_frame->id))
    {
        const uint32_t now_cycle = DWT->CYCCNT;

        g_rx_count_dummy++;
        g_rx_dummy_count++;
        g_rx_dummy_last_id = p_frame->id;
        if (0U != g_rx_dummy_last_cycle)
        {
            g_rx_dummy_last_dt_us = cycles_to_us(now_cycle - g_rx_dummy_last_cycle);
        }
        g_rx_dummy_last_cycle = now_cycle;
        return;
    }

    switch (p_frame->id)
    {
        case 0x100U:
            update_0x100_measurement();
            debug_gpio_toggle_0x100();
            g_target_speed = read_i16_le(p_frame->data[0], p_frame->data[1]);
            g_dir_flag = p_frame->data[2];
            g_rx_count_urgent++;
            g_rx_count_0x100++;
            g_rx_100_count++;
            break;
        case 0x110U:
            update_interval_pp(0x110U);
            debug_gpio_toggle_0x110();
            g_rx_count_normal++;
            g_rx_count_0x110++;
            g_rx_110_count++;
            break;
        default:
            g_rx_count_unknown++;
            break;
    }
}

void canfd1_callback(can_callback_args_t * p_args)
{
    g_last_event = p_args->event;
    g_last_can_event = (uint32_t) p_args->event;

    switch (p_args->event)
    {
        case CAN_EVENT_RX_COMPLETE:
            store_last_frame(&p_args->frame);
            g_rx_count++;
            g_rx_count_total++;
            unpack_frame(&p_args->frame);
            g_rx_flag = true;
            break;

        case CAN_EVENT_ERR_WARNING:
            g_can_error = true;
            g_error_count++;
            g_error_warning_count++;
            break;

        case CAN_EVENT_ERR_PASSIVE:
            g_can_error = true;
            g_error_count++;
            g_error_passive_count++;
            break;

        case CAN_EVENT_ERR_BUS_OFF:
            g_can_error = true;
            g_error_count++;
            g_bus_off_count++;
            g_bus_error_count++;
            break;

        case CAN_EVENT_ERR_CHANNEL:
        case CAN_EVENT_ERR_GLOBAL:
        case CAN_EVENT_BUS_RECOVERY:
        case CAN_EVENT_FIFO_MESSAGE_LOST:
        case CAN_EVENT_MAILBOX_MESSAGE_LOST:
            g_can_error = true;
            g_error_count++;
            g_bus_error_count++;
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

    memset(&g_rx_frame, 0, sizeof(g_rx_frame));

    debug_gpio_init();
    transceiver_normal_mode();
    apply_canfd_diag_timing(g_canfd_diag_mode);

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
        g_loop_count++;
        can_status_update();
        error_state_update();
        service_canfd_diag_mode();
        measurement_reset_service();
        expression_symbol_keepalive_service();

        if (g_rx_flag)
        {
            g_rx_flag = false;
        }

        R_BSP_SoftwareDelay(LOOP_DELAY_MS, BSP_DELAY_UNITS_MILLISECONDS);
    }
}
