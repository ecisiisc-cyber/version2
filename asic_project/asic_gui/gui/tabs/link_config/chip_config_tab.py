# gui/tabs/link_config/chip_config_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QPushButton, QLabel,
    QScrollArea,)

from peripherals.chip_config import chip_config
from workers.qthread_worker  import run_in_thread
from gui.widgets             import ResultBox, StatusIndicator
from utils.session_logger    import log_transaction


class ChipConfigTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
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

        grp = QGroupBox("DUT Configuration")
        lay = QVBoxLayout(grp)
        lay.setSpacing(10)

        info = QLabel(
            "Triggers the DUT chip configuration sequence.\n"
            "Returns 0x11 (success) or 0x22 (failed)."
        )
        info.setStyleSheet("color: #8B949E; font-size: 11px;")
        lay.addWidget(info)

        protocol = QLabel(
            "TX:  55  08  01  55\n"
            "RX:  5A  [status]   (0x11=OK  0x22=FAIL)"
        )
        protocol.setStyleSheet(
            "font-family: monospace; color: #00D4FF; font-size: 11px;")
        lay.addWidget(protocol)

        self.cfg_btn = QPushButton("⚙  Configure Chip")
        self.cfg_btn.setObjectName("btn_primary")
        self.cfg_btn.setToolTip(
            "Send chip configuration command.\n\n"
            "TX:  55 08 01 55\n"
            "  SOF 0x55 = Read/trigger\n"
            "  ID  0x08 = Chip Config peripheral\n"
            "  LEN 0x01 = 1 data byte\n"
            "  DATA 0x55 = dummy trigger byte\n\n"
            "RX:  5A [status]\n"
            "  0x11 = Config success\n"
            "  0x22 = Config failed"
        )
        self.cfg_btn.clicked.connect(self._configure)
        lay.addWidget(self.cfg_btn)
        root.addWidget(grp)

        # ── Status indicator with 4 states ────────────────────────────────
        status_grp = QGroupBox("Status")
        status_lay = QVBoxLayout(status_grp)
        self.config_status = StatusIndicator("unconfigured")
        self.raw_lbl = QLabel("Raw status byte: —")
        self.raw_lbl.setStyleSheet("color: #8B949E; font-size: 11px;")
        status_lay.addWidget(self.config_status)
        status_lay.addWidget(self.raw_lbl)
        root.addWidget(status_grp)

        self.result_box = ResultBox()
        root.addWidget(self.result_box)
        root.addStretch()

    def _configure(self):
        self.cfg_btn.setEnabled(False)
        self.config_status.set_state("configuring")
        self.result_box.set_busy()
        self._thread, _ = run_in_thread(
            chip_config,
            on_result=self._on_result,
            on_error=self._on_error,
            parent=self,
        )

    def _on_result(self, result):
        self.cfg_btn.setEnabled(True)
        self.result_box.update(result)

        cfg = result.get("config_status", "unknown")
        raw = result.get("raw_status")
        self.raw_lbl.setText(
            f"Raw status byte: 0x{raw:02X}" if raw is not None else
            "Raw status byte: —"
        )

        state_map = {
            "success": "success",
            "failed":  "failed",
            "unknown": "warning",
        }
        self.config_status.set_state(
            state_map.get(cfg, "idle"),
            custom_label={
                "success": "Config Success  (0x11) ✓",
                "failed":  "Config Failed   (0x22) ✗",
            }.get(cfg, f"Unknown (0x{raw:02X})" if raw else "Unknown")
        )

        log_transaction("TX", "ChipConfig", result.get("tx", b""),
                        "chip_config()", result.get("status", ""))
        log_transaction("RX", "ChipConfig", result.get("rx", b""),
                        cfg, result.get("status", ""))
        self.log_signal.emit("TX", "ChipConfig", result.get("tx", b""),
                             "chip_config()", result.get("status", ""))
        self.log_signal.emit("RX", "ChipConfig", result.get("rx", b""),
                             cfg, result.get("status", ""))

    def _on_error(self, tb):
        self.cfg_btn.setEnabled(True)
        self.config_status.set_state("failed", "Exception")
        self.result_box.status.set_custom("#F85149", tb.splitlines()[-1])
