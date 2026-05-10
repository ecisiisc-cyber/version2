# gui/tabs/link_config/loopback_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QSizePolicy,
    QScrollArea,)

from peripherals import uart_handler as uart
from peripherals.loopback          import loop_back
from workers.qthread_worker      import run_in_thread
from gui.widgets                 import ResultBox, StatusIndicator
from utils.session_logger        import log_transaction


class LoopbackTab(QWidget):
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

        # ── Info card ─────────────────────────────────────────────────────
        grp = QGroupBox("Loopback Test")
        grp_lay = QVBoxLayout(grp)
        grp_lay.setSpacing(10)

        info = QLabel(
            "Sends 4 test bytes (11 22 33 44) to the FPGA and verifies\n"
            "they are echoed back unchanged.  Use this first after connecting\n"
            "to confirm the UART link is healthy."
        )
        info.setStyleSheet("color: #8B949E; font-size: 11px;")
        grp_lay.addWidget(info)

        protocol = QLabel(
            "TX:  55  00  04  11  22  33  44\n"
            "RX:  5A  11  22  33  44"
        )
        protocol.setStyleSheet(
            "font-family: monospace; color: #00D4FF; font-size: 11px;")
        grp_lay.addWidget(protocol)

        self.run_btn = QPushButton("▶  Run Loopback")
        self.run_btn.setObjectName("btn_primary")
        self.run_btn.setToolTip(
            "Send loopback packet and check echo.\n\n"
            "TX:  55 00 04 11 22 33 44\n"
            "RX expected:  5A 11 22 33 44\n\n"
            "SOF 0x55 = Read/Loopback\n"
            "ID  0x00 = Loopback peripheral\n"
            "LEN 0x04 = 4 data bytes\n"
            "RX  5A   = Valid ACK from FPGA\n"
            "Returns: MATCH (green) or MISMATCH (red)"
        )
        self.run_btn.clicked.connect(self._run)
        grp_lay.addWidget(self.run_btn)
        root.addWidget(grp)

        # ── Echo display ──────────────────────────────────────────────────
        echo_grp = QGroupBox("Echo Result")
        echo_lay = QVBoxLayout(echo_grp)

        self.echo_lbl = QLabel("—")
        self.echo_lbl.setObjectName("label_value")
        self.echo_lbl.setStyleSheet(
            "font-size: 18px; font-family: monospace; letter-spacing: 4px;")
        echo_lay.addWidget(self.echo_lbl)

        self.match_status = StatusIndicator("idle")
        echo_lay.addWidget(self.match_status)
        root.addWidget(echo_grp)

        # ── Results ───────────────────────────────────────────────────────
        self.result_box = ResultBox()
        root.addWidget(self.result_box)
        root.addStretch()

    def _run(self):
        if not uart.is_connected():
            self.run_btn.setEnabled(True)
            self.result_box.status.set_custom("#F85149", "UART disconnected")
            self.match_status.set_state("error", "NO UART")
            self.echo_lbl.setText("—")
            return

        self.run_btn.setEnabled(False)
        self.result_box.set_busy()
        self._thread, self._worker = run_in_thread(
            loop_back,
            on_result=self._on_result,
            on_error=self._on_error,
            parent=self,
        )

    def _on_result(self, result):
        self.run_btn.setEnabled(True)
        self.result_box.update(result)

        echo = result.get("echo", [])
        hex_echo = " ".join(f"{b:02X}" for b in echo)
        self.echo_lbl.setText(hex_echo or "—")

        if result.get("match"):
            self.match_status.set_state("ok", "MATCH ✓")
        elif result.get("status") == "mismatch":
            self.match_status.set_state("error", "MISMATCH ✗")
        else:
            self.match_status.set_state("error",
                                        result.get("status", "error").upper())

        log_transaction("TX", "Loopback", result.get("tx", b""),
                        "loop_back()", result.get("status", ""))
        log_transaction("RX", "Loopback", result.get("rx", b""),
                        f"echo={hex_echo}", result.get("status", ""))
        self.log_signal.emit("TX", "Loopback", result.get("tx", b""),
                             "loop_back()", result.get("status", ""))
        self.log_signal.emit("RX", "Loopback", result.get("rx", b""),
                             f"echo={hex_echo}", result.get("status", ""))

    def _on_error(self, tb):
        self.run_btn.setEnabled(True)
        self.match_status.set_state("error", "Exception")
        self.result_box.status.set_custom("#F85149", tb.splitlines()[-1])
