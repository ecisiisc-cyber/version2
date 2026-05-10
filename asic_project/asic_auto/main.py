#!/usr/bin/env python3
"""
main.py — ASIC Characterization Automation Script
===================================================
Sweep core voltage × frequency operating points, run the DUT self-test
at each point, measure power/energy, log results to CSV, and plot shmoos.

Threading model
---------------
  Main thread   : sweep loop, PMIC/clock setup, logging, sequencing
  meas_thread   : runs inside SMU or PSU module — polls power every 500 ms
  uart_ack_thread: waits for the DUT self-test ACK byte (0xFA = pass)
                   so the main thread can proceed without blocking the
                   power measurement thread.

Edit the CONFIG section below before running.
"""

import sys
import os
import time
import threading

# ── allow imports from project root ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── peripheral modules ────────────────────────────────────────────────────────
import peripherals.uart_handler as uart
from peripherals.loopback     import loop_back
from peripherals.pmic         import unlock_pmic, set_buck_voltage
from peripherals.clock_ber    import clock_set_frequency
from peripherals.chip_config  import chip_config
from peripherals.raw_uart     import uart_tx_packet, wait_for_byte

# ── instrument modules ────────────────────────────────────────────────────────
import instruments.smu_2602b as smu
import instruments.psu_2230g as psu

# ── utilities ─────────────────────────────────────────────────────────────────
from utils.session_logger import init_session, log_transaction, log_char_data
from utils.plot_shmoo import plot_all_shmoos


# =============================================================================
#  CONFIG — edit this section before running
# =============================================================================

# ── UART ──────────────────────────────────────────────────────────────────────
UART_PORT  = "COM9"          # Change to your COM port (Linux: "/dev/ttyUSB0")
UART_BAUD  = 115200

# ── Core instrument: "PSU" or "SMU" ──────────────────────────────────────────
CORE_INSTRUMENT = "PSU"      # "PSU" → 2230G,  "SMU" → 2602B

# ── VISA addresses ────────────────────────────────────────────────────────────
PSU_VISA = "USB0::0x05E6::0x2230::9876543::INSTR"   # 2230G
SMU_VISA = "USB0::0x05E6::0x2602::1234567::INSTR"   # 2602B

# ── PSU/SMU channel assignments ───────────────────────────────────────────────
CORE_PSU_CHANNEL = 1         # PSU channel used for core supply
CORE_SMU_CHANNEL = "a"       # SMU channel used if CORE_INSTRUMENT="SMU"

# ── IO rails (Buck regulators via PMIC) — fixed, no sweep ────────────────────
BUCK1_VOLTAGE_MV = 1800.0    # IO rail 1  (e.g. VDDIO 1.8 V)
BUCK2_VOLTAGE_MV = 3300.0    # IO rail 2  (e.g. VDDIO 3.3 V)

# ── Sweep: core voltage (V) and frequency (Hz) ───────────────────────────────
# All combinations are tested (option B grid).
CORE_VOLTAGES_V   = [0.9, 1.0, 1.1]          # core supply in Volts
FREQUENCIES_HZ    = [25e6, 50e6, 100e6]       # DUT clock frequencies

# ── Self-test command ─────────────────────────────────────────────────────────
# The FPGA clock_sel byte is derived from the clock divisor at each sweep point.
# Format: 55 66 01 [clock_sel]
# clock_sel = clock divisor LSB (computed automatically each sweep point)
SELFTEST_SOF = 0x55
SELFTEST_ID  = 0x66

# ── Self-test ACK ─────────────────────────────────────────────────────────────
SELFTEST_PASS_BYTE = 0xFA    # 0xFA = pass, anything else = fail
SELFTEST_TIMEOUT_S = 300     # 5 minutes

# ── Output ────────────────────────────────────────────────────────────────────
SESSION_LABEL = "asic_char"
PLOT_OUTPUT_DIR = "plots"

# =============================================================================
#  HELPERS
# =============================================================================

def print_banner(text):
    bar = "=" * 60
    print(f"\n{bar}\n  {text}\n{bar}")


def print_step(step, text):
    print(f"\n[STEP {step}] {text}")


def abort(reason):
    print(f"\n[ABORT] {reason}")
    sys.exit(1)


def connect_instruments():
    """Connect UART, PSU/SMU. Abort on failure."""
    # ── UART ──────────────────────────────────────────────────────────────
    print_step("1", f"Connecting UART on {UART_PORT}")
    if not uart.connect(UART_PORT, UART_BAUD):
        abort(f"Cannot open UART port {UART_PORT}")

    # ── Loopback health check ──────────────────────────────────────────────
    print_step("1.1", "Running loopback test")
    result = loop_back()
    if not result["match"]:
        abort(f"Loopback failed — check cable/FPGA. "
              f"Echo: {result['echo']}, Status: {result['status']}")
    print(f"  Loopback OK — echo: {[hex(b) for b in result['echo']]}")

    # ── Core instrument ────────────────────────────────────────────────────
    if CORE_INSTRUMENT == "PSU":
        print_step("2", f"Connecting PSU (2230G) at {PSU_VISA}")
        if not psu.connect(PSU_VISA):
            abort("Cannot connect to PSU 2230G")
    else:
        print_step("2", f"Connecting SMU (2602B) at {SMU_VISA}")
        if not smu.connect(SMU_VISA):
            abort("Cannot connect to SMU 2602B")


