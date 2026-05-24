# gui/tabs/power/psu_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QButtonGroup, QRadioButton,
    QScrollArea, QSpinBox,)

import instruments.psu_2230g as psu
from gui.widgets             import ValueDisplay, StatusIndicator
from workers.qthread_worker  import run_in_thread


class PSUTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._measuring  = False
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

        out_grp = QGroupBox("Output Control  (Keithley 2230G — SCPI)")
        out_lay = QVBoxLayout(out_grp)

        ch_row = QHBoxLayout()
        ch_row.addWidget(QLabel("Channel:"))
        self._ch_group = QButtonGroup(self)
        self._ch_btns  = {}
        for i in [1, 2, 3]:
            rb = QRadioButton(f"CH{i}")
            rb.setToolTip(
                f"Select PSU output channel {i}.\n"
                "2230G has 3 independent channels.\n"
                "CH1, CH2: 0–30 V / 1.5 A each\n"
                "CH3: 0–6 V / 5 A"
            )
            if i == 1:
                rb.setChecked(True)
            self._ch_group.addButton(rb, i)
            self._ch_btns[i] = rb
            ch_row.addWidget(rb)
        ch_row.addStretch()
        out_lay.addLayout(ch_row)

        volt_row = QHBoxLayout()
        volt_row.addWidget(QLabel("Voltage (V):"))
        self.volt_spin = QDoubleSpinBox()
        self.volt_spin.setRange(0.0, 30.0)
        self.volt_spin.setDecimals(3)
        self.volt_spin.setValue(1.0)
        self.volt_spin.setSingleStep(0.1)
        self.volt_spin.setToolTip(
            "Output voltage in Volts.\n"
            "CH1/CH2 range: 0–30 V\n"
            "CH3 range:     0–6 V\n\n"
            "SCPI commands sent:\n"
            "  INST CH<n>\n"
            "  VOLT <value>\n"
            "  OUTP ON"
        )
        volt_row.addWidget(self.volt_spin)
        out_lay.addLayout(volt_row)

        self.set_volt_btn = QPushButton("⚡  Set Voltage")
        self.set_volt_btn.setObjectName("btn_primary")
        self.set_volt_btn.setToolTip(
            "Set selected channel voltage and enable output.\n"
            "Sends SCPI: INST CH<n> → VOLT <v> → OUTP ON"
        )
        self.set_volt_btn.clicked.connect(self._set_voltage)
        out_lay.addWidget(self.set_volt_btn)
        root.addWidget(out_grp)

        meas_grp = QGroupBox("Power Measurement")
        meas_lay = QVBoxLayout(meas_grp)

        self.meas_btn = QPushButton("▶  Start Measuring")
        self.meas_btn.setObjectName("btn_success")
        self.meas_btn.setToolTip(
            "Start background power measurement on selected channel.\n"
            "Polls MEAS:VOLT? and MEAS:CURR? at the selected interval via SCPI.\n"
            "Accumulates energy (J) = ∫P dt.\n"
            "Click again to stop."
        )
        self.meas_btn.clicked.connect(self._toggle_measure)
        meas_lay.addWidget(self.meas_btn)

        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("Sample interval (ms):"))
        self.sample_interval_spin = QSpinBox()
        self.sample_interval_spin.setRange(50, 10000)
        self.sample_interval_spin.setSingleStep(50)
        self.sample_interval_spin.setValue(psu.get_measurement_interval_ms())
        self.sample_interval_spin.setToolTip(
            "PSU measurement polling interval.\n"
            "Default: 500 ms. Lower values may be limited by PSU/SCPI speed."
        )
        self.sample_interval_spin.valueChanged.connect(
            self._on_sample_interval_changed)
        rate_row.addWidget(self.sample_interval_spin)
        rate_row.addStretch()
        meas_lay.addLayout(rate_row)

        self.meas_status = StatusIndicator("idle")
        meas_lay.addWidget(self.meas_status)

        self.volt_disp    = ValueDisplay("Voltage",  "V",  width=100)
        self.curr_disp    = ValueDisplay("Current",  "mA", width=100)
        self.power_disp   = ValueDisplay("Power",    "mW", width=100)
        self.energy_disp  = ValueDisplay("Energy",   "mJ", width=100)
        self.elapsed_disp = ValueDisplay("Elapsed",  "s",  width=100)
        for w in [self.volt_disp, self.curr_disp, self.power_disp,
                  self.energy_disp, self.elapsed_disp]:
            meas_lay.addWidget(w)
        root.addWidget(meas_grp)
        root.addStretch()

    def _selected_channel(self):
        return self._ch_group.checkedId()

    def _set_voltage(self):
        if not psu.is_connected():
            return
        self.set_volt_btn.setEnabled(False)
        ch = self._selected_channel()
        v  = self.volt_spin.value()
        self._thread, _ = run_in_thread(
            psu.PSU_vset, ch, v,
            on_result=lambda r: self.set_volt_btn.setEnabled(True),
            on_error=lambda _: self.set_volt_btn.setEnabled(True),
            parent=self,
        )

    def _toggle_measure(self):
        if not self._measuring:
            ch = self._selected_channel()
            interval_ms = self.sample_interval_spin.value()
            psu.set_measurement_interval_ms(interval_ms)
            psu.PSU_measure_start(ch)
            self._measuring = True
            self._poll_timer.start(interval_ms)
            self.meas_btn.setText("■  Stop Measuring")
            self.meas_btn.setObjectName("btn_danger")
            self.meas_status.set_state("busy", "Measuring…")
        else:
            psu.PSU_measure_stop()
            self._measuring = False
            self._poll_timer.stop()
            self.meas_btn.setText("▶  Start Measuring")
            self.meas_btn.setObjectName("btn_success")
            self.meas_status.set_state("idle", "Stopped")

    def _on_sample_interval_changed(self, interval_ms):
        psu.set_measurement_interval_ms(interval_ms)
        if self._measuring:
            self._poll_timer.start(interval_ms)

    def _poll_measurement(self):
        m = psu.get_measurement()
        self.volt_disp.set_value(m.get("voltage_v"), "{:.4f}")
        self.curr_disp.set_value(
            (m.get("current_a") or 0) * 1000, "{:.3f}")
        self.power_disp.set_value(
            (m.get("power_w") or 0) * 1000, "{:.3f}")
        self.energy_disp.set_value(
            (m.get("energy_j") or 0) * 1000, "{:.4f}")
        self.elapsed_disp.set_value(m.get("elapsed_s"), "{:.1f}")
