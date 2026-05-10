# peripherals/awg.py
# AWG (Arbitrary Waveform Generator) using DDS — ID 0x40
# TX: AA 40 04 [clk_div_H][clk_div_L][inc_H][inc_L]
# RX: 5A
#
# Clock formula:  Fs   = clk_freq / (2 * clock_divisor)
# DDS formula:    Fout = Fs * inc / 2^16
# Rearranged:     inc  = round(Fout * 2^16 / Fs)
#               = round(Fout * 2^16 * 2 * clock_divisor / clk_freq)

import peripherals.uart_handler as uart

PERIPHERAL_ID = 0x40
CLK_FREQ_HZ   = 100_000_000  # 100 MHz system clock
PHASE_BITS    = 16
PHASE_MAX     = (1 << PHASE_BITS)  # 65536


def awg(clock_divisor, inc):
    """
    Raw register write to AWG.
    clock_divisor: 16-bit int (1–65535)
    inc          : 16-bit int (0–65535)
    """
    clock_divisor = max(1, min(clock_divisor, 65535))
    inc = max(0, min(inc, 65535))

    data = bytes([
        (clock_divisor >> 8) & 0xFF,
        clock_divisor & 0xFF,
        (inc >> 8) & 0xFF,
        inc & 0xFF,
    ])

    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    fs = CLK_FREQ_HZ / (2 * clock_divisor)
    actual_fout = fs * inc / PHASE_MAX

    result["clock_divisor"] = clock_divisor
    result["inc"] = inc
    result["fs_hz"] = fs
    result["actual_fout_hz"] = actual_fout
    result["nyquist_warning"] = inc > (PHASE_MAX // 2)
    return result


def awg_set_frequency(fout_hz, clock_divisor=1):
    """
    Compute inc from desired Fout and set AWG.
    fout_hz      : desired output frequency in Hz
    clock_divisor: 16-bit int, default 1 (Fs = 50 MHz)
    Returns dict with computed and actual frequencies.
    """
    clock_divisor = max(1, min(clock_divisor, 65535))
    fs = CLK_FREQ_HZ / (2 * clock_divisor)
    inc = round(fout_hz * PHASE_MAX / fs)
    inc = max(0, min(inc, 65535))

    if inc > PHASE_MAX // 2:
        print(f"[AWG] Warning: Fout {fout_hz/1e6:.3f} MHz exceeds Nyquist "
              f"({fs/2/1e6:.3f} MHz). Aliasing will occur.")

    return awg(clock_divisor, inc)
