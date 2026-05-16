# peripherals/adc.py
# ADC — ID 0x20
# 16-bit unipolar, 2.5V reference, 8 channels (0–7)
# Voltage = (raw / 65535) * 2500 mV
#
# Trigger TX: AA 20 03 A1 [CH] FF  → RX: 5A 5A  (wait ~5ms)
# Read    TX: 55 20 01 A2           → RX: 5A [MSB][LSB]

import time
import peripherals.uart_handler as uart

PERIPHERAL_ID = 0x20
VREF_MV       = 2500.0
ADC_MAX       = 65535
CONV_DELAY_S  = 0.005  # 5 ms conversion wait


# def adc_write(channel):
#     """
#     Trigger ADC conversion on channel 0–7.
#     TX: AA 20 03 A1 [channel] FF
#     RX: 5A 5A
#     """
#     if channel not in range(8):
#         return {"status": "error", "error": "channel must be 0-7"}
#     data = bytes([0xA1, channel & 0x07, 0xFF])
#     result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
#     result["channel"] = channel
#     return result

# modified by harriam in compactable with the verilog adc peripheral -two writes to trigger conversion
def adc_write(channel):
    """
    Trigger ADC conversion on channel 0–7.
    TX: AA 20 03 A1 [channel] FF
    RX: 5A 5A
    """
    if channel not in range(8):
        return {"status": "error", "error": "channel must be 0-7"}
    data = bytes([0xA1, channel & 0x07, 0xFF])
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    data = bytes([0xA1, channel & 0x07, 0xFF])
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    data = bytes([0xA1, channel & 0x07, 0xFF])
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    result["channel"] = channel
    return result


def adc_read():
    """
    Read last ADC conversion result.
    TX: 55 20 01 A2
    RX: 5A [MSB][LSB]
    Returns raw counts and voltage in mV.
    """
    result = uart.send_packet(uart.SOF_READ, PERIPHERAL_ID,
                              bytes([0xA2]))
    rx = result.get("rx", b"")
    if result["status"] == "ok" and len(rx) >= 3:
        raw = (rx[1] << 8) | rx[2]
        voltage_mv = (raw / ADC_MAX) * VREF_MV
        result["raw"] = raw
        result["voltage_mv"] = round(voltage_mv, 3)
        result["binary"] = f"{raw:016b}"
    else:
        result["raw"] = None
        result["voltage_mv"] = None
        result["binary"] = None
    return result


def adc_read_channel(channel):
    """
    Trigger conversion on channel, wait 5ms, read result.
    Convenience wrapper around adc_write + adc_read.
    """
    trigger = adc_write(channel)
    if trigger["status"] != "ok":
        return trigger
    time.sleep(CONV_DELAY_S)
    read = adc_read()
    read["channel"] = channel
    return read


def adc_scan_all():
    """
    Read all 8 ADC channels sequentially.
    Returns dict with 'channels' key containing per-channel results.
    """
    channels = {}
    for ch in range(8):
        r = adc_read_channel(ch)
        channels[ch] = {
            "raw": r.get("raw"),
            "voltage_mv": r.get("voltage_mv"),
            "status": r.get("status"),
        }
    return {
        "status": "ok",
        "channels": channels,
    }
