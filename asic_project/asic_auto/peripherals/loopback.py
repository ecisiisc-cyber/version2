# peripherals/loopback.py
# Loopback test — ID 0x00
# Sends 4 test bytes and verifies the FPGA echoes them back.
# TX: 55 00 04 11 22 33 44
# RX: 5A 11 22 33 44

import peripherals.uart_handler as uart

PERIPHERAL_ID = 0x00
TEST_BYTES = bytes([0x11, 0x22, 0x33, 0x44])


def loop_back():
    """
    Send loopback test packet and verify echo.
    Returns dict:
      status  : "ok" | "error" | "mismatch" | "timeout" | "not_connected"
      echo    : list of received echo bytes
      match   : True if echo matches TEST_BYTES
      tx      : raw bytes sent
      rx      : raw bytes received
    """
    result = uart.send_packet(uart.SOF_READ, PERIPHERAL_ID, TEST_BYTES)

    if result["status"] != "ok":
        return {
            "status": result["status"],
            "echo": [],
            "match": False,
            "tx": result["tx"],
            "rx": result["rx"],
        }

    rx = result["rx"]
    # Expected: 5A 11 22 33 44  (5 bytes total)
    echo_bytes = rx[1:] if len(rx) > 1 else b""
    match = (echo_bytes == TEST_BYTES)

    return {
        "status": "ok" if match else "mismatch",
        "echo": list(echo_bytes),
        "match": match,
        "tx": result["tx"],
        "rx": rx,
    }
