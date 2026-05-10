# ASIC Characterization Package — API Reference

All functions live in `asic_auto/`.
Import pattern:  `from peripherals.loopback import loop_back`

Return values marked with `→ dict` always contain at minimum:
  `status`  : "ok" | "error" | "timeout" | "invalid" | "not_connected"
  `tx`      : bytes sent
  `rx`      : bytes received

---

## 1. uart_handler  (`peripherals/uart_handler.py`)

Manages the single shared serial port. Call `connect()` first.
All other peripheral modules use this internally.

| Function | Arguments | Returns |
|---|---|---|
| `list_ports()` | — | `list[str]` — available COM port names |
| `connect(port, baud=115200, timeout=2.0)` | `port`: str e.g. "COM3" / "/dev/ttyUSB0"<br>`baud`: int (fixed 115200)<br>`timeout`: float seconds | `bool` — True if opened successfully |
| `disconnect()` | — | `None` |
| `is_connected()` | — | `bool` |
| `send_packet(sof, peripheral_id, data)` | `sof`: int SOF byte (0xAA/0x55)<br>`peripheral_id`: int ID byte<br>`data`: bytes payload | `dict` → `status`, `tx`, `rx` |
| `read_raw(size, timeout_s=5.0)` | `size`: int bytes to read<br>`timeout_s`: float | `bytes` — may be fewer than size on timeout |
| `send_raw(data)` | `data`: bytes | `bool` — True if sent |
| `flush_rx()` | — | `None` |

---

## 2. loopback  (`peripherals/loopback.py`)

| Function | Arguments | Returns |
|---|---|---|
| `loop_back()` | — | `dict` |

**Return dict keys:**
```
status  : "ok" | "mismatch" | "timeout" | "not_connected"
echo    : list[int]  — 4 bytes echoed back e.g. [0x11,0x22,0x33,0x44]
match   : bool       — True if echo == [0x11,0x22,0x33,0x44]
tx      : bytes      — raw bytes sent
rx      : bytes      — raw bytes received
```

---

## 3. level_setting  (`peripherals/level_setting.py`)

LTC2656 Octal 16-bit DAC. 2.5 V reference. Channels 0–7 (A–H).
CMD constants: `CMD_WRITE_UPDATE=0x3`  `CMD_POWER_DOWN=0x4`  `CMD_WRITE_UPDATE_ALL=0xF`

| Function | Arguments | Returns |
|---|---|---|
| `level_set_dac_analog(channel, value_mv, cmd=0x3)` | `channel`: int 0–7 (A–H)<br>`value_mv`: float 0.0–2500.0 mV<br>`cmd`: int command nibble | `dict` |
| `level_set_dac_digital(channel, digital_value, cmd=0x3)` | `channel`: int 0–7<br>`digital_value`: int 0–65535<br>`cmd`: int command nibble | `dict` |
| `level_set(d0, d1, d2)` | `d0`: int (cmd nibble \| channel)<br>`d1`: int value MSB<br>`d2`: int value LSB | `dict` |

**Return dict keys (analog/digital):**
```
status        : "ok" | "error" | ...
channel_name  : str  — "A" through "H"
value_mv      : float — voltage sent in mV
counts        : int  — 16-bit DAC code used  (analog only)
digital_value : int  — code used             (digital only)
d0, d1, d2    : int  — raw bytes sent
tx            : bytes
rx            : bytes  — expect 5A 5A on success
parsed        : {"ack_count": int}
```

---

## 4. awg  (`peripherals/awg.py`)

DDS Arbitrary Waveform Generator. ID 0x40.
Formula: `Fs = 100MHz / (2 × clock_divisor)`,  `Fout = Fs × inc / 65536`

| Function | Arguments | Returns |
|---|---|---|
| `awg(clock_divisor, inc)` | `clock_divisor`: int 1–65535<br>`inc`: int 0–65535 | `dict` |
| `awg_set_frequency(fout_hz, clock_divisor=1)` | `fout_hz`: float Hz (1–50MHz)<br>`clock_divisor`: int 1–65535 | `dict` |

**Return dict keys:**
```
status          : "ok" | "error" | ...
clock_divisor   : int   — divisor used
inc             : int   — DDS increment used
fs_hz           : float — sampling frequency Hz
actual_fout_hz  : float — actual output frequency Hz
nyquist_warning : bool  — True if inc > 32767 (Fout > Fs/2)
tx              : bytes
rx              : bytes — expect 5A on success
```

---

## 5. pmic  (`peripherals/pmic.py`)

MCP16701 — 8 Buck + 4 LDO regulators. ID 0x04.
**Always call `unlock_pmic()` before writing any voltage.**