def setup_io_rails():
    """Set PMIC Buck 1 and Buck 2 to fixed IO voltages."""
    print_step("3", "Configuring IO rails via PMIC")

    unlock = unlock_pmic()
    log_transaction("TX", "PMIC", unlock.get("tx", b""),
                    "unlock_pmic", unlock.get("status"))
    if unlock["status"] != "ok":
        abort(f"PMIC unlock failed: {unlock}")
    print(f"  PMIC unlocked")

    r1 = set_buck_voltage(1, BUCK1_VOLTAGE_MV)
    print(f"  Buck1 (IO rail 1): requested {BUCK1_VOLTAGE_MV} mV → "
          f"actual {r1.get('actual_mv')} mV  [{r1['status']}]")
    log_transaction("TX", "PMIC_BUCK1",
                    r1.get("vset0_result", {}).get("tx", b""),
                    f"Buck1={BUCK1_VOLTAGE_MV}mV", r1["status"])

    r2 = set_buck_voltage(2, BUCK2_VOLTAGE_MV)
    print(f"  Buck2 (IO rail 2): requested {BUCK2_VOLTAGE_MV} mV → "
          f"actual {r2.get('actual_mv')} mV  [{r2['status']}]")
    log_transaction("TX", "PMIC_BUCK2",
                    r2.get("vset0_result", {}).get("tx", b""),
                    f"Buck2={BUCK2_VOLTAGE_MV}mV", r2["status"])


def set_core_voltage(voltage_v):
    """Set core voltage via PSU or SMU."""
    if CORE_INSTRUMENT == "PSU":
        result = psu.PSU_vset(CORE_PSU_CHANNEL, voltage_v)
    else:
        result = smu.SMU_vset(CORE_SMU_CHANNEL, voltage_v)
    return result


def start_core_measurement():
    """Start background power measurement on PSU or SMU."""
    if CORE_INSTRUMENT == "PSU":
        psu.PSU_measure_start(CORE_PSU_CHANNEL)
    else:
        smu.SMU_measure_start(CORE_SMU_CHANNEL)


def stop_core_measurement():
    """Stop background measurement and return snapshot."""
    if CORE_INSTRUMENT == "PSU":
        return psu.PSU_measure_stop()
    else:
        return smu.SMU_measure_stop()


def get_core_measurement():
    """Non-blocking snapshot of latest power measurement."""
    if CORE_INSTRUMENT == "PSU":
        return psu.get_measurement()
    else:
        return smu.get_measurement()


def run_selftest(clock_divisor):
    """
    Send self-test command: 55 66 01 [clock_sel]
    clock_sel = clock_divisor & 0xFF (LSB of divisor)
    Returns dict: {"pass": bool, "elapsed_s": float, "status": str}
    """
    clock_sel = clock_divisor & 0xFF
    hex_str = f"55 66 01 {clock_sel:02X}"
    uart_tx_packet(hex_str)

    # Log TX
    raw_tx = bytes([0x55, 0x66, 0x01, clock_sel])
    log_transaction("TX", "SELFTEST", raw_tx,
                    f"clock_sel=0x{clock_sel:02X}", "sent")

    # Wait for ACK
    ack = wait_for_byte(SELFTEST_PASS_BYTE, timeout_s=SELFTEST_TIMEOUT_S)
    status = ack["status"]
    passed = (status == "found")

    log_transaction("RX", "SELFTEST",
                    bytes([SELFTEST_PASS_BYTE]) if passed else b"",
                    f"ACK={'0xFA(pass)' if passed else 'timeout/fail'}",
                    "ok" if passed else "fail")

    return {
        "pass": passed,
        "elapsed_s": ack["elapsed_s"],
        "status": status,
    }


# =============================================================================
#  MAIN SWEEP LOOP
# =============================================================================

