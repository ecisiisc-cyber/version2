# peripherals/raw_uart.py
# Raw UART TX/RX — bypass mode, no packet wrapping.

import peripherals.uart_handler as uart
import time


def uart_tx_packet(hex_string):
    """
    Parse hex string and send raw bytes.
    hex_string: space-separated or plain hex, e.g. "AA 02 03 78 9A BC"
    Returns dict: status, bytes_sent, tx_hex
    """
    if not uart.is_connected():
        return {"status": "not_connected", "error": "UART is not connected",
                "bytes_sent": 0, "tx": b"", "tx_hex": ""}

    hex_clean = hex_string.replace(" ", "").replace("0x", "").replace(",", "")
    try:
        raw = bytes.fromhex(hex_clean)
    except ValueError as e:
        return {"status": "error", "error": f"Invalid hex: {e}",
                "bytes_sent": 0, "tx_hex": hex_string}

    success = uart.send_raw(raw)
    return {
        "status": "ok" if success else "error",
        "bytes_sent": len(raw),
        "tx": raw,
        "tx_hex": raw.hex(" ").upper(),
    }


def uart_rx_packet(size, timeout_s=5.0):
    """
    Read exactly 'size' bytes from RX buffer.
    Returns dict: status, data (bytes), hex string
    """
    if not uart.is_connected():
        return {"status": "not_connected", "data": b"",
                "bytes_received": 0, "hex": ""}

    data = uart.read_raw(size, timeout_s=timeout_s)
    return {
        "status": "ok" if len(data) == size else "timeout",
        "data": data,
        "bytes_received": len(data),
        "hex": data.hex(" ").upper() if data else "",
    }


def wait_for_byte(target_byte, timeout_s=300.0):
    """
    Poll RX buffer until target_byte is seen or timeout.
    Used for self-test ACK (e.g. 0xFA = pass).
    Returns dict: status ("found"|"timeout"), elapsed_s
    """
    deadline = time.time() + timeout_s
    elapsed = 0.0
    while time.time() < deadline:
        data = uart.read_raw(1, timeout_s=0.5)
        if data and data[0] == target_byte:
            elapsed = time.time() - (deadline - timeout_s)
            return {"status": "found", "byte": target_byte,
                    "elapsed_s": elapsed}
    return {"status": "timeout", "byte": target_byte,
            "elapsed_s": timeout_s}