| Function | Arguments | Returns |
|---|---|---|
| `unlock_pmic()` | — | `dict` |
| `set_buck_voltage(buck_num, voltage_mv)` | `buck_num`: int 1–8<br>`voltage_mv`: float 600–3800 mV | `dict` |
| `set_ldo_voltage(ldo_num, voltage_mv)` | `ldo_num`: int 1–4<br>`voltage_mv`: float 600–1600 mV | `dict` |
| `pmic_write(reg_addr, value)` | `reg_addr`: int 10-bit (e.g. 0x22F)<br>`value`: int 0x00–0xFF | `dict` |
| `pmic_read(reg_addr)` | `reg_addr`: int 10-bit | `dict` |
| `pmic_generic_write(reg_addr, value)` | same as pmic_write | `dict` |
| `pmic_generic_read(reg_addr)` | same as pmic_read | `dict` |

**Return dict keys — set_buck_voltage / set_ldo_voltage:**
```
status        : "ok" | "error"
buck_num      : int   — regulator number
requested_mv  : float — voltage you asked for
actual_mv     : float — nearest valid voltage applied
vset_code     : int   — 8-bit VSET code written
warning       : str   — clamping warning if out of range
vset0_result  : dict  — result of writing VSET0 register
vset1_result  : dict  — result of writing VSET1 register
```

**Return dict keys — pmic_read / pmic_generic_read:**
```
status      : "ok" | "error"
reg_addr    : int   — address read
opcode_h    : int   — computed OPCODE_H byte
opcode_l    : int   — computed OPCODE_L byte
value_read  : int   — raw byte returned (0x00–0xFF)
voltage_mv  : float — decoded voltage in mV (from VSET table)
tx          : bytes
rx          : bytes — 5A [value]
```

---

## 6. clock_ber  (`peripherals/clock_ber.py`)

Clock Generator and BER counter. ID 0x80.
Formula: `f_out = 100MHz / (2 × divisor)`

| Function | Arguments | Returns |
|---|---|---|
| `clock(divisor)` | `divisor`: int 1–2147483647 | `dict` |
| `clock_set_frequency(freq_hz)` | `freq_hz`: float Hz (1–50MHz) | `dict` |
| `read_ber()` | — | `dict` |
| `sweep_ber(freq_list, log_callback=None)` | `freq_list`: list[float] Hz values<br>`log_callback`: callable(dict) or None | `list[dict]` |

**Return dict keys — clock / clock_set_frequency:**
```
status            : "ok" | "error"
divisor           : int   — divisor used
f_out_hz          : float — actual output frequency Hz
requested_freq_hz : float — frequency you asked for (set_frequency only)
actual_freq_hz    : float — frequency achieved     (set_frequency only)
tx                : bytes
rx                : bytes — 5A 5A on success
```

**Return dict keys — read_ber:**
```
status    : "ok" | "error"
ber_raw   : int        — 16-bit BER count (0–65535), None on error
ber_bytes : list[int]  — [BER_B1, BER_B2]
tx        : bytes
rx        : bytes — 5A [B1][B2]
```

**Return list items — sweep_ber:**
```
Each item is a dict:
  freq_hz      : float — frequency for this point
  clock_result : dict  — result from clock_set_frequency()
  ber_result   : dict  — result from read_ber()
  ber_raw      : int | None
```

---

## 7. chip_config  (`peripherals/chip_config.py`)

| Function | Arguments | Returns |
|---|---|---|
| `chip_config()` | — | `dict` |

**Return dict keys:**
```
status        : "ok" | "error"
config_status : "success" | "failed" | "unknown"
raw_status    : int  — 0x11=success, 0x22=failed
tx            : bytes — 55 08 01 55
rx            : bytes — 5A [status]
```

---

## 8. adc  (`peripherals/adc.py`)

16-bit unipolar ADC. 2.5 V reference. 8 channels (0–7).
Voltage formula: `(raw / 65535) × 2500 mV`

| Function | Arguments | Returns |
|---|---|---|
| `adc_write(channel)` | `channel`: int 0–7 | `dict` |
| `adc_read()` | — | `dict` |
| `adc_read_channel(channel)` | `channel`: int 0–7 | `dict` |
| `adc_scan_all()` | — | `dict` |

**Return dict keys — adc_read / adc_read_channel:**
```
status     : "ok" | "error"
channel    : int   — channel read
raw        : int   — 16-bit count 0–65535,  None on error
voltage_mv : float — mV 0.0–2500.0,         None on error
binary     : str   — "0111111111111111" 16-char binary string
tx         : bytes
rx         : bytes — 5A [MSB][LSB]
```

**Return dict keys — adc_scan_all:**
```
status   : "ok"
channels : {
    0: {"raw": int, "voltage_mv": float, "status": str},
    1: {...},
    ...
    7: {...}
}
```

---

## 9. raw_uart  (`peripherals/raw_uart.py`)

