# instruments/psu_2230g.py
# Keithley 2230G-30-1 Triple-Output PSU over USB via PyVISA + SCPI
# Used for core voltage supply and power measurement.

import time
import threading

try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False
    print("[PSU] pyvisa not installed. PSU functions unavailable.")

_rm = None
_inst = None
_lock = threading.Lock()

# Measurement thread control
_meas_thread = None
_meas_stop_event = threading.Event()
_latest_measurement = {
    "voltage_v": 0.0,
    "current_a": 0.0,
    "power_w": 0.0,
    "energy_j": 0.0,
    "elapsed_s": 0.0,
    "status": "idle",
}
_meas_lock = threading.Lock()


def connect(visa_address):
    """
    Connect to PSU 2230G via VISA USB address.
    e.g. visa_address = "USB0::0x05E6::0x2230::xxxxxxxx::INSTR"
    Returns True on success.
    """
    global _rm, _inst
    if not PYVISA_AVAILABLE:
        print("[PSU] pyvisa not available")
        return False
    try:
        _rm = pyvisa.ResourceManager()
        _inst = _rm.open_resource(visa_address)
        _inst.timeout = 10000
        idn = _inst.query("*IDN?")
        print(f"[PSU] Connected: {idn.strip()}")
        return True
    except Exception as e:
        print(f"[PSU] Connection failed: {e}")
        _inst = None
        return False


def disconnect():
    global _inst, _rm
    PSU_measure_stop()
    if _inst:
        try:
            _inst.close()
        except Exception:
            pass
        _inst = None
    if _rm:
        _rm.close()
        _rm = None
    print("[PSU] Disconnected")


def is_connected():
    return _inst is not None


def PSU_vset(channel, voltage):
    """
    Set output voltage on PSU channel (1, 2, or 3).
    voltage: float in Volts (0–30V)
    Enables the channel output.
    """
    if not is_connected():
        return {"status": "not_connected"}

    if channel not in (1, 2, 3):
        return {"status": "error", "error": "channel must be 1, 2, or 3"}

    with _lock:
        try:
            _inst.write(f"INST CH{channel}")
            _inst.write(f"VOLT {voltage:.3f}")
            _inst.write("OUTP ON")
            return {"status": "ok", "channel": channel,
                    "voltage_set": voltage}
        except Exception as e:
            return {"status": "error", "error": str(e)}


def _measure_loop(channel, stop_event):
    """Background thread: measure V and I every 500ms, accumulate energy."""
    start_time = time.time()
    energy_j = 0.0
    last_time = start_time

    with _meas_lock:
        _latest_measurement["status"] = "measuring"
        _latest_measurement["energy_j"] = 0.0

    while not stop_event.is_set():
        try:
            with _lock:
                _inst.write(f"INST CH{channel}")
                v = float(_inst.query("MEAS:VOLT?"))
                i = float(_inst.query("MEAS:CURR?"))

            p = v * i
            now = time.time()
            dt = now - last_time
            last_time = now
            energy_j += p * dt
            elapsed = now - start_time

            with _meas_lock:
                _latest_measurement.update({
                    "voltage_v": round(v, 4),
                    "current_a": round(i, 4),
                    "power_w": round(p, 6),
                    "energy_j": round(energy_j, 6),
                    "elapsed_s": round(elapsed, 3),
                    "status": "measuring",
                })
        except Exception as e:
            with _meas_lock:
                _latest_measurement["status"] = f"error: {e}"

        stop_event.wait(0.5)

    with _meas_lock:
        _latest_measurement["status"] = "idle"


def PSU_measure_start(channel=1):
    """Start background power measurement thread on given channel."""
    global _meas_thread, _meas_stop_event

    if _meas_thread and _meas_thread.is_alive():
        PSU_measure_stop()

    _meas_stop_event = threading.Event()
    _meas_thread = threading.Thread(
        target=_measure_loop,
        args=(channel, _meas_stop_event),
        daemon=True,
        name="PSU_measure",
    )
    _meas_thread.start()
    print(f"[PSU] Measurement started on CH{channel}")


def PSU_measure_stop():
    """Stop background measurement thread and return final snapshot."""
    _meas_stop_event.set()
    if _meas_thread and _meas_thread.is_alive():
        _meas_thread.join(timeout=3.0)
    print("[PSU] Measurement stopped")
    with _meas_lock:
        return dict(_latest_measurement)


def get_measurement():
    """Return latest measurement snapshot (non-blocking)."""
    with _meas_lock:
        return dict(_latest_measurement)
