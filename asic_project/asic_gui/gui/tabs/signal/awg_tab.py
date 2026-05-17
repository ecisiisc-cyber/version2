# gui/tabs/signal/awg_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox, QCheckBox,
    QScrollArea,)

from peripherals.awg         import awg, awg_set_frequency
from workers.qthread_worker  import run_in_thread
from gui.widgets             import ResultBox, ValueDisplay
from utils.session_logger    import log_transaction

CLK_FREQ = 100_000_000


class AWGTab(QWidget):
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

        grp = QGroupBox("DDS Waveform Generator  (ID 0x40)")
        lay = QVBoxLayout(grp)
        lay.setSpacing(10)

        # Desired Fout
        fout_row = QHBoxLayout()
        fout_row.addWidget(QLabel("Output Frequency (Hz):"))
        self.fout_spin = QDoubleSpinBox()
        self.fout_spin.setRange(1.0, 50_000_000.0)
        self.fout_spin.setValue(1_000_000.0)
        self.fout_spin.setDecimals(0)
        self.fout_spin.setSingleStep(500_000)
        self.fout_spin.setToolTip(
            "Desired AWG output frequency in Hz.\n"
            "Range: 1 Hz – 50 MHz  (Nyquist limit with divisor=1)\n\n"
            "Formula:\n"
            "  Fs   = 100 MHz / clock_divisor\n"
            "  inc  = round(Fout × 65536 / Fs)\n"
            "  Fout_actual = Fs × inc / 65536\n\n"
            "TX: AA 40 04 [div_H][div_L][inc_H][inc_L]\n"
            "RX: 5A (success) or A5 (error)"
        )
        self.fout_spin.valueChanged.connect(self._update_computed)
        fout_row.addWidget(self.fout_spin)
        lay.addLayout(fout_row)

        # Manual divisor override
        div_row = QHBoxLayout()
        self.override_chk = QCheckBox("Manual clock divisor override")
        self.override_chk.setToolTip(
            "When unchecked: divisor=1 (Fs=100 MHz)\n"
            "When checked: set divisor manually to control Fs independently.\n"
            "Valid range: 1–65535"
        )
        self.override_chk.toggled.connect(self._on_override)
        self.div_spin = QSpinBox()
        self.div_spin.setRange(1, 65535)
        self.div_spin.setValue(1)
        self.div_spin.setEnabled(False)
        self.div_spin.setToolTip(
            "Clock divisor for the DDS sampling clock.\n"
            "Fs = 100 MHz / divisor\n"
            "divisor=1 → Fs=100 MHz (max)\n"
            "divisor=2 → Fs=50 MHz\n"
            "Only active when 'Manual override' is checked."
        )
        self.div_spin.valueChanged.connect(self._update_computed)
        div_row.addWidget(self.override_chk)
        div_row.addWidget(self.div_spin)
        div_row.addStretch()
        lay.addLayout(div_row)

        # Computed values
        self.fs_lbl      = ValueDisplay("Sampling Freq", "MHz", width=120)
        self.actual_lbl  = ValueDisplay("Actual Fout",   "Hz",  width=120)
        self.inc_lbl     = ValueDisplay("DDS Increment", "",    width=120)
        self.nyq_lbl = QLabel("")
        self.nyq_lbl.setObjectName("label_warn")
        lay.addWidget(self.fs_lbl)
        lay.addWidget(self.actual_lbl)
        lay.addWidget(self.inc_lbl)
        lay.addWidget(self.nyq_lbl)

        self.send_btn = QPushButton("▶  Send AWG Command")
        self.send_btn.setObjectName("btn_primary")
        self.send_btn.setToolTip(
            "Send the computed AWG configuration to the FPGA.\n"
            "TX: AA 40 04 [clk_div_H][clk_div_L][inc_H][inc_L]\n"
            "RX: 5A (success)"
        )
        self.send_btn.clicked.connect(self._send)
        lay.addWidget(self.send_btn)
        root.addWidget(grp)

        self.result_box = ResultBox()
        root.addWidget(self.result_box)
        root.addStretch()

        self._update_computed()

    def _on_override(self, checked):
        self.div_spin.setEnabled(checked)
        self._update_computed()

    def _update_computed(self):
        fout = self.fout_spin.value()
        div  = self.div_spin.value() if self.override_chk.isChecked() else 1
        fs   = CLK_FREQ / div
        inc  = round(fout * 65536 / fs)
        inc  = max(0, min(inc, 65535))
        actual = fs * inc / 65536

        self.fs_lbl.set_value(fs / 1e6, "{:.3f}")
        self.actual_lbl.set_value(actual, "{:.2f}")
        self.inc_lbl.set_value(inc, "{:.0f}")

        if inc > 32767:
            self.nyq_lbl.setText(
                "⚠  Nyquist warning: Fout > Fs/2, aliasing will occur")
        else:
            self.nyq_lbl.setText("")

    def _send(self):
        fout = self.fout_spin.value()
        div  = self.div_spin.value() if self.override_chk.isChecked() else 1
        self.send_btn.setEnabled(False)
        self.result_box.set_busy()
        self._thread, _ = run_in_thread(
            awg_set_frequency, fout, div,
            on_result=self._on_result,
            on_error=self._on_error,
            parent=self,
        )

    def _on_result(self, result):
        self.send_btn.setEnabled(True)
        self.result_box.update(result)
        parsed = (f"Fout={result.get('actual_fout_hz',0)/1e6:.3f}MHz "
                  f"div={result.get('clock_divisor')} "
                  f"inc={result.get('inc')}")
        log_transaction("TX", "AWG", result.get("tx", b""), parsed,
                        result.get("status", ""))
        self.log_signal.emit("TX", "AWG", result.get("tx", b""),
                             parsed, result.get("status", ""))

    def _on_error(self, tb):
        self.send_btn.setEnabled(True)
        self.result_box.status.set_custom("#F85149", tb.splitlines()[-1])
