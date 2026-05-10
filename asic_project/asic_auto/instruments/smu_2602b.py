# instruments/smu_2602b.py
# Keithley 2602B SMU over USB via PyVISA + TSP
# Used for core voltage supply and power measurement.

import time
import threading

try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False
    print("[SMU] pyvisa not installed. SMU functions unavailable.")

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
    Connect to SMU 2602B via VISA USB address.
    e.g. visa_address = "USB0::0x05E6::0x2602::xxxxxxxx::INSTR"
    Returns True on success.
    """
    global _rm, _inst
    if not PYVISA_AVAILABLE:
        print("[SMU] pyvisa not available")
        return False
    try:
        _rm = pyvisa.ResourceManager()
        _inst = _rm.open_resource(visa_address)
        _inst.timeout = 10000  # 10s
        # Reset and configure
        _inst.write("reset()")
        idn = _inst.query("print(localnode.model)")
        print(f"[SMU] Connected: {idn.strip()}")
        return True
    except Exception as e:
        print(f"[SMU] Connection failed: {e}")
        _inst = None
        return False


def disconnect():
    global _inst, _rm
    SMU_measure_stop()
    if _inst:
        try:
            _inst.close()
        except Exception:
            pass
        _inst = None
    if _rm:
        _rm.close()
        _rm = None
    print("[SMU] Disconnected")


def is_connected():
    return _inst is not None


def SMU_vset(channel, voltage):
    """
    Set output voltage on SMU channel.
    channel: "a" or "b"
    voltage: float in Volts
    Configures channel as voltage source, enables output.
    """
    if not is_connected():
        return {"status": "not_connected"}

    ch = channel.lower()
    if ch not in ("a", "b"):
        return {"status": "error", "error": "channel must be 'a' or 'b'"}

    tsp = f"""
smu{ch}.reset()
smu{ch}.source.func = smu{ch}.OUTPUT_DCVOLTS
smu{ch}.source.levelv = {voltage:.6f}
smu{ch}.source.limiti = 3.0
smu{ch}.measure.nplc = 1
smu{ch}.source.output = smu{ch}.OUTPUT_ON
"""
    with _lock:
        try:
            _inst.write(tsp)
            return {"status": "ok", "channel": ch,
                    "voltage_set": voltage}
        except Exception as e:
            return {"status": "error", "error": str(e)}


def _measure_loop(channel, stop_event):
    """Background thread: measure V, I, P every 500ms, accumulate energy."""
    ch = channel.lower()
    start_time = time.time()
    energy_j = 0.0
    last_time = start_time

    with _meas_lock:
        _latest_measurement["status"] = "measuring"
        _latest_measurement["energy_j"] = 0.0

    while not stop_event.is_set():
        try:
            with _lock:
                _inst.write(f"print(smu{ch}.measure.v(), "
                            f"smu{ch}.measure.i())")
                resp = _inst.read()

            parts = resp.strip().split("\t")
            if len(parts) >= 2:
                v = float(parts[0])
                i = float(parts[1])
                p = v * i
                now = time.time()
                dt = now - last_time
                last_time = now
                energy_j += p * dt
                elapsed = now - start_time

                with _meas_lock:
                    _latest_measurement.update({
                        "voltage_v": round(v, 6),
                        "current_a": round(i, 6),
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


def SMU_measure_start(channel="a"):
    """Start background power measurement thread."""
    global _meas_thread, _meas_stop_event

    if _meas_thread and _meas_thread.is_alive():
        SMU_measure_stop()

    _meas_stop_event = threading.Event()
    _meas_thread = threading.Thread(
        target=_measure_loop,
        args=(channel, _meas_stop_event),
        daemon=True,
        name="SMU_measure",
    )
    _meas_thread.start()
    print(f"[SMU] Measurement started on channel {channel.upper()}")


def SMU_measure_stop():
    """Stop background measurement thread and return final snapshot."""
    global _meas_thread
    _meas_stop_event.set()
    if _meas_thread and _meas_thread.is_alive():
        _meas_thread.join(timeout=3.0)
    print("[SMU] Measurement stopped")
    with _meas_lock:
        return dict(_latest_measurement)


def get_measurement():
    """Return latest measurement snapshot (non-blocking)."""
    with _meas_lock:
        return dict(_latest_measurement)
