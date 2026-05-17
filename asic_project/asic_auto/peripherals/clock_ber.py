# peripherals/clock_ber.py
# Clock Generator and BER — ID 0x80
# Set clock TX : AA 80 05 AA [div31:24][div23:16][div15:8][div7:0]
# Set clock RX : 5A 5A
# Read BER  TX : 55 80 05 55 [div31:24][div23:16][div15:8][div7:0]
# Read BER  RX : 5A [BER_B1][BER_B2]
#
# Frequency formula: f_out = clk_freq / (2 * divider)
# clk_freq = 100 MHz

import time

import peripherals.uart_handler as uart

PERIPHERAL_ID = 0x80
CLK_FREQ_HZ   = 100_000_000
BER_BITS      = 100_000
BER_MARGIN_S  = 0.05

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


def ber_wait_time_s(freq_hz, margin_s=BER_MARGIN_S):
    """
    Wait time needed for the 100000-bit BER run at the selected frequency.
    """
    if freq_hz <= 0:
        return None
    return (BER_BITS / freq_hz) + max(0.0, float(margin_s))


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


def clock_set_frequency_and_read_ber(freq_hz, margin_s=BER_MARGIN_S,
                                     stop_check=None):
    """
    Set clock, wait for 100000 bits plus margin, then read BER.
    """
    clk_result = clock_set_frequency(freq_hz)
    actual_freq = clk_result.get("actual_freq_hz")
    wait_s = ber_wait_time_s(actual_freq, margin_s) if actual_freq else None

    if clk_result.get("status") != "ok" or wait_s is None:
        return {
            "status": clk_result.get("status", "error"),
            "clock_result": clk_result,
            "ber_result": None,
            "ber_raw": None,
            "wait_s": wait_s,
        }

    deadline = time.time() + wait_s
    while True:
        if stop_check and stop_check():
            return {
                "status": "stopped",
                "clock_result": clk_result,
                "ber_result": None,
                "ber_raw": None,
                "wait_s": wait_s,
            }
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))

    ber_result = read_ber()
    return {
        "status": ber_result.get("status"),
        "clock_result": clk_result,
        "ber_result": ber_result,
        "ber_raw": ber_result.get("ber_raw"),
        "wait_s": wait_s,
    }


def sweep_ber(freq_list, log_callback=None):
    """
    Step through a list of frequencies, set clock, read BER.
    log_callback: optional function(result_dict) called after each point.
    Returns list of result dicts.
    """
    results = []
    for freq in freq_list:
        point_result = clock_set_frequency_and_read_ber(freq)
        clk_result = point_result.get("clock_result")
        ber_result = point_result.get("ber_result") or {}
        point = {
            "freq_hz": freq,
            "clock_result": clk_result,
            "ber_result": ber_result,
            "ber_raw": ber_result.get("ber_raw"),
            "wait_s": point_result.get("wait_s"),
        }
        results.append(point)
        if log_callback:
            log_callback(point)
    return results
