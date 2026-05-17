# peripherals/chip_config.py
# Chip Configuration — ID 0x08
# TX: 55 08 01 55
# RX: 5A [status_byte]
#   0x11 = config success
#   0x22 = config failed

import time

import peripherals.uart_handler as uart

PERIPHERAL_ID   = 0x08
STATUS_SUCCESS  = 0x11
STATUS_FAILED   = 0x22
CONFIG_READ_DELAY_S = 3.0


def chip_config():
    """
    Trigger DUT configuration and return result.
    Returns dict:
      status        : "ok" | "error" | ...
      config_status : "success" | "failed" | "unknown"
      raw_status    : int byte received
      tx / rx       : raw bytes
    """
    packet = bytes([uart.SOF_READ, PERIPHERAL_ID, 0x01, 0x55])
    if not uart.is_connected():
        result = {"status": "not_connected", "tx": b"", "rx": b""}
    else:
        uart.flush_rx()
        if not uart.send_raw(packet):
            result = {"status": "error", "tx": packet, "rx": b""}
        else:
            time.sleep(CONFIG_READ_DELAY_S)
            rx = uart.read_raw(2)
            if not rx:
                status = "timeout"
            elif rx[0] != uart.SOF_ACK_OK:
                status = "invalid"
            else:
                status = "ok"
            result = {"status": status, "tx": packet, "rx": rx}

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
