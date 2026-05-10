# ASIC Characterization Tool

Complete PC-side test and characterization tool for ASIC/FPGA boards.
Consists of two packages that work together:

```
asic_project/
├── API_REFERENCE.md          ← Full function reference for all modules
├── asic_auto/                ← Characterization package (hardware modules)
│   ├── main.py               ← Automation sweep script (no GUI)
│   ├── peripherals/          ← UART peripheral drivers
│   │   ├── uart_handler.py
│   │   ├── loopback.py
│   │   ├── level_setting.py
│   │   ├── awg.py
│   │   ├── pmic.py
│   │   ├── clock_ber.py
│   │   ├── chip_config.py
│   │   ├── adc.py
│   │   └── raw_uart.py
│   ├── instruments/          ← Bench instrument drivers
│   │   ├── smu_2602b.py      ← Keithley 2602B (TSP over USB)
│   │   └── psu_2230g.py      ← Keithley 2230G (SCPI over USB)
│   ├── utils/
│   │   ├── pmic_vset_table.py
│   │   ├── pmic_registers.py
│   │   ├── session_logger.py
│   │   └── plot_shmoo.py
│   ├── sessions/             ← Auto-created CSV logs go here
│   ├── plots/                ← Auto-created PNG plots go here
│   └── requirements.txt
└── asic_gui/                 ← PyQt5 GUI on top of asic_auto
    ├── main_gui.py           ← GUI entry point  ← RUN THIS
    ├── style/theme.py        ← Dark + light QSS themes
    ├── workers/              ← QThread worker
    ├── gui/
    │   ├── main_window.py
    │   ├── settings_panel.py
    │   ├── log_panel.py
    │   ├── widgets.py
    │   ├── graph_window.py
    │   └── tabs/
    │       ├── link_config/  ← Loopback · Chip Config · Raw UART
    │       ├── signal/       ← Level Setting · AWG · Clock+BER · ADC
    │       └── power/        ← PMIC · SMU · PSU
    └── requirements.txt
```

---

## Setup

### Install dependencies (one command installs everything)

```bash
pip install PyQt5 pyserial pyvisa pyvisa-py matplotlib numpy pandas
```

For PyVISA USB backend on Linux:
```bash
pip install pyusb
# Also may need: sudo apt install libusb-1.0-0
```

---

## Run the GUI

```bash
cd asic_project
python asic_gui/main_gui.py
```

The GUI automatically adds `asic_auto/` to the Python path.

---

## Run the automation script (no GUI)

Edit the CONFIG section at the top of `asic_auto/main.py`:

```python
UART_PORT        = "COM3"           # your serial port
CORE_INSTRUMENT  = "PSU"            # "PSU" or "SMU"
PSU_VISA         = "USB0::..."      # VISA address
CORE_VOLTAGES_V  = [0.9, 1.0, 1.1] # core voltage sweep
FREQUENCIES_HZ   = [25e6, 50e6]    # frequency sweep
BUCK1_VOLTAGE_MV = 1800.0           # IO rail 1 (fixed)
BUCK2_VOLTAGE_MV = 3300.0           # IO rail 2 (fixed)
```

Then run:
```bash
cd asic_project
python asic_auto/main.py
```

---

## UART Protocol Summary

```
Packet:  [SOF:1][ID:1][LEN:1][DATA:N]

SOF:  0xAA = Write     0x55 = Read
      0x5A = ACK OK    0xA5 = ACK Error

Port: 115200 baud, RTS/CTS hardware flow control
```

| Peripheral     | ID     | Mode  |
|----------------|--------|-------|
| Loopback       | 0x00   | R     |
| Level Setting  | 0x02   | W     |
| PMIC           | 0x04   | R/W   |
| Chip Config    | 0x08   | R     |
| ADC            | 0x20   | R/W   |
| AWG            | 0x40   | W     |
| Clock + BER    | 0x80   | R/W   |

---

## GUI Tab Structure

```
🔗 Link & Config
    ├── Loopback       — link health check
    ├── Chip Config    — DUT configuration trigger
    └── Raw UART       — manual hex TX/RX

📡 Signal
    ├── Level Setting  — LTC2656 DAC + linearity sweep plot
    ├── AWG            — DDS waveform generator
    ├── Clock + BER    — clock set + BER sweep plot
    └── ADC            — 16-bit 8-channel ADC + scan

⚡ Power
    ├── PMIC           — MCP16701 Buck/LDO voltage control
    ├── SMU 2602B      — voltage source + power measurement
    └── PSU 2230G      — voltage source + power measurement
```

Toolbar buttons:
- **☀ Light / 🌙 Dark** — theme toggle
- **📈 Plot Viewer** — shmoo plot window (loads char CSV)
- **📋 Log Panel** — toggle TX/RX log dock

---

## Output Files

All outputs written to `asic_auto/sessions/` and `asic_auto/plots/`:

| File | Contents |
|------|----------|
| `sessions/session_YYYYMMDD_HHMMSS.csv` | Every TX/RX with timestamp |
| `sessions/char_data_YYYYMMDD_HHMMSS.csv` | Sweep results (V, F, pass/fail, power, energy) |
| `plots/shmoo_passfail_*.png` | Pass/fail shmoo |
| `plots/shmoo_power_*.png` | Power shmoo heatmap |
| `plots/shmoo_energy_*.png` | Energy shmoo heatmap |

---

## PMIC Address Quick Reference

```
OPCODE_H = (1 << 2) | (addr[9:8])
OPCODE_L = addr[7:0]

Buck1: VSET0=0x21F VSET1=0x220    Buck5: VSET0=0x23F VSET1=0x240
Buck2: VSET0=0x227 VSET1=0x228    Buck6: VSET0=0x247 VSET1=0x248
Buck3: VSET0=0x22F VSET1=0x230    Buck7: VSET0=0x24F VSET1=0x250
Buck4: VSET0=0x237 VSET1=0x238    Buck8: VSET0=0x257 VSET1=0x258
LDO1:  VSET0=0x25E VSET1=0x25F    LDO3:  VSET0=0x26C VSET1=0x26D
LDO2:  VSET0=0x265 VSET1=0x266    LDO4:  VSET0=0x273 VSET1=0x274
```

See `API_REFERENCE.md` for full function signatures and return values.
