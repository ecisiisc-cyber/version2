# gui/tabs/power/smu_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QButtonGroup, QRadioButton,
    QScrollArea,)

import instruments.smu_2602b as smu
from gui.widgets             import ValueDisplay, StatusIndicator
from workers.qthread_worker  import run_in_thread


class SMUTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._measuring = False
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_measurement)

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

        # ── Output control ────────────────────────────────────────────────
        out_grp = QGroupBox("Output Control  (Keithley 2602B — TSP)")
        out_lay = QVBoxLayout(out_grp)

        ch_row = QHBoxLayout()
        ch_row.addWidget(QLabel("Channel:"))
        self._ch_group = QButtonGroup(self)
        self._ch_a = QRadioButton("Channel A")
        self._ch_b = QRadioButton("Channel B")
        self._ch_a.setChecked(True)
        self._ch_group.addButton(self._ch_a, 0)
        self._ch_group.addButton(self._ch_b, 1)
        for rb in [self._ch_a, self._ch_b]:
            rb.setToolTip(
                "Select SMU output channel.\n"
                "2602B has two independent SMU channels (A and B).\n"
                "Each can source voltage and measure current independently."
            )
            ch_row.addWidget(rb)
        ch_row.addStretch()
        out_lay.addLayout(ch_row)

        volt_row = QHBoxLayout()
        volt_row.addWidget(QLabel("Voltage (V):"))
        self.volt_spin = QDoubleSpinBox()
        self.volt_spin.setRange(-200.0, 200.0)
        self.volt_spin.setDecimals(4)
        self.volt_spin.setValue(1.0)
        self.volt_spin.setSingleStep(0.1)
        self.volt_spin.setToolTip(
            "Output voltage in Volts.\n"
            "Range: -200 V to +200 V\n"
            "Current limit: 3 A (hardcoded)\n"
            "Sent via TSP: smua.source.levelv = <value>"
        )
        volt_row.addWidget(self.volt_spin)
        out_lay.addLayout(volt_row)

        self.set_volt_btn = QPushButton("⚡  Set Voltage")
        self.set_volt_btn.setObjectName("btn_primary")
        self.set_volt_btn.setToolTip(
            "Configure SMU as voltage source and enable output.\n\n"
            "TSP commands sent:\n"
            "  smua.reset()\n"
            "  smua.source.func = smua.OUTPUT_DCVOLTS\n"
            "  smua.source.levelv = <voltage>\n"
            "  smua.source.limiti = 3.0\n"
            "  smua.source.output = smua.OUTPUT_ON"
        )
        self.set_volt_btn.clicked.connect(self._set_voltage)
        out_lay.addWidget(self.set_volt_btn)
        root.addWidget(out_grp)

        # ── Measurement ───────────────────────────────────────────────────
        meas_grp = QGroupBox("Power Measurement")
        meas_lay = QVBoxLayout(meas_grp)

        self.meas_btn = QPushButton("▶  Start Measuring")
        self.meas_btn.setObjectName("btn_success")
        self.meas_btn.setToolTip(
            "Start background power measurement.\n"
            "Polls V and I every 500 ms via TSP.\n"
            "Accumulates energy (J) = ∫P dt over the measurement period.\n\n"
            "Click again to stop."
        )
        self.meas_btn.clicked.connect(self._toggle_measure)
        meas_lay.addWidget(self.meas_btn)

        self.meas_status = StatusIndicator("idle")
        meas_lay.addWidget(self.meas_status)

        self.volt_disp    = ValueDisplay("Voltage",  "V",   width=100)
        self.curr_disp    = ValueDisplay("Current",  "mA",  width=100)
        self.power_disp   = ValueDisplay("Power",    "mW",  width=100)
        self.energy_disp  = ValueDisplay("Energy",   "mJ",  width=100)
        self.elapsed_disp = ValueDisplay("Elapsed",  "s",   width=100)
        for w in [self.volt_disp, self.curr_disp, self.power_disp,
                  self.energy_disp, self.elapsed_disp]:
            meas_lay.addWidget(w)
        root.addWidget(meas_grp)
        root.addStretch()

    def _selected_channel(self):
        return "a" if self._ch_a.isChecked() else "b"

    def _set_voltage(self):
        if not smu.is_connected():
            return
        self.set_volt_btn.setEnabled(False)
        ch = self._selected_channel()
        v  = self.volt_spin.value()
        self._thread, _ = run_in_thread(
            smu.SMU_vset, ch, v,
            on_result=lambda r: self.set_volt_btn.setEnabled(True),
            on_error=lambda _: self.set_volt_btn.setEnabled(True),
            parent=self,
        )

    def _toggle_measure(self):
        if not self._measuring:
            ch = self._selected_channel()
            smu.SMU_measure_start(ch)
            self._measuring = True
            self._poll_timer.start(500)
            self.meas_btn.setText("■  Stop Measuring")
            self.meas_btn.setObjectName("btn_danger")
            self.meas_status.set_state("busy", "Measuring…")
        else:
            smu.SMU_measure_stop()
            self._measuring = False
            self._poll_timer.stop()
            self.meas_btn.setText("▶  Start Measuring")
            self.meas_btn.setObjectName("btn_success")
            self.meas_status.set_state("idle", "Stopped")

    def _poll_measurement(self):
        m = smu.get_measurement()
        self.volt_disp.set_value(m.get("voltage_v"), "{:.4f}")
        self.curr_disp.set_value(
            (m.get("current_a") or 0) * 1000, "{:.3f}")
        self.power_disp.set_value(
            (m.get("power_w") or 0) * 1000, "{:.3f}")
        self.energy_disp.set_value(
            (m.get("energy_j") or 0) * 1000, "{:.4f}")
        self.elapsed_disp.set_value(m.get("elapsed_s"), "{:.1f}")
