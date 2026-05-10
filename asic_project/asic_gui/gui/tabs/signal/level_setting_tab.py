# gui/tabs/signal/level_setting_tab.py
# LTC2656 DAC tab with:
#   - Channel select (A–H), analog mV or digital 16-bit input
#   - Send DAC command
#   - DAC linearity sweep: sweep mV range, send each value, read back via ADC,
#     plot expected vs actual inline using matplotlib embedded in PyQt5.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

import time
import numpy as np

from PyQt5.QtCore    import pyqtSignal, Qt, QThread, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox,
    QButtonGroup, QRadioButton, QComboBox, QProgressBar,
    QSplitter, QSizePolicy, QScrollArea,
)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from peripherals.level_setting import (
    level_set_dac_analog, level_set_dac_digital, level_set,
    CMD_WRITE_UPDATE, CMD_POWER_DOWN, CMD_WRITE_UPDATE_ALL,
    CHANNEL_NAMES,
)
from peripherals.adc           import adc_read_channel
from workers.qthread_worker    import run_in_thread
from gui.widgets               import ResultBox
from gui.scale import sc
from style.theme               import get_matplotlib_style
from utils.session_logger      import log_transaction

VREF_MV  = 2500.0
DAC_MAX  = 65535
ADC_VREF = 2500.0


# ── Sweep worker ──────────────────────────────────────────────────────────────
class SweepWorker(QThread):
    """Runs the DAC linearity sweep in a thread, emitting one point at a time."""
    point_ready = pyqtSignal(float, float, float)  # expected_mv, dac_mv, adc_mv
    finished    = pyqtSignal()
    progress    = pyqtSignal(int)

    def __init__(self, channel, adc_ch, start_mv, stop_mv, step_mv):
        super().__init__()
        self.channel  = channel
        self.adc_ch   = adc_ch
        self.start_mv = start_mv
        self.stop_mv  = stop_mv
        self.step_mv  = step_mv
        self._stop    = False

    def stop(self):
        self._stop = True

    def run(self):
        steps = []
        v = self.start_mv
        while v <= self.stop_mv + 1e-6:
            steps.append(v)
            v += self.step_mv

        for i, target_mv in enumerate(steps):
            if self._stop:
                break
            # Send DAC value
            r = level_set_dac_analog(self.channel, target_mv, CMD_WRITE_UPDATE)
            dac_actual_mv = (round(target_mv / VREF_MV * DAC_MAX) / DAC_MAX) * VREF_MV
            # Read back via ADC
            time.sleep(0.01)
            adc_r = adc_read_channel(self.adc_ch)
            adc_mv = adc_r.get("voltage_mv") or 0.0

            self.point_ready.emit(target_mv, dac_actual_mv, adc_mv)
            self.progress.emit(int((i + 1) / len(steps) * 100))

        self.finished.emit()


class LevelSettingTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._sweep_worker = None
        self._sweep_expected = []
        self._sweep_dac      = []
        self._sweep_adc      = []
        self._current_theme  = "dark"

        # ── Single scroll area for everything: controls + sweep + plot ──
        _outer = QVBoxLayout(self)
        _outer.setContentsMargins(0, 0, 0, 0)
        _outer.setSpacing(0)

        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        _scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        _scroll.setFrameShape(QScrollArea.NoFrame)
        _outer.addWidget(_scroll)

        _inner = QWidget()
        root = QVBoxLayout(_inner)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        _scroll.setWidget(_inner)

        top    = _inner   # alias
        top_lay = root    # alias

        # Channel select
        ch_grp = QGroupBox("DAC Channel  (LTC2656 — 8 channels, 2.5 V ref)")
        ch_lay = QHBoxLayout(ch_grp)
        self._ch_group = QButtonGroup(self)
        for i, name in CHANNEL_NAMES.items():
            rb = QRadioButton(f"DAC {name}")
            rb.setToolTip(
                f"Select DAC channel {name} (index {i}).\n"
                "LTC2656 has 8 independent 16-bit rail-to-rail DAC outputs.\n"
                "Reference: internal 2.5 V\n"
                "Full scale: 65535 counts = 2500 mV"
            )
            if i == 0:
                rb.setChecked(True)
            self._ch_group.addButton(rb, i)
            ch_lay.addWidget(rb)
        top_lay.addWidget(ch_grp)

        # Value input
        val_grp = QGroupBox("Value Input")
        val_lay = QVBoxLayout(val_grp)

        mode_row = QHBoxLayout()
        self._mode_grp = QButtonGroup(self)
        self._analog_rb  = QRadioButton("Analog (mV)")
        self._digital_rb = QRadioButton("Digital (16-bit)")
        self._analog_rb.setChecked(True)
        self._mode_grp.addButton(self._analog_rb,  0)
        self._mode_grp.addButton(self._digital_rb, 1)
        self._analog_rb.toggled.connect(self._on_mode)
        mode_row.addWidget(self._analog_rb)
        mode_row.addWidget(self._digital_rb)
        mode_row.addStretch()
        val_lay.addLayout(mode_row)

        self.analog_spin = QDoubleSpinBox()
        self.analog_spin.setRange(0.0, 2500.0)
        self.analog_spin.setDecimals(2)
        self.analog_spin.setSingleStep(10.0)
        self.analog_spin.setValue(1250.0)
        self.analog_spin.setSuffix("  mV")
        self.analog_spin.setToolTip(
            "Target voltage in millivolts.\n"
            "Range: 0.00 – 2500.00 mV (0 – 2.5 V)\n"
            "Converted to 16-bit count: round(mV / 2500 × 65535)\n"
            "Sent as: D1=count[15:8], D2=count[7:0]"
        )
        val_lay.addWidget(self.analog_spin)

        self.digital_spin = QSpinBox()
        self.digital_spin.setRange(0, 65535)
        self.digital_spin.setValue(32767)
        self.digital_spin.setToolTip(
            "Raw 16-bit DAC code.\n"
            "Range: 0 – 65535\n"
            "0 = 0 V,  32767 ≈ 1.25 V,  65535 = 2.5 V\n"
            "Sent as: D1=value[15:8], D2=value[7:0]"
        )
        self.digital_spin.setVisible(False)
        val_lay.addWidget(self.digital_spin)

        cmd_row = QHBoxLayout()
        cmd_row.addWidget(QLabel("Command:"))
        self.cmd_combo = QComboBox()
        self.cmd_combo.addItems([
            "Write & Update (0x3)",
            "Power Down     (0x4)",
            "Write & Update All (0xF)",
        ])
        self.cmd_combo.setToolTip(
            "DAC command nibble (upper nibble of D0 byte):\n"
            "  0x3 = Write and Update — load output immediately (default)\n"
            "  0x4 = Power Down — disable DAC output\n"
            "  0xF = Write and Update All — update all 8 channels at once\n\n"
            "D0 = (cmd_nibble << 4) | channel_index"
        )
        cmd_row.addWidget(self.cmd_combo)
        cmd_row.addStretch()
        val_lay.addLayout(cmd_row)

        self.send_btn = QPushButton("▶  Send DAC Command")
        self.send_btn.setObjectName("btn_primary")
        self.send_btn.setToolTip(
            "Send DAC command.\n\n"
            "TX: AA 02 03 [D0][D1][D2]\n"
            "  SOF 0xAA = Write\n"
            "  ID  0x02 = Level Setting\n"
            "  LEN 0x03 = 3 data bytes\n"
            "  D0  = (cmd<<4) | channel\n"
            "  D1  = value[15:8]\n"
            "  D2  = value[7:0]\n\n"
            "RX: 5A 5A  (two ACKs: cmd valid + write done)"
        )
        self.send_btn.clicked.connect(self._send)
        val_lay.addWidget(self.send_btn)
        top_lay.addWidget(val_grp)

        self.result_box = ResultBox()
        top_lay.addWidget(self.result_box)
        # ── Linearity sweep + plot (same scroll, continues below) ──────

        sweep_grp = QGroupBox("DAC Linearity Sweep  (S9)")
        sw_lay = QVBoxLayout(sweep_grp)

        params_row = QHBoxLayout()
        params_row.addWidget(QLabel("Start (mV):"))
        self.sw_start = QDoubleSpinBox()
        self.sw_start.setRange(0, 2500); self.sw_start.setValue(0)
        self.sw_start.setToolTip("Sweep start voltage in mV (0–2500)")
        params_row.addWidget(self.sw_start)

        params_row.addWidget(QLabel("Stop (mV):"))
        self.sw_stop = QDoubleSpinBox()
        self.sw_stop.setRange(0, 2500); self.sw_stop.setValue(2500)
        self.sw_stop.setToolTip("Sweep stop voltage in mV (0–2500)")
        params_row.addWidget(self.sw_stop)

        params_row.addWidget(QLabel("Step (mV):"))
        self.sw_step = QDoubleSpinBox()
        self.sw_step.setRange(1, 500); self.sw_step.setValue(100)
        self.sw_step.setToolTip("Voltage step size in mV (1–500)")
        params_row.addWidget(self.sw_step)

        params_row.addWidget(QLabel("ADC CH:"))
        self.sw_adc_ch = QSpinBox()
        self.sw_adc_ch.setRange(0, 7); self.sw_adc_ch.setValue(0)
        self.sw_adc_ch.setToolTip(
            "ADC channel (0–7) to read back for each DAC code.\n"
            "Wire the DAC output to this ADC input for linearity check.")
        params_row.addWidget(self.sw_adc_ch)
        sw_lay.addLayout(params_row)

        sweep_btn_row = QHBoxLayout()
        self.run_sweep_btn = QPushButton("▶  Run Linearity Sweep")
        self.run_sweep_btn.setObjectName("btn_success")
        self.run_sweep_btn.setToolTip(
            "Sweep DAC output from Start to Stop in Step increments.\n"
            "At each point: set DAC → wait 10 ms → read ADC.\n"
            "Plots expected mV vs DAC quantised mV vs ADC measured mV.\n"
            "ADC channel must be wired to DAC output.")
        self.run_sweep_btn.clicked.connect(self._run_sweep)

        self.stop_sweep_btn = QPushButton("■  Stop")
        self.stop_sweep_btn.setObjectName("btn_danger")
        self.stop_sweep_btn.setEnabled(False)
        self.stop_sweep_btn.clicked.connect(self._stop_sweep)

        sweep_btn_row.addWidget(self.run_sweep_btn)
        sweep_btn_row.addWidget(self.stop_sweep_btn)
        sweep_btn_row.addStretch()
        sw_lay.addLayout(sweep_btn_row)

        self.sweep_progress = QProgressBar()
        self.sweep_progress.setValue(0)
        sw_lay.addWidget(self.sweep_progress)
        root.addWidget(sweep_grp)

        # Embedded matplotlib plot
        self._fig = Figure(figsize=(8, 3.5), tight_layout=True)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.setMinimumHeight(sc(380))
        self._canvas.setMaximumHeight(sc(500))
        self._init_plot()
        root.addWidget(self._canvas)
        root.addStretch()

    # ── Mode toggle ───────────────────────────────────────────────────────
    def _on_mode(self, analog):
        self.analog_spin.setVisible(analog)
        self.digital_spin.setVisible(not analog)

    def _cmd_nibble(self):
        return [0x3, 0x4, 0xF][self.cmd_combo.currentIndex()]

    # ── Send ──────────────────────────────────────────────────────────────
    def _send(self):
        ch  = self._ch_group.checkedId()
        cmd = self._cmd_nibble()
        self.send_btn.setEnabled(False)
        self.result_box.set_busy()

        if self._analog_rb.isChecked():
            mv = self.analog_spin.value()
            self._thread, _ = run_in_thread(
                level_set_dac_analog, ch, mv, cmd,
                on_result=self._on_result,
                on_error=self._on_error,
                parent=self,
            )
        else:
            dv = self.digital_spin.value()
            self._thread, _ = run_in_thread(
                level_set_dac_digital, ch, dv, cmd,
                on_result=self._on_result,
                on_error=self._on_error,
                parent=self,
            )

    def _on_result(self, result):
        self.send_btn.setEnabled(True)
        self.result_box.update(result)
        ch   = result.get("channel_name", "?")
        mv   = result.get("value_mv", 0)
        cnt  = result.get("counts") or result.get("digital_value", 0)
        parsed = f"DAC{ch} {mv:.2f}mV count={cnt}"
        log_transaction("TX", "LevelSet", result.get("tx", b""),
                        parsed, result.get("status", ""))
        self.log_signal.emit("TX", "LevelSet", result.get("tx", b""),
                             parsed, result.get("status", ""))

    def _on_error(self, tb):
        self.send_btn.setEnabled(True)
        self.result_box.status.set_custom("#F85149", tb.splitlines()[-1])

    # ── Linearity sweep ───────────────────────────────────────────────────
    def _run_sweep(self):
        self._sweep_expected.clear()
        self._sweep_dac.clear()
        self._sweep_adc.clear()
        self.sweep_progress.setValue(0)
        self._init_plot()

        ch     = self._ch_group.checkedId()
        adc_ch = self.sw_adc_ch.value()
        start  = self.sw_start.value()
        stop   = self.sw_stop.value()
        step   = self.sw_step.value()

        self.run_sweep_btn.setEnabled(False)
        self.stop_sweep_btn.setEnabled(True)

        self._sweep_worker = SweepWorker(ch, adc_ch, start, stop, step)
        self._sweep_worker.point_ready.connect(self._on_sweep_point)
        self._sweep_worker.progress.connect(self.sweep_progress.setValue)
        self._sweep_worker.finished.connect(self._on_sweep_done)
        self._sweep_worker.start()

    @pyqtSlot(float, float, float)
    def _on_sweep_point(self, expected, dac_mv, adc_mv):
        self._sweep_expected.append(expected)
        self._sweep_dac.append(dac_mv)
        self._sweep_adc.append(adc_mv)
        self._update_plot()

    def _on_sweep_done(self):
        self.run_sweep_btn.setEnabled(True)
        self.stop_sweep_btn.setEnabled(False)
        self._update_plot(final=True)

    def _stop_sweep(self):
        if self._sweep_worker:
            self._sweep_worker.stop()
        self.stop_sweep_btn.setEnabled(False)

    # ── Plot ──────────────────────────────────────────────────────────────
    def _apply_theme(self):
        rc = get_matplotlib_style(self._current_theme)
        self._fig.set_facecolor(rc["figure.facecolor"])
        self._ax.set_facecolor(rc["axes.facecolor"])
        for spine in self._ax.spines.values():
            spine.set_edgecolor(rc["axes.edgecolor"])
        self._ax.xaxis.label.set_color(rc["axes.labelcolor"])
        self._ax.yaxis.label.set_color(rc["axes.labelcolor"])
        self._ax.title.set_color(rc["axes.titlecolor"])
        self._ax.tick_params(colors=rc["xtick.color"])
        self._ax.grid(color=rc["grid.color"], linestyle="--",
                      linewidth=0.5, alpha=0.6)

    def _init_plot(self):
        self._ax.clear()
        self._apply_theme()
        self._ax.set_xlabel("Expected Voltage (mV)")
        self._ax.set_ylabel("Voltage (mV)")
        self._ax.set_title("DAC Linearity Check — Expected vs Actual")
        self._ax.set_xlim(0, 2500)
        self._ax.set_ylim(0, 2700)
        # Ideal line
        self._ax.plot([0, 2500], [0, 2500], "--",
                      color="#8B949E", linewidth=1, label="Ideal")
        self._canvas.draw_idle()

    def _update_plot(self, final=False):
        self._ax.clear()
        self._apply_theme()
        self._ax.set_xlabel("Expected Voltage (mV)")
        self._ax.set_ylabel("Voltage (mV)")
        self._ax.set_title("DAC Linearity Check — Expected vs Actual")

        x = self._sweep_expected
        self._ax.plot([0, 2500], [0, 2500], "--",
                      color="#8B949E", linewidth=1, label="Ideal")
        if x:
            self._ax.plot(x, self._sweep_dac, "o-",
                          color="#00D4FF", linewidth=1.5,
                          markersize=4, label="DAC Quantised")
            self._ax.plot(x, self._sweep_adc, "s-",
                          color="#3FB950", linewidth=1.5,
                          markersize=4, label="ADC Measured")

        self._ax.legend(loc="upper left", fontsize=9,
                        facecolor="#161B22", labelcolor="#E6EDF3")
        self._ax.grid(True, alpha=0.3)
        self._canvas.draw_idle()

    def set_theme(self, theme_name):
        self._current_theme = theme_name
        self._update_plot()