def run_sweep():
    print_banner("ASIC Characterization Automation")
    init_session(SESSION_LABEL)

    # Step 1 & 2: Connect all instruments
    connect_instruments()

    # Step 3: Set fixed IO rails
    setup_io_rails()
    time.sleep(0.2)  # Settle after PMIC configuration

    total_points = len(CORE_VOLTAGES_V) * len(FREQUENCIES_HZ)
    point_num = 0

    # ── Outer loop: core voltage ───────────────────────────────────────────
    for core_v in CORE_VOLTAGES_V:
        core_mv = core_v * 1000.0

        # Step 3.3: Set core voltage
        print_step("3.3", f"Setting core voltage: {core_v:.3f} V")
        cv_result = set_core_voltage(core_v)
        if cv_result.get("status") != "ok":
            print(f"  WARNING: Core voltage set may have failed: {cv_result}")
        time.sleep(0.1)  # Settle

        # ── Inner loop: frequency ──────────────────────────────────────────
        for freq_hz in FREQUENCIES_HZ:
            point_num += 1
            print_banner(
                f"Point {point_num}/{total_points} | "
                f"Core={core_v:.3f}V  Freq={freq_hz/1e6:.1f}MHz"
            )

            # ── Step 3.4: Set clock ────────────────────────────────────────
            print_step("3.4", f"Setting clock to {freq_hz/1e6:.1f} MHz")
            clk_result = clock_set_frequency(freq_hz)
            clock_divisor = clk_result.get("divisor", 1)
            actual_freq   = clk_result.get("actual_freq_hz", freq_hz)
            print(f"  Divisor: {clock_divisor}, "
                  f"Actual freq: {actual_freq/1e6:.4f} MHz "
                  f"[{clk_result['status']}]")
            log_transaction("TX", "CLK_BER", clk_result.get("tx", b""),
                            f"freq={actual_freq/1e6:.3f}MHz",
                            clk_result["status"])
            time.sleep(0.05)

            # ── Step 3.5: Chip config ──────────────────────────────────────
            print_step("3.5", "Configuring DUT chip")
            cfg_result = chip_config()
            print(f"  Config status: {cfg_result['config_status']} "
                  f"(raw=0x{cfg_result.get('raw_status') or 0:02X})")
            log_transaction("TX", "CHIP_CFG", cfg_result.get("tx", b""),
                            cfg_result["config_status"],
                            cfg_result["status"])

            if cfg_result["config_status"] == "failed":
                print("  Config FAILED — logging as fail, continuing")
                log_char_data(
                    voltage_v=core_v,
                    frequency_hz=freq_hz,
                    pass_fail="fail",
                    notes="chip_config failed",
                )
                continue  # next frequency point

            # ── Step 3.6: Send self-test command + start power measurement ─
            # The self-test runs on the DUT; power measurement runs in a
            # background thread. Both happen concurrently.
            print_step("3.6", "Starting power measurement + self-test")

            # Thread A: background power measurement (already looping at 500ms)
            start_core_measurement()
            time.sleep(0.1)  # Let measurement thread take first sample

            # Thread B: send self-test in a separate thread so we don't
            # block the measurement thread.
            selftest_result = {}
            selftest_done = threading.Event()

            def selftest_worker():
                selftest_result.update(run_selftest(clock_divisor))
                selftest_done.set()

            st_thread = threading.Thread(
                target=selftest_worker,
                daemon=True,
                name="selftest_ack",
            )
            st_thread.start()

            # ── Step 3.7: Wait for DUT ACK ────────────────────────────────
            print_step("3.7",
                       f"Waiting for self-test ACK "
                       f"(timeout={SELFTEST_TIMEOUT_S}s)...")
            selftest_done.wait(timeout=SELFTEST_TIMEOUT_S + 5)

            passed    = selftest_result.get("pass", False)
            elapsed_s = selftest_result.get("elapsed_s", 0.0)
            print(f"  Self-test: {'PASS' if passed else 'FAIL'} "
                  f"({elapsed_s:.1f} s)")

            # ── Step 3.8: Stop measurement, snapshot results ───────────────
            print_step("3.8", "Stopping power measurement")
            meas = stop_core_measurement()

            power_w  = meas.get("power_w", 0.0)
            energy_j = meas.get("energy_j", 0.0)
            voltage_meas = meas.get("voltage_v", core_v)
            current_a    = meas.get("current_a", 0.0)

            print(f"  Voltage : {voltage_meas:.4f} V")
            print(f"  Current : {current_a*1000:.2f} mA")
            print(f"  Power   : {power_w*1000:.2f} mW")
            print(f"  Energy  : {energy_j*1000:.4f} mJ")

            # ── Log to CSV ─────────────────────────────────────────────────
            log_char_data(
                voltage_v=core_v,
                frequency_hz=freq_hz,
                pass_fail="pass" if passed else "fail",
                power_w=power_w,
                energy_j=energy_j,
                ber="",
                notes=f"divisor={clock_divisor}",
            )

            print(f"\n  ✓ Point {point_num}/{total_points} logged: "
                  f"{'PASS' if passed else 'FAIL'}  "
                  f"{power_w*1000:.1f} mW  {energy_j*1e6:.2f} µJ")

            # Short settle before next point
            time.sleep(0.2)

    # ── Step 3.10: Generate all shmoo plots ───────────────────────────────────
    print_banner("Sweep complete — generating plots")
    from utils.session_logger import get_char_data_path
    csv_path = get_char_data_path()

    if csv_path and os.path.exists(csv_path):
        print(f"  CSV: {csv_path}")
        saved = plot_all_shmoos(csv_path,
                                out_dir=PLOT_OUTPUT_DIR,
                                show=True)
        for p in saved:
            print(f"  Plot saved: {p}")
    else:
        print("  No char data CSV found for plotting.")

    print_banner("Done")


# =============================================================================
#  ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    try:
        run_sweep()
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Stopping measurement and disconnecting...")
        try:
            stop_core_measurement()
        except Exception:
            pass
        uart.disconnect()
        psu.disconnect()
        smu.disconnect()
        print("Cleanup done.")
        sys.exit(0)
