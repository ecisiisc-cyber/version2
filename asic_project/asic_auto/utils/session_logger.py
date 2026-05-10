# utils/session_logger.py
# Logs all TX/RX transactions and characterization data to CSV files.

import csv
import os
import datetime

_session_dir = "sessions"
_session_start = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
_tx_rx_path = None
_char_path = None

# CSV headers
TX_RX_HEADERS = [
    "timestamp", "direction", "peripheral",
    "raw_hex", "parsed_summary", "status",
]
CHAR_HEADERS = [
    "timestamp", "voltage_v", "frequency_hz",
    "pass_fail", "power_w", "energy_j",
    "ber", "temperature_c", "notes",
]


def _ensure_dir():
    os.makedirs(_session_dir, exist_ok=True)


def init_session(label=""):
    """
    Create new session CSV files with timestamped names.
    Call once at the start of each automation run.
    """
    global _session_start, _tx_rx_path, _char_path
    _ensure_dir()
    _session_start = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    _tx_rx_path = os.path.join(
        _session_dir, f"session_{_session_start}{suffix}.csv")
    _char_path = os.path.join(
        _session_dir, f"char_data_{_session_start}{suffix}.csv")

    # Write headers
    for path, headers in [(_tx_rx_path, TX_RX_HEADERS),
                           (_char_path, CHAR_HEADERS)]:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(headers)

    print(f"[Logger] Session log : {_tx_rx_path}")
    print(f"[Logger] Char data   : {_char_path}")
    return _tx_rx_path, _char_path


def log_transaction(direction, peripheral, raw_bytes,
                    parsed_summary="", status="ok"):
    """
    Log one TX or RX event.
    direction    : "TX" or "RX"
    peripheral   : name string e.g. "PMIC"
    raw_bytes    : bytes object
    parsed_summary: short human-readable string
    status       : "ok" | "error" | "timeout" etc.
    """
    if not _tx_rx_path:
        return
    ts = datetime.datetime.now().isoformat(timespec="milliseconds")
    hex_str = raw_bytes.hex(" ").upper() if raw_bytes else ""
    with open(_tx_rx_path, "a", newline="") as f:
        csv.writer(f).writerow(
            [ts, direction, peripheral, hex_str, parsed_summary, status])


def log_char_data(voltage_v, frequency_hz, pass_fail,
                  power_w=0.0, energy_j=0.0, ber="",
                  temperature_c="", notes=""):
    """
    Log one characterization data point.
    pass_fail: "pass" or "fail"
    """
    if not _char_path:
        return
    ts = datetime.datetime.now().isoformat(timespec="milliseconds")
    with open(_char_path, "a", newline="") as f:
        csv.writer(f).writerow([
            ts, voltage_v, frequency_hz, pass_fail,
            power_w, energy_j, ber, temperature_c, notes,
        ])


def get_char_data_path():
    return _char_path


def get_session_log_path():
    return _tx_rx_path
