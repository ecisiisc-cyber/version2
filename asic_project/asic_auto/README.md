# ASIC Characterization Automation Tool

## Project Structure

```
asic_auto/
├── main.py                     # Automation entry point — edit CONFIG here
├── requirements.txt
├── peripherals/
│   ├── uart_handler.py         # Serial port connection and packet engine
│   ├── loopback.py             # Loopback test (ID 0x00)
│   ├── level_setting.py        # LTC2656 DAC (ID 0x02)
│   ├── awg.py                  # DDS waveform generator (ID 0x40)
│   ├── pmic.py                 # MCP16701 PMIC (ID 0x04)
│   ├── clock_ber.py            # Clock gen + BER (ID 0x80)
│   ├── chip_config.py          # DUT configuration (ID 0x08)
│   ├── adc.py                  # 16-bit ADC (ID 0x20)
│   └── raw_uart.py             # Raw UART TX/RX + ACK waiter
├── instruments/
│   ├── smu_2602b.py            # Keithley 2602B via PyVISA + TSP
│   └── psu_2230g.py            # Keithley 2230G via PyVISA + SCPI
└── utils/
    ├── pmic_vset_table.py      # MCP16701 VSET[7:0] lookup table
    ├── pmic_registers.py       # Buck/LDO register addresses + opcode math
    ├── session_logger.py       # CSV logging (TX/RX + char data)
    └── plot_shmoo.py           # All shmoo and line plot functions
```

## Setup

```bash
pip install -r requirements.txt
```

For PyVISA USB: also install the NI-VISA backend or use `pyvisa-py`:
```bash
pip install pyvisa-py pyusb
```

## Configuration

Open `main.py` and edit the **CONFIG** section at the top:

```python
UART_PORT        = "COM3"           # Your serial port
CORE_INSTRUMENT  = "PSU"            # "PSU" or "SMU"
PSU_VISA         = "USB0::..."      # VISA address for 2230G
SMU_VISA         = "USB0::..."      # VISA address for 2602B
CORE_PSU_CHANNEL = 1                # PSU channel for core supply
BUCK1_VOLTAGE_MV = 1800.0           # Fixed IO rail 1
BUCK2_VOLTAGE_MV = 3300.0           # Fixed IO rail 2
CORE_VOLTAGES_V  = [0.9, 1.0, 1.1] # Core voltage sweep points
FREQUENCIES_HZ   = [25e6, 50e6]    # Frequency sweep points
```

## Running

```bash
cd asic_auto
python main.py
```

## Sweep Flow (per operating point)

```
1. Connect UART → loopback test
2. Connect PSU/SMU
3. Set IO rails via PMIC (Buck 1 + Buck 2, fixed)
   For each core voltage:
     Set core voltage (PSU or SMU)
     For each frequency:
       3.4  Set clock via Clock Gen peripheral
       3.5  Chip config command → check 0x11 (success) / 0x22 (fail)
       3.6  Send self-test: 55 66 01 [clock_sel]
            Start power measurement in background thread
       3.7  Wait up to 5 min for ACK byte 0xFA (pass) or timeout (fail)
       3.8  Stop measurement, snapshot power + energy
            Log to char_data_YYYYMMDD_HHMMSS.csv
4. Generate shmoo plots (pass/fail, power, energy) → saved to plots/
```

## Threading Model

- **Main thread**: sweep sequencing, PMIC/clock/config commands, logging
- **meas_thread** (in PSU/SMU module): polls V+I every 500 ms, accumulates energy, stores in shared dict protected by a lock
- **selftest_ack thread**: sends self-test UART command, waits for 0xFA byte — runs concurrently with meas_thread so power is measured throughout the DUT test

The main thread calls `start_core_measurement()` then launches the
self-test thread, then waits for the self-test to complete, then calls
`stop_core_measurement()` for the final snapshot.

## Output Files

All output goes to `sessions/` directory:

| File | Contents |
|------|----------|
| `session_YYYYMMDD_HHMMSS.csv` | Every TX/RX transaction with timestamps |
| `char_data_YYYYMMDD_HHMMSS.csv` | One row per sweep point: voltage, frequency, pass/fail, power, energy |

Plots are saved to `plots/`:
- `shmoo_passfail_*.png`
- `shmoo_power_*.png`
- `shmoo_energy_*.png`

## Importing Modules in Your Own Scripts

```python
from peripherals.pmic import set_buck_voltage, unlock_pmic
from peripherals.clock_ber import clock_set_frequency
from peripherals.adc import adc_scan_all
from instruments.psu_2230g import PSU_vset, PSU_measure_start
from utils.plot_shmoo import plot_multivar, plot_passfail_shmoo
```

## PMIC Address Computation

`utils/pmic_registers.py` — `compute_opcodes(reg_addr)`:
```
reg_addr = 0x22F (BUCK3 VSET0)
  a9a8     = (0x22F >> 8) & 0x03 = 0x02
  a7a0     = 0x22F & 0xFF        = 0x2F
  opcode_h = (1 << 2) | 0x02    = 0x06
  opcode_l = 0x2F
  TX write : AA 04 04 AA 06 2F [VSET]
```

## VSET Voltage Lookup

The MCP16701 uses a non-linear 8-bit VSET code (Table 2-3).
Use `vset_from_voltage(target_mv)` to find the nearest valid code.
Ranges: 600–3800 mV (Buck), 600–1600 mV (LDO), 12.5 mV or 25 mV steps.