| Function | Arguments | Returns |
|---|---|---|
| `uart_tx_packet(hex_string)` | `hex_string`: str e.g. `"AA 02 03 78 9A BC"` | `dict` |
| `uart_rx_packet(size, timeout_s=5.0)` | `size`: int 1–255<br>`timeout_s`: float | `dict` |
| `wait_for_byte(target_byte, timeout_s=300.0)` | `target_byte`: int 0x00–0xFF<br>`timeout_s`: float | `dict` |

**Return dict keys — uart_tx_packet:**
```
status      : "ok" | "error"
bytes_sent  : int   — number of bytes sent
tx          : bytes — raw bytes sent
tx_hex      : str   — e.g. "AA 02 03 78 9A BC"
```

**Return dict keys — uart_rx_packet:**
```
status         : "ok" | "timeout"
data           : bytes — raw bytes received
bytes_received : int
hex            : str   — space-separated uppercase hex
```

**Return dict keys — wait_for_byte:**
```
status    : "found" | "timeout"
byte      : int   — target byte waited for
elapsed_s : float — time taken in seconds
```

---

## 10. smu_2602b  (`instruments/smu_2602b.py`)

Keithley 2602B over USB + PyVISA. Uses TSP scripting.

| Function | Arguments | Returns |
|---|---|---|
| `connect(visa_address)` | `visa_address`: str e.g. `"USB0::0x05E6::0x2602::SERIAL::INSTR"` | `bool` |
| `disconnect()` | — | `None` |
| `is_connected()` | — | `bool` |
| `SMU_vset(channel, voltage)` | `channel`: str `"a"` or `"b"`<br>`voltage`: float Volts (-200 to 200) | `dict` |
| `SMU_measure_start(channel="a")` | `channel`: str `"a"` or `"b"` | `None` — starts background thread |
| `SMU_measure_stop()` | — | `dict` — final measurement snapshot |
| `get_measurement()` | — | `dict` — latest snapshot (non-blocking) |

**Return dict keys — SMU_vset:**
```
status      : "ok" | "error" | "not_connected"
channel     : str   — "a" or "b"
voltage_set : float — voltage configured
```

**Return dict keys — get_measurement / SMU_measure_stop:**
```
voltage_v  : float — measured voltage V
current_a  : float — measured current A
power_w    : float — instantaneous power W  (V × I)
energy_j   : float — accumulated energy J   (∫P dt)
elapsed_s  : float — measurement duration s
status     : "measuring" | "idle" | "error: <msg>"
```

---

## 11. psu_2230g  (`instruments/psu_2230g.py`)

Keithley 2230G-30-1 over USB + PyVISA. Uses SCPI commands.

| Function | Arguments | Returns |
|---|---|---|
| `connect(visa_address)` | `visa_address`: str e.g. `"USB0::0x05E6::0x2230::SERIAL::INSTR"` | `bool` |
| `disconnect()` | — | `None` |
| `is_connected()` | — | `bool` |
| `PSU_vset(channel, voltage)` | `channel`: int 1, 2, or 3<br>`voltage`: float Volts (0–30) | `dict` |
| `PSU_measure_start(channel=1)` | `channel`: int 1–3 | `None` — starts background thread |
| `PSU_measure_stop()` | — | `dict` — final snapshot |
| `get_measurement()` | — | `dict` — latest snapshot (non-blocking) |

**Return dict keys — PSU_vset:**
```
status      : "ok" | "error" | "not_connected"
channel     : int   — 1, 2, or 3
voltage_set : float — voltage configured
```

**Return dict keys — get_measurement / PSU_measure_stop:**
```
voltage_v  : float
current_a  : float
power_w    : float
energy_j   : float
elapsed_s  : float
status     : "measuring" | "idle" | "error: <msg>"
```

---

## 12. pmic_vset_table  (`utils/pmic_vset_table.py`)

| Function | Arguments | Returns |
|---|---|---|
| `vset_from_voltage(target_mv, is_ldo=False)` | `target_mv`: float mV<br>`is_ldo`: bool (caps max at 1600 mV) | `tuple(vset_code, actual_mv, warning_str)` |
| `voltage_from_vset(vset_code)` | `vset_code`: int 0x00–0xFF | `float` mV or `None` |

**Examples:**
```python
code, mv, warn = vset_from_voltage(1000.0)
# → (0x50, 1000.0, "")

code, mv, warn = vset_from_voltage(1800.0)
# → (0x88, 1800.0, "")

code, mv, warn = vset_from_voltage(2000.0, is_ldo=True)
# → (0x9F, 1600.0, "Clamped to maximum 1600.0 mV")

mv = voltage_from_vset(0x50)
# → 1000.0
```

---

## 13. pmic_registers  (`utils/pmic_registers.py`)

