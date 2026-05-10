# peripherals/level_setting.py
# LTC2656 Octal 16-bit DAC — ID 0x02
# TX: AA 02 03 [D0][D1][D2]
# D0 upper nibble = command, lower nibble = channel (0=A .. 7=H)
# D1 = value[15:8], D2 = value[7:0]
# RX: 5A 5A

import peripherals.uart_handler as uart

PERIPHERAL_ID = 0x02
VREF_MV       = 2500.0
DAC_BITS      = 16
DAC_MAX       = (1 << DAC_BITS) - 1  # 65535

# LTC2656 command nibbles
CMD_WRITE_UPDATE     = 0x3
CMD_POWER_DOWN       = 0x4
CMD_WRITE_UPDATE_ALL = 0xF

CHANNEL_NAMES = {0: "A", 1: "B", 2: "C", 3: "D",
                 4: "E", 5: "F", 6: "G", 7: "H"}


def _send(d0, d1, d2):
    data = bytes([d0, d1, d2])
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    parsed = {}
    if result["status"] == "ok":
        # Expect 5A 5A
        rx = result["rx"]
        parsed["ack_count"] = sum(1 for b in rx if b == uart.SOF_ACK_OK)
    return {**result, "parsed": parsed,
            "d0": d0, "d1": d1, "d2": d2}


def level_set_dac_analog(channel, value_mv, cmd=CMD_WRITE_UPDATE):
    """
    Set DAC channel to a voltage in mV (0.0 – 2500.0 mV).
    channel: 0–7 (A–H)
    value_mv: float, clamped to [0, 2500]
    cmd: command nibble, default Write and Update
    """
    if channel not in range(8):
        return {"status": "error", "error": "channel must be 0-7"}

    value_mv = max(0.0, min(value_mv, VREF_MV))
    counts = int((value_mv / VREF_MV) * DAC_MAX)
    counts = max(0, min(counts, DAC_MAX))

    d0 = ((cmd & 0xF) << 4) | (channel & 0xF)
    d1 = (counts >> 8) & 0xFF
    d2 = counts & 0xFF

    result = _send(d0, d1, d2)
    result["channel_name"] = CHANNEL_NAMES[channel]
    result["value_mv"] = value_mv
    result["counts"] = counts
    return result


def level_set_dac_digital(channel, digital_value, cmd=CMD_WRITE_UPDATE):
    """
    Set DAC channel to a raw 16-bit digital value (0–65535).
    channel: 0–7 (A–H)
    digital_value: int 0–65535
    """
    if channel not in range(8):
        return {"status": "error", "error": "channel must be 0-7"}

    digital_value = max(0, min(digital_value, DAC_MAX))
    d0 = ((cmd & 0xF) << 4) | (channel & 0xF)
    d1 = (digital_value >> 8) & 0xFF
    d2 = digital_value & 0xFF

    result = _send(d0, d1, d2)
    result["channel_name"] = CHANNEL_NAMES[channel]
    result["digital_value"] = digital_value
    result["value_mv"] = (digital_value / DAC_MAX) * VREF_MV
    return result


def level_set(d0, d1, d2):
    """Generic raw 3-byte send to level setting peripheral."""
    return _send(d0, d1, d2)
