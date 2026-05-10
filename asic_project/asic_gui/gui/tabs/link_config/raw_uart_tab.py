# gui/tabs/link_config/raw_uart_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QSpinBox, QTextEdit,
    QScrollArea,)

from peripherals.raw_uart    import uart_tx_packet, uart_rx_packet
from peripherals import uart_handler as uart
from workers.qthread_worker  import run_in_thread
from gui.widgets             import ResultBox
from utils.session_logger    import log_transaction
from gui.scale               import sc


class RawUartTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        _scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        _scroll.setFrameShape(QScrollArea.NoFrame)
        _inner = QWidget()
        root = QVBoxLayout(_inner)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        _scroll.setWidget(_inner)
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)
        _outer.addWidget(_scroll)

        # ── TX ────────────────────────────────────────────────────────────
        tx_grp = QGroupBox("Transmit")
        tx_lay = QVBoxLayout(tx_grp)

        self.tx_edit = QLineEdit()
        self.tx_edit.setPlaceholderText("e.g.  AA 02 03 78 9A BC")
        self.tx_edit.setToolTip(
            "Enter raw bytes to send as space-separated hex values.\n"
            "Format: AA 02 03 78 9A BC\n"
            "No packet wrapping is applied — bytes are sent exactly as entered.\n"
            "SOF, ID, LEN, DATA must all be specified manually."
        )
        tx_lay.addWidget(QLabel("Bytes (hex, space-separated):"))
        tx_lay.addWidget(self.tx_edit)

        self.send_btn = QPushButton("↑  Send")
        self.send_btn.setObjectName("btn_primary")
        self.send_btn.setToolTip(
            "Send the hex bytes directly to the serial port.\n"
            "No ACK is read automatically — use the Receive section below.")
        self.send_btn.clicked.connect(self._send)
        tx_lay.addWidget(self.send_btn)
        root.addWidget(tx_grp)

        # ── RX ────────────────────────────────────────────────────────────
        rx_grp = QGroupBox("Receive")
        rx_lay = QVBoxLayout(rx_grp)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Bytes to read:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 255)
        self.size_spin.setValue(5)
        self.size_spin.setToolTip(
            "Number of bytes to read from the RX buffer.\n"
            "Range: 1–255\n"
            "Waits up to 5 seconds for the requested number of bytes."
        )
        size_row.addWidget(self.size_spin)
        size_row.addStretch()

        self.read_btn = QPushButton("↓  Read")
        self.read_btn.setToolTip(
            "Read the specified number of bytes from the UART RX buffer.\n"
            "Timeout: 5 seconds."
        )
        self.read_btn.clicked.connect(self._read)
        size_row.addWidget(self.read_btn)
        rx_lay.addLayout(size_row)

        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFixedHeight(sc(100))
        self.rx_display.setPlaceholderText("Received bytes appear here…")
        rx_lay.addWidget(self.rx_display)
        root.addWidget(rx_grp)

        self.result_box = ResultBox()
        root.addWidget(self.result_box)
        root.addStretch()

    def _send(self):
        if not uart.is_connected():
            self.result_box.update({"status": "not_connected",
                                    "tx": b"", "rx": b""})
            return
        hex_str = self.tx_edit.text().strip()
        if not hex_str:
            return
        self.send_btn.setEnabled(False)
        self._thread, self._worker = run_in_thread(
            uart_tx_packet, hex_str,
            on_result=self._on_send,
            on_error=lambda tb: self.send_btn.setEnabled(True),
            parent=self,
        )

    def _on_send(self, result):
        self.send_btn.setEnabled(True)
        self.result_box.update(result)
        log_transaction("TX", "RawUART", result.get("tx", b""),
                        f"{result.get('bytes_sent',0)} bytes",
                        result.get("status", ""))
        self.log_signal.emit("TX", "RawUART", result.get("tx", b""),
                             f"{result.get('bytes_sent',0)} bytes",
                             result.get("status", ""))

    def _read(self):
        if not uart.is_connected():
            self.result_box.update({"status": "not_connected",
                                    "tx": b"", "rx": b""})
            return
        size = self.size_spin.value()
        self.read_btn.setEnabled(False)
        self._thread, self._worker = run_in_thread(
            uart_rx_packet, size,
            on_result=self._on_read,
            on_error=lambda tb: self.read_btn.setEnabled(True),
            parent=self,
        )

    def _on_read(self, result):
        self.read_btn.setEnabled(True)
        hex_str = result.get("hex", "")
        self.rx_display.append(hex_str)
        self.result_box.update(result)
        log_transaction("RX", "RawUART", result.get("data", b""),
                        f"{result.get('bytes_received',0)} bytes",
                        result.get("status", ""))
        self.log_signal.emit("RX", "RawUART", result.get("data", b""),
                             f"{result.get('bytes_received',0)} bytes",
                             result.get("status", ""))
