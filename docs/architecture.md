
# Architecture

RA6M5 TX firmware generates strategy-specific fixed payload frames and optional 0x300-series background frames. RA6M5 RX firmware validates DLC/payload and records event markers. PCAN TRC captures form the statistical campaign; a separate oscilloscope campaign observes Tpre/Ttx/Trx/Tpwm_sw markers.
