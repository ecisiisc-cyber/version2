# gui/tabs/signal/clock_ber_tab.py
# Clock Generator + BER tab with:
#   - Set clock frequency
#   - Read BER
#   - BER frequency sweep with embedded matplotlib plot

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import pyqtSignal, Qt, QThread, pyqtSlot
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox,
    QProgressBar, QSplitter, QSizePolicy, QScrollArea,
)

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from gui.scale import sc
from peripherals.clock_ber   import (
    BER_MARGIN_S,
    ber_wait_time_s,
    clock_set_frequency,
    clock_set_frequency_and_read_ber,
)
from workers.qthread_worker  import run_in_thread
from gui.widgets             import ResultBox, ValueDisplay, StatusIndicator
from style.theme             import get_matplotlib_style
from utils.session_logger    import log_transaction

CLK_FREQ = 100_000_000


# ── Sweep worker ──────────────────────────────────────────────────────────────
class BERSweepWorker(QThread):
    point_ready = pyqtSignal(float, object)   # freq_hz, ber_raw (int or None)
    finished    = pyqtSignal()
    progress    = pyqtSignal(int)

    def __init__(self, freq_list, margin_s):
        super().__init__()
        self._freq_list = freq_list
        self._margin_s  = margin_s
        self._stop      = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self._freq_list)
        for i, freq in enumerate(self._freq_list):
            if self._stop:
                break
            result = clock_set_frequency_and_read_ber(
                freq, self._margin_s, stop_check=lambda: self._stop)
            if result.get("status") == "stopped":
                break
            ber_raw = result.get("ber_raw")
            self.point_ready.emit(freq, ber_raw)
            self.progress.emit(int((i + 1) / total * 100))
        self.finished.emit()


class ClockBERTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread        = None
        self._sweep_worker  = None
        self._sweep_freqs   = []
        self._sweep_bers    = []
        self._current_theme = "light"

        # ── Single scroll area holds everything: controls + sweep + plot ──
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

        top = _inner   # alias so existing code below still works
        top_lay = root  # alias

        # Clock control
        clk_grp = QGroupBox("Clock Control  (ID 0x80)")
        clk_lay = QVBoxLayout(clk_grp)

        info = QLabel(
            "Formula:  f_out = 100 MHz / (2 × divisor)\n"
            "divisor=1 → 50 MHz    divisor=2 → 25 MHz"
        )
        info.setStyleSheet("color: #8B949E; font-size: 11px;")
        clk_lay.addWidget(info)

        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("Output Frequency (Hz):"))
        self.freq_spin = QDoubleSpinBox()
        self.freq_spin.setRange(1.0, 50_000_000.0)
        self.freq_spin.setValue(25_000_000.0)
        self.freq_spin.setDecimals(0)
        self.freq_spin.setSingleStep(1_000_000)
        self.freq_spin.setToolTip(
            "Desired clock output frequency in Hz.\n"
            "Range: 1 Hz – 50 MHz\n\n"
            "Formula: f_out = 100 MHz / (2 × divisor)\n"
            "  → divisor = round(100 MHz / (2 × f_out))\n\n"
            "TX: AA 80 05 AA [div31:24][div23:16][div15:8][div7:0]\n"
            "RX: 5A 5A  (cmd valid + write done)"
        )
        self.freq_spin.valueChanged.connect(self._update_divisor_label)
        freq_row.addWidget(self.freq_spin)
        clk_lay.addLayout(freq_row)

        self.divisor_lbl  = ValueDisplay("Divisor",       "",    width=100)
        self.actual_f_lbl = ValueDisplay("Actual freq",   "MHz", width=100)
        clk_lay.addWidget(self.divisor_lbl)
        clk_lay.addWidget(self.actual_f_lbl)
        self._update_divisor_label()

        self.set_clk_btn = QPushButton("▶  Set Clock")
        self.set_clk_btn.setObjectName("btn_primary")
        self.set_clk_btn.setToolTip(
            "Send clock divisor to FPGA.\n\n"
            "TX: AA 80 05 AA [div31:24][div23:16][div15:8][div7:0]\n"
            "RX: 5A 5A"
        )
        self.set_clk_btn.clicked.connect(self._set_clock)
        clk_lay.addWidget(self.set_clk_btn)
        top_lay.addWidget(clk_grp)

        # BER read
        ber_grp = QGroupBox("Bit Error Rate")
        ber_lay = QVBoxLayout(ber_grp)

        self.read_ber_btn = QPushButton("📖  Read BER")
        self.read_ber_btn.setToolTip(
            "Set the selected clock, wait for 100000 bits plus margin, then read BER.\n\n"
            "Wait = 100000 / actual_clock_frequency + margin\n\n"
            "Set TX: AA 80 05 AA [div bytes]\n"
            "TX: 55 80 05 55 [div bytes — same as last set clock]\n"
            "RX: 5A [BER_B3][BER_B2][BER_B1][BER_B0]  (4-byte BER value)\n\n"
            "Returns raw 32-bit BER count."
        )
        self.read_ber_btn.clicked.connect(self._read_ber)
        ber_lay.addWidget(self.read_ber_btn)

        margin_row = QHBoxLayout()
        margin_row.addWidget(QLabel("Margin (s):"))
        self.ber_margin_spin = QDoubleSpinBox()
        self.ber_margin_spin.setRange(0.0, 3600.0)
        self.ber_margin_spin.setValue(BER_MARGIN_S)
        self.ber_margin_spin.setDecimals(3)
        self.ber_margin_spin.setSingleStep(0.010)
        self.ber_margin_spin.setToolTip(
            "Extra wait time added after the 100000-bit BER run."
        )
        self.ber_margin_spin.valueChanged.connect(self._update_timing_label)
        margin_row.addWidget(self.ber_margin_spin)
        margin_row.addStretch()
        ber_lay.addLayout(margin_row)

        self.ber_raw_disp = ValueDisplay("BER raw (dec)", "",    width=130)
        self.ber_hex_disp = ValueDisplay("BER raw (hex)", "",    width=130)
        self.ber_wait_disp = ValueDisplay("Estimated wait", "s", width=130)
        self.ber_wait_warn = QLabel("")
        self.ber_wait_warn.setObjectName("label_warn")
        self.ber_status   = StatusIndicator("idle")
        ber_lay.addWidget(self.ber_raw_disp)
        ber_lay.addWidget(self.ber_hex_disp)
        ber_lay.addWidget(self.ber_wait_disp)
        ber_lay.addWidget(self.ber_wait_warn)
        ber_lay.addWidget(self.ber_status)
        top_lay.addWidget(ber_grp)
        self._update_timing_label()

        self.result_box = ResultBox()
        top_lay.addWidget(self.result_box)
        # ── BER sweep + plot (continues in same scroll) ─────────────────
        bot_lay = root  # same layout

        sweep_grp = QGroupBox("BER vs Frequency Sweep")
        sw_lay = QVBoxLayout(sweep_grp)

        params_row = QHBoxLayout()
        params_row.addWidget(QLabel("Start (Hz):"))
        self.sw_start = QDoubleSpinBox()
        self.sw_start.setRange(1, 50e6)
        self.sw_start.setValue(1_000_000)
        self.sw_start.setDecimals(0)
        self.sw_start.setToolTip("Sweep start frequency in Hz (1 Hz – 50 MHz)")
        params_row.addWidget(self.sw_start)

        params_row.addWidget(QLabel("Stop (Hz):"))
        self.sw_stop = QDoubleSpinBox()
        self.sw_stop.setRange(1, 50e6)
        self.sw_stop.setValue(25_000_000)
        self.sw_stop.setDecimals(0)
        self.sw_stop.setToolTip("Sweep stop frequency in Hz (1 Hz – 50 MHz)")
        params_row.addWidget(self.sw_stop)

        params_row.addWidget(QLabel("Steps:"))
        self.sw_steps = QSpinBox()
        self.sw_steps.setRange(2, 100)
        self.sw_steps.setValue(10)
        self.sw_steps.setToolTip(
            "Number of evenly-spaced frequency points.\n"
            "Range: 2–100\n"
            "Points are log-spaced for better coverage of the frequency range."
        )
        params_row.addWidget(self.sw_steps)
        sw_lay.addLayout(params_row)

        sweep_btn_row = QHBoxLayout()
        self.run_sweep_btn = QPushButton("▶  Run BER Sweep")
        self.run_sweep_btn.setObjectName("btn_success")
        self.run_sweep_btn.setToolTip(
            "Sweep clock frequency from Start to Stop.\n"
            "At each point: set clock → wait 100000/frequency + margin → read BER.\n"
            "Points are logarithmically spaced.\n"
            "Results plot live as each point completes."
        )
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
        bot_lay.addWidget(sweep_grp)

        # Embedded matplotlib plot
        self._fig    = Figure(figsize=(8, 3.5), tight_layout=True)
        self._ax     = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._canvas.setMinimumHeight(sc(380))
        self._canvas.setMaximumHeight(sc(500))
        self._init_plot()
        bot_lay.addWidget(self._canvas)
        root.addStretch()

    # ── Clock control ──────────────────────────────────────────────────────
    def _update_divisor_label(self):
        freq = self.freq_spin.value()
        div  = max(1, round(CLK_FREQ / (2 * freq)))
        actual = CLK_FREQ / (2 * div)
        self.divisor_lbl.set_value(div, "{:.0f}")
        self.actual_f_lbl.set_value(actual / 1e6, "{:.4f}")
        if hasattr(self, "ber_wait_disp"):
            self._update_timing_label()

    def _update_timing_label(self):
        freq = self.freq_spin.value()
        div  = max(1, round(CLK_FREQ / (2 * freq)))
        actual = CLK_FREQ / (2 * div)
        wait_s = ber_wait_time_s(actual, self.ber_margin_spin.value())
        self.ber_wait_disp.set_value(wait_s, "{:.3f}")

        if wait_s and wait_s > 30.0:
            self.ber_wait_warn.setText(
                f"Long BER wait: this point will take about {wait_s:.1f} s")
        else:
            self.ber_wait_warn.setText("")

    def _set_clock(self):
        freq = self.freq_spin.value()
        self.set_clk_btn.setEnabled(False)
        self.result_box.set_busy()
        self._thread, _ = run_in_thread(
            clock_set_frequency, freq,
            on_result=self._on_clock_set,
            on_error=self._on_error,
            parent=self,
        )

    def _on_clock_set(self, result):
        self.set_clk_btn.setEnabled(True)
        self.result_box.update(result)
        actual = result.get("actual_freq_hz", 0)
        div    = result.get("divisor", 0)
        parsed = f"freq={actual/1e6:.4f}MHz div={div}"
        log_transaction("TX", "ClockBER", result.get("tx", b""),
                        parsed, result.get("status", ""))
        self.log_signal.emit("TX", "ClockBER", result.get("tx", b""),
                             parsed, result.get("status", ""))

    # ── BER read ───────────────────────────────────────────────────────────
    def _read_ber(self):
        freq = self.freq_spin.value()
        margin_s = self.ber_margin_spin.value()
        self.read_ber_btn.setEnabled(False)
        self.set_clk_btn.setEnabled(False)
        self.ber_status.set_state("busy", "Waiting for BER run")
        self.result_box.set_busy()
        self._thread, _ = run_in_thread(
            clock_set_frequency_and_read_ber, freq, margin_s,
            on_result=self._on_ber_read,
            on_error=self._on_error,
            parent=self,
        )

    def _on_ber_read(self, result):
        self.read_ber_btn.setEnabled(True)
        self.set_clk_btn.setEnabled(True)
        ber_result = result.get("ber_result")
        clk_result = result.get("clock_result", {})
        display_result = ber_result or clk_result or result
        self.result_box.update(display_result)
        raw = result.get("ber_raw")
        if raw is not None:
            self.ber_raw_disp.set_value(raw, "{:.0f}")
            self.ber_hex_disp._val.setText(f"0x{raw:08X}")
            self.ber_status.set_state("ok", f"BER = {raw}")
        else:
            self.ber_status.set_state("error", "No data")

        wait_s = result.get("wait_s")
        parsed = f"BER={raw} wait={wait_s:.3f}s" if wait_s is not None else f"BER={raw}"
        if clk_result:
            actual = clk_result.get("actual_freq_hz", 0)
            div = clk_result.get("divisor", 0)
            clk_parsed = f"freq={actual/1e6:.4f}MHz div={div}"
            log_transaction("TX", "ClockBER", clk_result.get("tx", b""),
                            clk_parsed, clk_result.get("status", ""))
            self.log_signal.emit("TX", "ClockBER", clk_result.get("tx", b""),
                                 clk_parsed, clk_result.get("status", ""))
        if ber_result:
            log_transaction("RX", "ClockBER", ber_result.get("rx", b""),
                            parsed, ber_result.get("status", ""))
            self.log_signal.emit("RX", "ClockBER", ber_result.get("rx", b""),
                                 parsed, ber_result.get("status", ""))

    # ── BER sweep ──────────────────────────────────────────────────────────
    def _run_sweep(self):
        import numpy as np
        self._sweep_freqs.clear()
        self._sweep_bers.clear()
        self.sweep_progress.setValue(0)
        self._init_plot()

        start = self.sw_start.value()
        stop  = self.sw_stop.value()
        n     = self.sw_steps.value()
        # Log-spaced for better frequency coverage
        freq_list = list(np.logspace(
            np.log10(max(1, start)),
            np.log10(max(start + 1, stop)),
            n,
        ))

        self.run_sweep_btn.setEnabled(False)
        self.stop_sweep_btn.setEnabled(True)

        self._sweep_worker = BERSweepWorker(freq_list, self.ber_margin_spin.value())
        self._sweep_worker.point_ready.connect(self._on_sweep_point)
        self._sweep_worker.progress.connect(self.sweep_progress.setValue)
        self._sweep_worker.finished.connect(self._on_sweep_done)
        self._sweep_worker.start()

    @pyqtSlot(float, object)
    def _on_sweep_point(self, freq_hz, ber_raw):
        self._sweep_freqs.append(freq_hz)
        self._sweep_bers.append(ber_raw if ber_raw is not None else 0)
        self._update_plot()

    def _on_sweep_done(self):
        self.run_sweep_btn.setEnabled(True)
        self.stop_sweep_btn.setEnabled(False)
        self._update_plot(final=True)

    def _stop_sweep(self):
        if self._sweep_worker:
            self._sweep_worker.stop()
        self.stop_sweep_btn.setEnabled(False)

    # ── Plot ───────────────────────────────────────────────────────────────
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
        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("BER (raw count)")
        self._ax.set_title("BER vs Clock Frequency")
        self._ax.grid(True, which="both", alpha=0.3,
                      color=get_matplotlib_style(self._current_theme)["grid.color"])
        self._canvas.draw_idle()

    def _update_plot(self, final=False):
        self._ax.clear()
        self._apply_theme()
        rc = get_matplotlib_style(self._current_theme)

        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("BER (raw count)")
        self._ax.set_title("BER vs Clock Frequency")

        if self._sweep_freqs:
            freqs_mhz = [f / 1e6 for f in self._sweep_freqs]
            color = "#00D4FF" if self._current_theme == "dark" else "#0078D4"
            self._ax.plot(
                freqs_mhz, self._sweep_bers,
                "o-", color=color,
                linewidth=2, markersize=5,
                markerfacecolor=color,
                label="BER",
            )
            # Annotate last point
            if final and len(freqs_mhz) > 0:
                self._ax.annotate(
                    f"{self._sweep_bers[-1]}",
                    (freqs_mhz[-1], self._sweep_bers[-1]),
                    textcoords="offset points",
                    xytext=(6, 4),
                    fontsize=8,
                    color=rc["text.color"],
                )

        self._ax.grid(True, which="both", alpha=0.3,
                      color=rc["grid.color"])
        self._ax.legend(loc="upper right", fontsize=9,
                        facecolor=rc["axes.facecolor"],
                        labelcolor=rc["text.color"])
        self._canvas.draw_idle()

    def _on_error(self, tb):
        self.set_clk_btn.setEnabled(True)
        self.read_ber_btn.setEnabled(True)
        self.result_box.status.set_custom("#F85149", tb.splitlines()[-1])

    def set_theme(self, theme_name):
        self._current_theme = theme_name
        self._update_plot()
