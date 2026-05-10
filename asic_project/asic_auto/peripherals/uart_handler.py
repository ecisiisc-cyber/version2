# peripherals/uart_handler.py
# Manages the serial UART connection to the FPGA/ASIC board.
# Protocol: 115200 baud, RTS/CTS enabled, packet format [SOF][ID][LEN][DATA...]

import time
import threading

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
    _SERIAL_IMPORT_ERROR = ""
    _SERIAL_ERRORS = (serial.SerialException, OSError)
except ImportError as e:
    serial = None
    SERIAL_AVAILABLE = False
    _SERIAL_IMPORT_ERROR = str(e)
    _SERIAL_ERRORS = (OSError,)

# SOF byte constants
SOF_WRITE   = 0xAA
SOF_READ    = 0x55
SOF_ACK_OK  = 0x5A
SOF_ACK_ERR = 0xA5

_ser = None
_lock = threading.Lock()
_last_error = ""
_connection = {
    "port": "",
    "baud": 115200,
    "timeout": 2.0,
    "rtscts": True,
}


def list_ports():
    """Return list of available COM port names."""
    if not SERIAL_AVAILABLE:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


def connect(port, baud=115200, timeout=2.0, rtscts=True):
    """
    Open the serial port with RTS/CTS flow control.
    Returns True on success, False on failure.
    """
    global _ser, _last_error, _connection
    port = (port or "").strip()
    if not SERIAL_AVAILABLE:
        _last_error = f"pyserial is not installed: {_SERIAL_IMPORT_ERROR}"
        return False

    if not port:
        _last_error = "No COM port selected"
        return False

    with _lock:
        try:
            if _ser and _ser.is_open:
                _ser.close()

            _ser = serial.Serial(
                port=port,
                baudrate=baud,
                rtscts=rtscts,
                dsrdtr=False,
                timeout=timeout,
                write_timeout=timeout,
            )
            _ser.reset_input_buffer()
            _ser.reset_output_buffer()
            _connection = {
                "port": port,
                "baud": baud,
                "timeout": timeout,
                "rtscts": rtscts,
            }
            _last_error = ""
            flow = "RTS/CTS" if rtscts else "no flow control"
            print(f"[UART] Connected to {port} at {baud} baud ({flow})")
            return True
        except _SERIAL_ERRORS as e:
            print(f"[UART] Connection failed: {e}")
            _last_error = str(e)
            _ser = None
            return False


def disconnect():
    """Close the serial port."""
    global _ser
    with _lock:
        if _ser and _ser.is_open:
            _ser.close()
            print("[UART] Disconnected")
        _ser = None


def is_connected():
    return _ser is not None and _ser.is_open


def get_last_error():
    """Return the last UART connection or I/O error message."""
    return _last_error


def get_connection_info():
    """Return a snapshot of the active UART configuration."""
    return dict(_connection)


def send_packet(sof, peripheral_id, data: bytes):
    """
    Build and send a packet: [SOF][ID][LEN][DATA...]
    Reads and returns the full response bytes.
    Returns dict: {
        "status": "ok" | "error" | "invalid" | "timeout" | "not_connected",
        "tx":     bytes sent,
        "rx":     bytes received,
    }
    """
    if not is_connected():
        return {"status": "not_connected", "tx": b"", "rx": b""}

    packet = bytes([sof, peripheral_id, len(data)]) + data

    with _lock:
        try:
            _ser.reset_input_buffer()
            _ser.write(packet)
            _ser.flush()
            time.sleep(0.1)  # increased from 0.02 to 0.1 for slower boards

            # Read first byte — should be SOF_ACK_OK or SOF_ACK_ERR
            first = _ser.read(1)
            if not first:
                return {"status": "timeout", "tx": packet, "rx": b""}

            if first[0] == SOF_ACK_ERR:
                return {"status": "invalid", "tx": packet, "rx": first}

            # Read remaining bytes available
            time.sleep(0.1)  # increased from 0.05 to 0.1
            rest = _ser.read(_ser.in_waiting or 8)
            rx = first + rest

            return {"status": "ok", "tx": packet, "rx": rx}

        except _SERIAL_ERRORS as e:
            return {"status": "error", "tx": packet, "rx": b"",
                    "error": str(e)}


def read_raw(size, timeout_s=5.0):
    """
    Read exactly 'size' bytes from the RX buffer.
    Used for raw UART and self-test ACK polling.
    Returns bytes read (may be fewer if timeout).
    """
    if not is_connected():
        return b""

    deadline = time.time() + timeout_s
    buf = b""
    with _lock:
        old_timeout = _ser.timeout
        try:
            while len(buf) < size and time.time() < deadline:
                remaining = max(0.0, deadline - time.time())
                _ser.timeout = min(0.1, remaining)
                chunk = _ser.read(size - len(buf))
                if chunk:
                    buf += chunk
        except _SERIAL_ERRORS:
            return buf
        finally:
            _ser.timeout = old_timeout
    return buf


def send_raw(data: bytes):
    """Send raw bytes without any packet wrapping."""
    if not is_connected():
        return False
    with _lock:
        try:
            _ser.write(data)
            _ser.flush()
            return True
        except _SERIAL_ERRORS:
            return False


def flush_rx():
    """Flush the RX input buffer."""
    if is_connected():
        with _lock:
            _ser.reset_input_buffer()
