#ifndef CANFD_SIGNALSET_64B_H
#define CANFD_SIGNALSET_64B_H

#include <stdint.h>

static const uint8_t g_u1_payload[8] =
{
    0xF4U, 0x01U, 0x01U, 0x02U, 0x2CU, 0x01U, 0x00U, 0xA5U
};

static const uint8_t g_u2_payload[8] =
{
    0x88U, 0xFFU, 0xFAU, 0x00U, 0xE8U, 0x03U, 0xEEU, 0x02U
};

static const uint8_t g_u3_payload[16] =
{
    0xE0U, 0x01U, 0xE2U, 0x01U, 0xDFU, 0x01U, 0xE1U, 0x01U,
    0xE7U, 0xFFU, 0x64U, 0x00U, 0xD8U, 0xFFU, 0xAAU, 0x55U
};

static const uint8_t g_n1_payload[8] =
{
    0x34U, 0x12U, 0x41U, 0x00U, 0xE4U, 0x0CU, 0x00U, 0x00U
};

static const uint8_t g_n2_payload[8] =
{
    0xE8U, 0x03U, 0xC8U, 0x00U, 0x32U, 0x00U, 0x20U, 0x03U
};

static const uint8_t g_n3_payload[16] =
{
    0x44U, 0x33U, 0x22U, 0x11U, 0x88U, 0x77U, 0x66U, 0x55U,
    0xD4U, 0xC3U, 0xB2U, 0xA1U, 0x3CU, 0x2DU, 0x1EU, 0x0FU
};

_Static_assert(sizeof(g_u1_payload) == 8U, "U1 must be 8 bytes");
_Static_assert(sizeof(g_u2_payload) == 8U, "U2 must be 8 bytes");
_Static_assert(sizeof(g_u3_payload) == 16U, "U3 must be 16 bytes");
_Static_assert(sizeof(g_n1_payload) == 8U, "N1 must be 8 bytes");
_Static_assert(sizeof(g_n2_payload) == 8U, "N2 must be 8 bytes");
_Static_assert(sizeof(g_n3_payload) == 16U, "N3 must be 16 bytes");
_Static_assert((sizeof(g_u1_payload) + sizeof(g_u2_payload) + sizeof(g_u3_payload)) == 32U,
               "Urgent payload must be 32 bytes");
_Static_assert((sizeof(g_n1_payload) + sizeof(g_n2_payload) + sizeof(g_n3_payload)) == 32U,
               "Normal payload must be 32 bytes");
_Static_assert((sizeof(g_u1_payload) + sizeof(g_u2_payload) + sizeof(g_u3_payload) +
                sizeof(g_n1_payload) + sizeof(g_n2_payload) + sizeof(g_n3_payload)) == 64U,
               "Full logical signal set must be 64 bytes");

#endif
