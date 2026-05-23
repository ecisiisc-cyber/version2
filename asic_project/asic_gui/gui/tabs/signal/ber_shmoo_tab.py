# gui/tabs/signal/ber_shmoo_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox, QComboBox,
    QProgressBar, QSizePolicy, QScrollArea,
)

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from gui.scale import sc
from gui.widgets import ResultBox, StatusIndicator
from peripherals.clock_ber import (
    BER_MARGIN_S,
    ber_wait_time_s,
    clock_set_frequency,
    read_ber,
)
from peripherals.pmic import (
    configure_buck_voltage_and_enable,
    configure_ldo_voltage_and_enable,
)
from style.theme import get_matplotlib_style
from utils.session_logger import log_transaction

BER_BITS = 100_000
BER_YELLOW_LIMIT = int(BER_BITS * 0.001)  # 0.1% of 100000 = 100


def _inclusive_range(start, stop, step):
    start = float(start)
    stop = float(stop)
    step = abs(float(step))
    if step <= 0:
        step = 1.0
    if stop < start:
        start, stop = stop, start

    values = []
    v = start
    while v <= stop + (step * 1e-9):
        values.append(round(v, 6))
        v += step
    if values and values[-1] < stop:
        values.append(round(stop, 6))
    return values


def _ber_color_code(ber_raw):
    if ber_raw == 0:
        return 0
    if ber_raw is not None and ber_raw <= BER_YELLOW_LIMIT:
        return 1
    return 2


class BERShmooWorker(QThread):
    point_ready = pyqtSignal(dict)
    status_ready = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, is_ldo, rail_num, voltages_mv, freqs_hz,
                 margin_s, voltage_settle_s, freq_settle_s):
        super().__init__()
        self._is_ldo = is_ldo
        self._rail_num = rail_num
        self._voltages_mv = voltages_mv
        self._freqs_hz = freqs_hz
        self._margin_s = margin_s
        self._voltage_settle_s = voltage_settle_s
        self._freq_settle_s = freq_settle_s
        self._stop = False

    def stop(self):
        self._stop = True

    def _wait_s(self, seconds):
        deadline_ms = int(max(0.0, seconds) * 1000)
        elapsed = 0
        while elapsed < deadline_ms:
            if self._stop:
                return False
            step = min(100, deadline_ms - elapsed)
            self.msleep(step)
            elapsed += step
        return not self._stop

    def run(self):
        set_voltage = (
            configure_ldo_voltage_and_enable if self._is_ldo
            else configure_buck_voltage_and_enable
        )
        total = max(1, len(self._voltages_mv) * len(self._freqs_hz))
        done = 0
        rail_type = "ldo" if self._is_ldo else "buck"

        for v_idx, voltage_mv in enumerate(self._voltages_mv):
            if self._stop:
                break

            self.status_ready.emit(
                f"Setting {rail_type} {self._rail_num} to {voltage_mv:.1f} mV")
            pmic_result = set_voltage(self._rail_num, voltage_mv)
            if pmic_result.get("status") != "ok":
                for f_idx, freq_hz in enumerate(self._freqs_hz):
                    done += 1
                    self.point_ready.emit({
                        "v_idx": v_idx,
                        "f_idx": f_idx,
                        "voltage_mv": voltage_mv,
                        "freq_hz": freq_hz,
                        "ber_raw": None,
                        "pmic_result": pmic_result,
                        "status": "error",
                        "error": pmic_result.get("error", "PMIC voltage set failed"),
                    })
                    self.progress.emit(int(done / total * 100))
                continue

            if not self._wait_s(self._voltage_settle_s):
                break

            for f_idx, freq_hz in enumerate(self._freqs_hz):
                if self._stop:
                    break

                self.status_ready.emit(
                    f"BER at {voltage_mv:.1f} mV, {freq_hz/1e6:.4f} MHz")
                clk_result = clock_set_frequency(freq_hz)
                actual_freq = clk_result.get("actual_freq_hz")
                wait_s = ber_wait_time_s(actual_freq, self._margin_s) if actual_freq else None
                ber_result = None
                ber_raw = None
                status = clk_result.get("status", "error")

                if status == "ok" and wait_s is not None:
                    if self._wait_s(self._freq_settle_s) and self._wait_s(wait_s):
                        ber_result = read_ber()
                        status = ber_result.get("status", "error")
                        ber_raw = ber_result.get("ber_raw")
                    else:
                        status = "stopped"

                done += 1
                self.point_ready.emit({
                    "v_idx": v_idx,
                    "f_idx": f_idx,
                    "voltage_mv": voltage_mv,
                    "freq_hz": freq_hz,
                    "actual_freq_hz": actual_freq,
                    "ber_raw": ber_raw,
                    "pmic_result": pmic_result,
                    "clock_result": clk_result,
                    "ber_result": ber_result,
                    "wait_s": wait_s,
                    "status": status,
                })
                self.progress.emit(int(done / total * 100))


class BERShmooTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._current_theme = "dark"
        self._voltages_mv = []
        self._freqs_hz = []
        self._ber_grid = None
        self._color_grid = None
        self._stop_requested = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        scroll.setWidget(inner)

        root.addWidget(self._build_controls())

        self.result_box = ResultBox()
        root.addWidget(self.result_box)

        self._fig = Figure(figsize=(8, 4.2), tight_layout=True)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.setMinimumHeight(sc(420))
        self._canvas.setMaximumHeight(sc(560))
        self._init_plot()
        root.addWidget(self._canvas)
        root.addStretch()

    def _build_controls(self):
        grp = QGroupBox("BER Shmoo")
        lay = QVBoxLayout(grp)

        rail_row = QHBoxLayout()
        rail_row.addWidget(QLabel("PMIC converter:"))
        self.rail_type_combo = QComboBox()
        self.rail_type_combo.addItems(["Buck", "LDO"])
        self.rail_type_combo.currentIndexChanged.connect(self._on_rail_type)
        rail_row.addWidget(self.rail_type_combo)

        rail_row.addWidget(QLabel("Channel:"))
        self.rail_num_spin = QSpinBox()
        self.rail_num_spin.setRange(1, 8)
        self.rail_num_spin.setValue(1)
        rail_row.addWidget(self.rail_num_spin)
        rail_row.addStretch()
        lay.addLayout(rail_row)

        v_row = QHBoxLayout()
        v_row.addWidget(QLabel("Voltage start (mV):"))
        self.v_start = QDoubleSpinBox()
        self.v_start.setRange(600.0, 3300.0)
        self.v_start.setValue(800.0)
        self.v_start.setDecimals(1)
        v_row.addWidget(self.v_start)

        v_row.addWidget(QLabel("stop:"))
        self.v_stop = QDoubleSpinBox()
        self.v_stop.setRange(600.0, 3300.0)
        self.v_stop.setValue(1200.0)
        self.v_stop.setDecimals(1)
        v_row.addWidget(self.v_stop)

        v_row.addWidget(QLabel("step:"))
        self.v_step = QDoubleSpinBox()
        self.v_step.setRange(1.0, 1000.0)
        self.v_step.setValue(100.0)
        self.v_step.setDecimals(1)
        v_row.addWidget(self.v_step)
        lay.addLayout(v_row)

        f_row = QHBoxLayout()
        f_row.addWidget(QLabel("Frequency start (Hz):"))
        self.f_start = QDoubleSpinBox()
        self.f_start.setRange(1.0, 50_000_000.0)
        self.f_start.setValue(1_000_000.0)
        self.f_start.setDecimals(0)
        f_row.addWidget(self.f_start)

        f_row.addWidget(QLabel("stop:"))
        self.f_stop = QDoubleSpinBox()
        self.f_stop.setRange(1.0, 50_000_000.0)
        self.f_stop.setValue(25_000_000.0)
        self.f_stop.setDecimals(0)
        f_row.addWidget(self.f_stop)

        f_row.addWidget(QLabel("step:"))
        self.f_step = QDoubleSpinBox()
        self.f_step.setRange(1.0, 50_000_000.0)
        self.f_step.setValue(1_000_000.0)
        self.f_step.setDecimals(0)
        f_row.addWidget(self.f_step)
        lay.addLayout(f_row)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("BER margin (s):"))
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0.0, 3600.0)
        self.margin_spin.setValue(BER_MARGIN_S)
        self.margin_spin.setDecimals(3)
        self.margin_spin.setSingleStep(0.010)
        delay_row.addWidget(self.margin_spin)

        delay_row.addWidget(QLabel("Voltage settle (s):"))
        self.v_settle_spin = QDoubleSpinBox()
        self.v_settle_spin.setRange(0.0, 60.0)
        self.v_settle_spin.setValue(0.200)
        self.v_settle_spin.setDecimals(3)
        self.v_settle_spin.setSingleStep(0.050)
        delay_row.addWidget(self.v_settle_spin)

        delay_row.addWidget(QLabel("Frequency settle (s):"))
        self.f_settle_spin = QDoubleSpinBox()
        self.f_settle_spin.setRange(0.0, 60.0)
        self.f_settle_spin.setValue(0.020)
        self.f_settle_spin.setDecimals(3)
        self.f_settle_spin.setSingleStep(0.010)
        delay_row.addWidget(self.f_settle_spin)
        lay.addLayout(delay_row)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Run BER Shmoo")
        self.run_btn.setObjectName("btn_success")
        self.run_btn.clicked.connect(self._run_shmoo)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("btn_danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_shmoo)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        lay.addWidget(self.progress)

        self.status = StatusIndicator("idle")
        lay.addWidget(self.status)
        return grp

    def _on_rail_type(self):
        if self.rail_type_combo.currentIndex() == 0:
            self.rail_num_spin.setRange(1, 8)
        else:
            self.rail_num_spin.setRange(1, 4)

    def _run_shmoo(self):
        if self._worker and self._worker.isRunning():
            return

        self._voltages_mv = _inclusive_range(
            self.v_start.value(), self.v_stop.value(), self.v_step.value())
        self._freqs_hz = _inclusive_range(
            self.f_start.value(), self.f_stop.value(), self.f_step.value())
        self._ber_grid = np.full((len(self._voltages_mv), len(self._freqs_hz)),
                                 np.nan)
        self._color_grid = np.full((len(self._voltages_mv), len(self._freqs_hz)),
                                   -1)
        self.progress.setValue(0)
        self._update_plot()
        self._stop_requested = False

        is_ldo = self.rail_type_combo.currentIndex() == 1
        rail_num = self.rail_num_spin.value()
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status.set_state("busy", "BER shmoo running")
        self.result_box.set_busy()

        self._worker = BERShmooWorker(
            is_ldo, rail_num, self._voltages_mv, self._freqs_hz,
            self.margin_spin.value(),
            self.v_settle_spin.value(),
            self.f_settle_spin.value(),
        )
        self._worker.point_ready.connect(self._on_point)
        self._worker.status_ready.connect(lambda s: self.status.set_state("busy", s))
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _stop_shmoo(self):
        if self._worker:
            self._stop_requested = True
            self._worker.stop()
        self.stop_btn.setEnabled(False)
        self.status.set_state("busy", "Stopping BER shmoo")

    def _on_point(self, result):
        v_idx = result["v_idx"]
        f_idx = result["f_idx"]
        ber_raw = result.get("ber_raw")
        self._ber_grid[v_idx, f_idx] = np.nan if ber_raw is None else ber_raw
        self._color_grid[v_idx, f_idx] = _ber_color_code(ber_raw)

        display = (
            result.get("ber_result") or result.get("clock_result") or
            result.get("pmic_result") or result
        )
        self.result_box.update(display)
        self._update_plot()

        parsed = (
            f"V={result.get('voltage_mv', 0):.1f}mV "
            f"F={result.get('freq_hz', 0)/1e6:.4f}MHz "
            f"BER={ber_raw}"
        )
        status = result.get("status", "")
        if result.get("clock_result"):
            log_transaction("TX", "BERShmoo",
                            result["clock_result"].get("tx", b""),
                            parsed, result["clock_result"].get("status", ""))
            self.log_signal.emit("TX", "BERShmoo",
                                 result["clock_result"].get("tx", b""),
                                 parsed, result["clock_result"].get("status", ""))
        if result.get("ber_result"):
            log_transaction("RX", "BERShmoo",
                            result["ber_result"].get("rx", b""),
                            parsed, result["ber_result"].get("status", ""))
            self.log_signal.emit("RX", "BERShmoo",
                                 result["ber_result"].get("rx", b""),
                                 parsed, result["ber_result"].get("status", ""))
        if status != "ok":
            self.status.set_state("warning", parsed)

    def _on_done(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        label = "BER shmoo stopped" if self._stop_requested else "BER shmoo complete"
        self.status.set_state("idle", label)
        self._worker = None
        self._update_plot()

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

    def _init_plot(self):
        self._ax.clear()
        self._apply_theme()
        self._ax.set_title("BER Shmoo")
        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("Voltage (mV)")
        self._ax.text(0.5, 0.5, "Run BER shmoo to populate plot",
                      ha="center", va="center", transform=self._ax.transAxes,
                      color=get_matplotlib_style(self._current_theme)["text.color"])
        self._canvas.draw_idle()

    def _update_plot(self):
        if self._color_grid is None:
            self._init_plot()
            return

        self._ax.clear()
        self._apply_theme()
        cmap = mcolors.ListedColormap(["#30363D", "#3FB950", "#D29922", "#F85149"])
        norm = mcolors.BoundaryNorm([-1.5, -0.5, 0.5, 1.5, 2.5], cmap.N)

        self._ax.imshow(self._color_grid, origin="lower", aspect="auto",
                        interpolation="nearest", cmap=cmap, norm=norm)
        self._ax.set_title("BER Shmoo")
        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("Voltage (mV)")

        self._ax.set_xticks(range(len(self._freqs_hz)))
        self._ax.set_xticklabels([f"{f/1e6:.3g}" for f in self._freqs_hz],
                                 rotation=45, ha="right")
        self._ax.set_yticks(range(len(self._voltages_mv)))
        self._ax.set_yticklabels([f"{v:.0f}" for v in self._voltages_mv])

        text_color = get_matplotlib_style(self._current_theme)["text.color"]
        for v_idx in range(len(self._voltages_mv)):
            for f_idx in range(len(self._freqs_hz)):
                ber = self._ber_grid[v_idx, f_idx]
                if not np.isnan(ber):
                    self._ax.text(f_idx, v_idx, f"{int(ber)}",
                                  ha="center", va="center",
                                  fontsize=8, color=text_color)

        handles = [
            mpatches.Patch(color="#3FB950", label="BER = 0"),
            mpatches.Patch(color="#D29922", label="1 <= BER <= 100"),
            mpatches.Patch(color="#F85149", label="BER > 100 / error"),
        ]
        rc = get_matplotlib_style(self._current_theme)
        self._ax.legend(handles=handles, loc="upper right", fontsize=8,
                        facecolor=rc["axes.facecolor"],
                        labelcolor=rc["text.color"])
        self._canvas.draw_idle()

    def set_theme(self, theme_name):
        self._current_theme = theme_name
        self._update_plot()
