# peripherals/clock_ber.py
# Clock Generator and BER — ID 0x80
# Set clock TX : AA 80 05 AA [div31:24][div23:16][div15:8][div7:0]
# Set clock RX : 5A 5A
# Read BER  TX : 55 80 05 55 [div31:24][div23:16][div15:8][div7:0]
# Read BER  RX : 5A [BER_B1][BER_B2]
#
# Frequency formula: f_out = clk_freq / (2 * divider)
# clk_freq = 100 MHz

import peripherals.uart_handler as uart

PERIPHERAL_ID = 0x80
CLK_FREQ_HZ   = 100_000_000

# Store last used divisor so read_ber can reuse it
_last_divisor = 2


def _div_to_bytes(divisor):
    d = max(1, int(divisor))
    return bytes([
        (d >> 24) & 0xFF,
        (d >> 16) & 0xFF,
        (d >>  8) & 0xFF,
         d        & 0xFF,
    ])


def clock(divisor):
    """
    Set clock output by divisor.
    f_out = 100MHz / (2 * divisor)
    divisor=2 → 25 MHz, divisor=1 → 50 MHz
    TX: AA 80 05 AA [div bytes x4]
    RX: 5A 5A
    """
    global _last_divisor
    divisor = max(1, int(divisor))
    _last_divisor = divisor

    data = bytes([uart.SOF_WRITE]) + _div_to_bytes(divisor)
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    result["divisor"] = divisor
    result["f_out_hz"] = CLK_FREQ_HZ / (2 * divisor)
    return result


def clock_set_frequency(freq_hz):
    """
    Set clock by desired output frequency in Hz.
    Computes divisor = clk_freq / (2 * freq_hz), rounded to nearest int.
    """
    if freq_hz <= 0:
        return {"status": "error", "error": "freq_hz must be > 0"}

    divisor = round(CLK_FREQ_HZ / (2 * freq_hz))
    divisor = max(1, divisor)
    actual_freq = CLK_FREQ_HZ / (2 * divisor)

    result = clock(divisor)
    result["requested_freq_hz"] = freq_hz
    result["actual_freq_hz"] = actual_freq
    return result


def read_ber():
    """
    Read current BER counter value.
    Uses the last divisor set by clock() or clock_set_frequency().
    TX: 55 80 05 55 [div bytes x4]
    RX: 5A [BER_B1][BER_B2]
    """
    data = bytes([uart.SOF_READ]) + _div_to_bytes(_last_divisor)
    result = uart.send_packet(uart.SOF_READ, PERIPHERAL_ID, data)

    rx = result.get("rx", b"")
    if result["status"] == "ok" and len(rx) >= 3:
        ber_raw = (rx[1] << 8) | rx[2]
        result["ber_raw"] = ber_raw
        result["ber_bytes"] = [rx[1], rx[2]]
    else:
        result["ber_raw"] = None
        result["ber_bytes"] = []
    return result


def sweep_ber(freq_list, log_callback=None):
    """
    Step through a list of frequencies, set clock, read BER.
    log_callback: optional function(result_dict) called after each point.
    Returns list of result dicts.
    """
    results = []
    for freq in freq_list:
        clk_result = clock_set_frequency(freq)
        ber_result = read_ber()
        point = {
            "freq_hz": freq,
            "clock_result": clk_result,
            "ber_result": ber_result,
            "ber_raw": ber_result.get("ber_raw"),
        }
        results.append(point)
        if log_callback:
            log_callback(point)
    return results
