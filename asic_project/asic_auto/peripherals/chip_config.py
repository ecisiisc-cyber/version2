# peripherals/chip_config.py
# Chip Configuration — ID 0x08
# TX: 55 08 01 55
# RX: 5A [status_byte]
#   0x11 = config success
#   0x22 = config failed

import peripherals.uart_handler as uart

PERIPHERAL_ID   = 0x08
STATUS_SUCCESS  = 0x11
STATUS_FAILED   = 0x22


def chip_config():
    """
    Trigger DUT configuration and return result.
    Returns dict:
      status        : "ok" | "error" | ...
      config_status : "success" | "failed" | "unknown"
      raw_status    : int byte received
      tx / rx       : raw bytes
    """
    result = uart.send_packet(uart.SOF_READ, PERIPHERAL_ID,
                              bytes([0x55]))
    rx = result.get("rx", b"")

    raw_status = rx[1] if len(rx) >= 2 else None

    if raw_status == STATUS_SUCCESS:
        config_status = "success"
    elif raw_status == STATUS_FAILED:
        config_status = "failed"
    else:
        config_status = "unknown"

    result["config_status"] = config_status
    result["raw_status"] = raw_status
    return result
