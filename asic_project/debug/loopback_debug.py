import os
import sys
import argparse

# Allow importing the peripherals package from the asic_auto folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'asic_auto'))

from peripherals import uart_handler as uart
from peripherals import loopback


def format_bytes(data: bytes) -> str:
    return ' '.join(f'{b:02X}' for b in data)


def run_loopback(port: str = 'COM9', baud: int = 115200, timeout: float = 2.0):
    print(f'Connecting UART on {port} @ {baud} baud with RTS/CTS enabled...')
    ok = uart.connect(port, baud=baud, timeout=timeout)
    if not ok:
        print('ERROR: Failed to open UART port.')
        return 1

    try:
        result = loopback.loop_back()
        print('\nLoopback test result:')
        print(f'  status : {result.get("status")}')
        print(f'  match  : {result.get("match")}')
        print(f'  tx     : {format_bytes(result.get("tx", b""))}')
        print(f'  rx     : {format_bytes(result.get("rx", b""))}')
        echo = result.get('echo', [])
        echo_hex = ' '.join(f'{b:02X}' for b in echo)
        print(f'  echo   : {echo_hex or "<none>"}  ({echo})')

        if result.get('status') == 'ok':
            print('\nSUCCESS: Loopback matched expected hex payload.')
            return 0
        elif result.get('status') == 'mismatch':
            print('\nFAIL: Received reply but payload did not match expected bytes.')
            return 2
        else:
            print('\nFAIL: Loopback did not complete successfully.')
            return 3

    finally:
        uart.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Debug loopback using COM9 RTS/CTS.')
    parser.add_argument('--port', default='COM9', help='COM port to use (default: COM9)')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate (default: 115200)')
    parser.add_argument('--timeout', type=float, default=2.0, help='Serial timeout in seconds')
    args = parser.parse_args()
    sys.exit(run_loopback(args.port, args.baud, args.timeout))