| Function / Constant | Description |
|---|---|
| `compute_opcodes(reg_addr)` | `reg_addr`: int 10-bit address → `tuple(opcode_h, opcode_l)` |
| `BUCK_REGS` | `dict` — `{1: {"VSET0": 0x21F, "VSET1": 0x220}, 2: ..., 8: ...}` |
| `LDO_REGS`  | `dict` — `{1: {"VSET0": 0x25E, "VSET1": 0x25F}, 2: ..., 4: ...}` |

**Example:**
```python
h, l = compute_opcodes(0x22F)   # Buck3 VSET0
# → (0x06, 0x2F)
# TX write: AA 04 04 AA 06 2F [VSET]
```

---

## 14. session_logger  (`utils/session_logger.py`)

| Function | Arguments | Returns |
|---|---|---|
| `init_session(label="")` | `label`: str optional suffix | `tuple(tx_rx_path, char_path)` — file paths created |
| `log_transaction(direction, peripheral, raw_bytes, parsed_summary="", status="ok")` | `direction`: "TX" or "RX"<br>`peripheral`: str name<br>`raw_bytes`: bytes<br>`parsed_summary`: str<br>`status`: str | `None` |
| `log_char_data(voltage_v, frequency_hz, pass_fail, power_w=0.0, energy_j=0.0, ber="", temperature_c="", notes="")` | see column names | `None` |
| `get_session_log_path()` | — | `str` path to TX/RX CSV |
| `get_char_data_path()` | — | `str` path to char data CSV |

**CSV columns — session log:**
```
timestamp, direction, peripheral, raw_hex, parsed_summary, status
```

**CSV columns — char data:**
```
timestamp, voltage_v, frequency_hz, pass_fail,
power_w, energy_j, ber, temperature_c, notes
```

---

## 15. plot_shmoo  (`utils/plot_shmoo.py`)

All functions save PNG to `out_dir` and optionally display on screen.

| Function | Arguments | Returns |
|---|---|---|
| `plot_passfail_shmoo(csv_path, out_dir="plots", show=True)` | `csv_path`: str<br>`out_dir`: str<br>`show`: bool | `str` saved PNG path |
| `plot_power_shmoo(csv_path, out_dir="plots", show=True)` | same | `str` |
| `plot_energy_shmoo(csv_path, out_dir="plots", show=True)` | same | `str` |
| `plot_multivar(csv_path, x_col, y_cols, threshold=None, threshold_color="red", log_x=False, log_y=False, out_dir="plots", show=True)` | `x_col`: str column name<br>`y_cols`: list[str] column names<br>`threshold`: float or None | `str` |
| `plot_ber_vs_freq(csv_path, log_y=True, out_dir="plots", show=True)` | `log_y`: bool log-scale Y axis | `str` |
| `plot_all_shmoos(csv_path, out_dir="plots", show=True)` | runs passfail + power + energy | `list[str]` — 3 PNG paths |

**Required CSV columns per plot:**
```
plot_passfail_shmoo : voltage_v, frequency_hz, pass_fail  (1/0 or "pass"/"fail")
plot_power_shmoo    : voltage_v, frequency_hz, power_w
plot_energy_shmoo   : voltage_v, frequency_hz, energy_j
plot_ber_vs_freq    : frequency_hz, ber
plot_multivar       : any columns — user specifies x_col and y_cols
```

---

## Quick usage example

```python
import peripherals.uart_handler as uart
from peripherals.loopback       import loop_back
from peripherals.pmic           import unlock_pmic, set_buck_voltage
from peripherals.clock_ber      import clock_set_frequency, read_ber
from peripherals.adc            import adc_read_channel
from instruments.psu_2230g      import PSU_vset, PSU_measure_start, PSU_measure_stop
from utils.session_logger       import init_session, log_char_data
from utils.plot_shmoo           import plot_all_shmoos

# Connect
uart.connect("COM3")
result = loop_back()
print(result["match"])          # True

# PMIC
unlock_pmic()
set_buck_voltage(1, 1800.0)     # Buck1 → 1.8 V
# → {"status":"ok", "actual_mv":1800.0, "vset_code":0x88, ...}

# Clock
clock_set_frequency(25e6)
# → {"status":"ok", "divisor":2, "actual_freq_hz":25000000.0, ...}

# BER
r = read_ber()
print(r["ber_raw"])             # int 0–65535

# ADC
r = adc_read_channel(3)         # CH3
print(r["voltage_mv"])          # e.g. 1234.5

# PSU power measurement
PSU_vset(1, 1.0)
PSU_measure_start(1)
import time; time.sleep(5)
m = PSU_measure_stop()
print(m["power_w"], m["energy_j"])

# Log and plot
init_session("my_test")
log_char_data(1.0, 25e6, "pass", m["power_w"], m["energy_j"])
plot_all_shmoos("sessions/char_data_*.csv")
```
