# # gui/tabs/signal/dut_shmoo_tab.py

# import sys, os
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

# import time

# import numpy as np
# import matplotlib
# matplotlib.use("Agg")
# import matplotlib.colors as mcolors
# import matplotlib.patches as mpatches
# from matplotlib.figure import Figure
# from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# from PyQt5.QtCore import Qt, QThread, pyqtSignal
# from PyQt5.QtWidgets import (
#     QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
#     QPushButton, QLabel, QDoubleSpinBox, QSpinBox, QComboBox,
#     QProgressBar, QSizePolicy, QScrollArea, QCheckBox,
# )

# import instruments.psu_2230g as psu
# from gui.scale import sc
# from gui.widgets import ResultBox, StatusIndicator
# from peripherals import uart_handler as uart
# from peripherals.chip_config import chip_config
# from style.theme import get_matplotlib_style
# from utils.session_logger import log_transaction


# DUT_PACKET_SOF = 0x55
# DUT_PACKET_ID = 0x10
# DUT_PACKET_LEN = 0x02
# DUT_ACK = 0x5A
# DUT_PASS = 0x11
# DUT_FAIL = 0x22
# DUT_BASE_HZ = 10_000_000.0
# MIN_DIVISOR = 1
# MAX_DIVISOR = 255
# MIN_MULTIPLIER = 2
# MAX_MULTIPLIER = 255
# MAX_SHMOO_POINTS = 250
# UART_POLL_SLICE_S = 0.1
# ACK_GUARD_TIMEOUT_S = 30.0
# RESULT_GUARD_TIMEOUT_S = 300.0
# DEFAULT_VOLTAGE_SETTLE_S = 0.500
# DEFAULT_CONFIG_SETTLE_S = 1.000
# DEFAULT_POINT_DELAY_S = 3.000


# def _inclusive_range(start, stop, step):
#     start = float(start)
#     stop = float(stop)
#     step = abs(float(step))
#     if step <= 0:
#         step = 1.0
#     if stop < start:
#         start, stop = stop, start

#     values = []
#     v = start
#     while v <= stop + (step * 1e-9):
#         values.append(round(v, 9))
#         v += step
#     if values and values[-1] < stop:
#         values.append(round(stop, 9))
#     return values


# def _format_duration(seconds):
#     seconds = max(0.0, float(seconds))
#     if seconds < 60:
#         return f"{seconds:.1f} s"
#     return f"{seconds / 60:.1f} min"


# def _best_clock_params(target_hz):
#     best = None
#     best_err = None
#     target_hz = max(1.0, float(target_hz))
#     for divisor in range(MIN_DIVISOR, MAX_DIVISOR + 1):
#         denom = divisor + 1
#         ideal_multiplier = int(round((target_hz * denom / DUT_BASE_HZ) - 1))
#         for multiplier in (
#             ideal_multiplier - 1,
#             ideal_multiplier,
#             ideal_multiplier + 1,
#         ):
#             if multiplier < MIN_MULTIPLIER or multiplier > MAX_MULTIPLIER:
#                 continue
#             actual_hz = DUT_BASE_HZ * (multiplier + 1) / denom
#             err = abs(actual_hz - target_hz)
#             if best is None or err < best_err:
#                 best = divisor, multiplier, actual_hz
#                 best_err = err
#     if best is None:
#         best = (
#             MAX_DIVISOR,
#             MIN_MULTIPLIER,
#             DUT_BASE_HZ * (MIN_MULTIPLIER + 1) / (MAX_DIVISOR + 1),
#         )
#     return best


# class DUTShmooWorker(QThread):
#     point_ready = pyqtSignal(dict)
#     status_ready = pyqtSignal(str)
#     progress = pyqtSignal(int)

#     def __init__(self, psu_channel, voltages_v, freqs_hz, voltage_settle_s,
#                  config_settle_s, point_delay_s, sample_interval_ms,
#                  turn_off_when_done):
#         super().__init__()
#         self._psu_channel = psu_channel
#         self._voltages_v = voltages_v
#         self._freqs_hz = freqs_hz
#         self._voltage_settle_s = voltage_settle_s
#         self._config_settle_s = config_settle_s
#         self._point_delay_s = point_delay_s
#         self._sample_interval_ms = sample_interval_ms
#         self._turn_off_when_done = turn_off_when_done
#         self._stop = False

#     def stop(self):
#         self._stop = True

#     def _wait_s(self, seconds):
#         deadline_ms = int(max(0.0, seconds) * 1000)
#         elapsed = 0
#         while elapsed < deadline_ms:
#             if self._stop:
#                 return False
#             step = min(100, deadline_ms - elapsed)
#             self.msleep(step)
#             elapsed += step
#         return not self._stop

#     def _read_until_expected(self, expected, guard_timeout_s):
#         expected = tuple(expected)
#         guard_timeout_s = max(UART_POLL_SLICE_S, float(guard_timeout_s))
#         deadline = time.time() + guard_timeout_s
#         rx = b""

#         while not self._stop and time.time() < deadline:
#             remaining = max(0.0, deadline - time.time())
#             chunk = uart.read_raw(
#                 1, timeout_s=min(UART_POLL_SLICE_S, remaining))
#             if not chunk:
#                 continue
#             rx += chunk
#             if chunk[0] in expected:
#                 return chunk[0], rx

#         return None, rx

#     def _run_dut_point(self, voltage_v, freq_hz):
#         divisor, multiplier, actual_hz = _best_clock_params(freq_hz)
#         packet = bytes([
#             DUT_PACKET_SOF,
#             DUT_PACKET_ID,
#             DUT_PACKET_LEN,
#             divisor,
#             multiplier,
#         ])
#         result = {
#             "voltage_v": voltage_v,
#             "target_freq_hz": freq_hz,
#             "actual_freq_hz": actual_hz,
#             "divisor": divisor,
#             "multiplier": multiplier,
#             "tx": packet,
#             "rx": b"",
#             "status": "error",
#             "pass_fail": "unknown",
#         }

#         if not uart.is_connected():
#             result["status"] = "uart_not_connected"
#             return result
#         if not psu.is_connected():
#             result["status"] = "psu_not_connected"
#             return result

#         psu.set_measurement_interval_ms(self._sample_interval_ms)
#         psu.PSU_measure_start(self._psu_channel)
#         t_start = time.time()
#         try:
#             uart.flush_rx()
#             if not uart.send_raw(packet):
#                 result["status"] = "uart_send_error"
#                 return result

#             ack_byte, ack_rx = self._read_until_expected(
#                 [DUT_ACK], ACK_GUARD_TIMEOUT_S)
#             result["rx"] += ack_rx
#             if ack_byte is None:
#                 result["status"] = "ack_timeout"
#                 return result

#             final_byte, final_rx = self._read_until_expected(
#                 [DUT_PASS, DUT_FAIL], RESULT_GUARD_TIMEOUT_S)
#             result["rx"] += final_rx
#             if final_byte is None:
#                 result["status"] = "result_timeout"
#                 return result
#             if final_byte == DUT_PASS:
#                 result["status"] = "ok"
#                 result["pass_fail"] = "pass"
#             elif final_byte == DUT_FAIL:
#                 result["status"] = "ok"
#                 result["pass_fail"] = "fail"
#         finally:
#             measurement = psu.PSU_measure_stop()
#             result.update({
#                 "meas_elapsed_s": time.time() - t_start,
#                 "psu_voltage_v": measurement.get("voltage_v"),
#                 "current_a": measurement.get("current_a"),
#                 "power_w": measurement.get("power_w"),
#                 "energy_j": measurement.get("energy_j"),
#             })
#         return result

#     def run(self):
#         total = max(1, len(self._voltages_v) * len(self._freqs_hz))
#         done = 0

#         for v_idx, voltage_v in enumerate(self._voltages_v):
#             if self._stop:
#                 break

#             self.status_ready.emit(
#                 f"Setting PSU CH{self._psu_channel} to {voltage_v:.3f} V")
#             vset_result = psu.PSU_vset(self._psu_channel, voltage_v)
#             if vset_result.get("status") != "ok":
#                 for f_idx, freq_hz in enumerate(self._freqs_hz):
#                     done += 1
#                     self.point_ready.emit({
#                         "v_idx": v_idx,
#                         "f_idx": f_idx,
#                         "voltage_v": voltage_v,
#                         "target_freq_hz": freq_hz,
#                         "status": vset_result.get("status", "error"),
#                         "pass_fail": "unknown",
#                         "vset_result": vset_result,
#                     })
#                     self.progress.emit(int(done / total * 100))
#                 continue

#             if not self._wait_s(self._voltage_settle_s):
#                 break

#             self.status_ready.emit(f"Configuring chip at {voltage_v:.3f} V")
#             config_result = chip_config()
#             config_ok = (
#                 config_result.get("status") == "ok" and
#                 config_result.get("config_status") == "success"
#             )
#             if not config_ok:
#                 for f_idx, freq_hz in enumerate(self._freqs_hz):
#                     done += 1
#                     self.point_ready.emit({
#                         "v_idx": v_idx,
#                         "f_idx": f_idx,
#                         "voltage_v": voltage_v,
#                         "target_freq_hz": freq_hz,
#                         "status": "chip_config_failed",
#                         "pass_fail": "unknown",
#                         "config_result": config_result,
#                     })
#                     self.progress.emit(int(done / total * 100))
#                 continue

#             if not self._wait_s(self._config_settle_s):
#                 break

#             for f_idx, freq_hz in enumerate(self._freqs_hz):
#                 if self._stop:
#                     break

#                 self.status_ready.emit(
#                     f"DUT shmoo {voltage_v:.3f} V, {freq_hz/1e6:.4f} MHz")
#                 point = self._run_dut_point(voltage_v, freq_hz)
#                 point.update({
#                     "v_idx": v_idx,
#                     "f_idx": f_idx,
#                     "config_result": config_result,
#                     "vset_result": vset_result,
#                 })
#                 done += 1
#                 self.point_ready.emit(point)
#                 self.progress.emit(int(done / total * 100))

#                 if self._stop:
#                     break
#                 if f_idx < len(self._freqs_hz) - 1:
#                     self._wait_s(self._point_delay_s)

#         if self._turn_off_when_done and psu.is_connected():
#             psu.PSU_vset(self._psu_channel, 0.0)


# class DUTShmooTab(QWidget):
#     log_signal = pyqtSignal(str, str, bytes, str, str)

#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self._worker = None
#         self._current_theme = "light"
#         self._voltages_v = []
#         self._freqs_hz = []
#         self._result_grid = None
#         self._color_grid = None
#         self._stop_requested = False
#         self._annot = None
#         self._hover_rect = None
#         self._hover_enabled = False
#         self._hover_axes = []
#         self._plot_mode = "passfail"

#         outer = QVBoxLayout(self)
#         outer.setContentsMargins(0, 0, 0, 0)
#         outer.setSpacing(0)

#         scroll = QScrollArea()
#         scroll.setWidgetResizable(True)
#         scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
#         scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
#         scroll.setFrameShape(QScrollArea.NoFrame)
#         outer.addWidget(scroll)

#         inner = QWidget()
#         root = QVBoxLayout(inner)
#         root.setContentsMargins(12, 12, 12, 12)
#         root.setSpacing(10)
#         scroll.setWidget(inner)

#         root.addWidget(self._build_controls())

#         self.result_box = ResultBox()
#         root.addWidget(self.result_box)

#         self._fig = Figure(figsize=(8, 4.2), tight_layout=True)
#         self._ax = self._fig.add_subplot(111)
#         self._canvas = FigureCanvas(self._fig)
#         self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
#         self._canvas.setMinimumHeight(sc(420))
#         self._canvas.setMaximumHeight(sc(560))
#         self._canvas.mpl_connect("motion_notify_event", self._on_hover)
#         root.addWidget(self._canvas)

#         self._init_plot()
#         root.addStretch()

#     def _build_controls(self):
#         grp = QGroupBox("DUT Shmoo")
#         lay = QVBoxLayout(grp)

#         psu_row = QHBoxLayout()
#         psu_row.addWidget(QLabel("PSU channel:"))
#         self.psu_channel_combo = QComboBox()
#         self.psu_channel_combo.addItems(["CH1", "CH2", "CH3"])
#         self.psu_channel_combo.setCurrentIndex(2)
#         psu_row.addWidget(self.psu_channel_combo)
#         psu_row.addStretch()
#         lay.addLayout(psu_row)

#         v_row = QHBoxLayout()
#         v_row.addWidget(QLabel("Voltage start (V):"))
#         self.v_start = QDoubleSpinBox()
#         self.v_start.setRange(0.0, 30.0)
#         self.v_start.setValue(0.8)
#         self.v_start.setDecimals(3)
#         self.v_start.valueChanged.connect(self._update_estimate)
#         v_row.addWidget(self.v_start)

#         v_row.addWidget(QLabel("stop:"))
#         self.v_stop = QDoubleSpinBox()
#         self.v_stop.setRange(0.0, 30.0)
#         self.v_stop.setValue(1.2)
#         self.v_stop.setDecimals(3)
#         self.v_stop.valueChanged.connect(self._update_estimate)
#         v_row.addWidget(self.v_stop)

#         v_row.addWidget(QLabel("step:"))
#         self.v_step = QDoubleSpinBox()
#         self.v_step.setRange(0.001, 30.0)
#         self.v_step.setValue(0.1)
#         self.v_step.setDecimals(3)
#         self.v_step.valueChanged.connect(self._update_estimate)
#         v_row.addWidget(self.v_step)
#         lay.addLayout(v_row)

#         f_row = QHBoxLayout()
#         f_row.addWidget(QLabel("Frequency start (MHz):"))
#         self.f_start = QDoubleSpinBox()
#         self.f_start.setRange(0.001, 1280.0)
#         self.f_start.setValue(20.0)
#         self.f_start.setDecimals(3)
#         self.f_start.valueChanged.connect(self._update_estimate)
#         f_row.addWidget(self.f_start)

#         f_row.addWidget(QLabel("stop:"))
#         self.f_stop = QDoubleSpinBox()
#         self.f_stop.setRange(0.001, 1280.0)
#         self.f_stop.setValue(100.0)
#         self.f_stop.setDecimals(3)
#         self.f_stop.valueChanged.connect(self._update_estimate)
#         f_row.addWidget(self.f_stop)

#         f_row.addWidget(QLabel("step:"))
#         self.f_step = QDoubleSpinBox()
#         self.f_step.setRange(0.001, 1280.0)
#         self.f_step.setValue(10.0)
#         self.f_step.setDecimals(3)
#         self.f_step.valueChanged.connect(self._update_estimate)
#         f_row.addWidget(self.f_step)
#         lay.addLayout(f_row)

#         timing_row = QHBoxLayout()
#         timing_row.addWidget(QLabel("Voltage settle (s):"))
#         self.v_settle = QDoubleSpinBox()
#         self.v_settle.setRange(0.0, 60.0)
#         self.v_settle.setValue(DEFAULT_VOLTAGE_SETTLE_S)
#         self.v_settle.setDecimals(3)
#         self.v_settle.setSingleStep(0.050)
#         self.v_settle.valueChanged.connect(self._update_estimate)
#         timing_row.addWidget(self.v_settle)

#         timing_row.addWidget(QLabel("Config settle (s):"))
#         self.config_settle = QDoubleSpinBox()
#         self.config_settle.setRange(0.0, 60.0)
#         self.config_settle.setValue(DEFAULT_CONFIG_SETTLE_S)
#         self.config_settle.setDecimals(3)
#         self.config_settle.setSingleStep(0.050)
#         self.config_settle.valueChanged.connect(self._update_estimate)
#         timing_row.addWidget(self.config_settle)

#         timing_row.addWidget(QLabel("Point delay (s):"))
#         self.point_delay = QDoubleSpinBox()
#         self.point_delay.setRange(0.0, 60.0)
#         self.point_delay.setValue(DEFAULT_POINT_DELAY_S)
#         self.point_delay.setDecimals(3)
#         self.point_delay.setSingleStep(0.010)
#         self.point_delay.valueChanged.connect(self._update_estimate)
#         timing_row.addWidget(self.point_delay)

#         lay.addLayout(timing_row)

#         read_row = QHBoxLayout()
#         read_row.addWidget(QLabel("PSU sample (ms):"))
#         self.sample_interval = QSpinBox()
#         self.sample_interval.setRange(50, 10000)
#         self.sample_interval.setSingleStep(50)
#         self.sample_interval.setValue(psu.get_measurement_interval_ms())
#         read_row.addWidget(self.sample_interval)

#         self.turn_off_cb = QCheckBox("Set 0 V when done")
#         self.turn_off_cb.setChecked(False)
#         read_row.addWidget(self.turn_off_cb)
#         read_row.addStretch()
#         lay.addLayout(read_row)

#         self.estimate_lbl = QLabel("")
#         self.estimate_lbl.setStyleSheet("color: #8B949E; font-size: 11px;")
#         lay.addWidget(self.estimate_lbl)

#         btn_row = QHBoxLayout()
#         self.run_btn = QPushButton("Run DUT Shmoo")
#         self.run_btn.setObjectName("btn_success")
#         self.run_btn.clicked.connect(self._run_shmoo)
#         self.stop_btn = QPushButton("Stop")
#         self.stop_btn.setObjectName("btn_danger")
#         self.stop_btn.setEnabled(False)
#         self.stop_btn.clicked.connect(self._stop_shmoo)
#         self.metric_plot_btn = QPushButton("Plot Power/Energy")
#         self.metric_plot_btn.setEnabled(False)
#         self.metric_plot_btn.clicked.connect(self._toggle_metric_plot)
#         btn_row.addWidget(self.run_btn)
#         btn_row.addWidget(self.stop_btn)
#         btn_row.addWidget(self.metric_plot_btn)
#         btn_row.addStretch()
#         lay.addLayout(btn_row)

#         self.progress = QProgressBar()
#         self.progress.setValue(0)
#         lay.addWidget(self.progress)

#         self.status = StatusIndicator("idle")
#         lay.addWidget(self.status)
#         self._update_estimate()
#         return grp

#     def _current_sweep_shape(self):
#         voltages_v = _inclusive_range(
#             self.v_start.value(), self.v_stop.value(), self.v_step.value())
#         freqs_mhz = _inclusive_range(
#             self.f_start.value(), self.f_stop.value(), self.f_step.value())
#         freqs_hz = [mhz * 1_000_000.0 for mhz in freqs_mhz]
#         points = len(voltages_v) * len(freqs_hz)
#         inter_freq_delays = len(voltages_v) * max(0, len(freqs_hz) - 1)
#         estimate_s = (
#             len(voltages_v) * (
#                 self.v_settle.value() + 3.0 + self.config_settle.value()) +
#             inter_freq_delays * self.point_delay.value()
#         )
#         return voltages_v, freqs_hz, estimate_s

#     def _update_estimate(self):
#         if not hasattr(self, "estimate_lbl"):
#             return
#         voltages_v, freqs_hz, estimate_s = self._current_sweep_shape()
#         points = len(voltages_v) * len(freqs_hz)
#         self.estimate_lbl.setText(
#             f"Points: {points}  Configured delay time: {_format_duration(estimate_s)}")

#     def _run_shmoo(self):
#         if self._worker and self._worker.isRunning():
#             return
#         if not uart.is_connected():
#             self.status.set_state("warning", "UART not connected")
#             return
#         if not psu.is_connected():
#             self.status.set_state("warning", "PSU not connected")
#             return

#         self._voltages_v, self._freqs_hz, _ = self._current_sweep_shape()
#         points = len(self._voltages_v) * len(self._freqs_hz)
#         if points > MAX_SHMOO_POINTS:
#             self.status.set_state(
#                 "warning",
#                 f"Too many points ({points}). Increase step size.")
#             return

#         self._result_grid = [[None for _ in self._freqs_hz]
#                              for _ in self._voltages_v]
#         self._color_grid = np.full((len(self._voltages_v), len(self._freqs_hz)),
#                                    -1)
#         self._stop_requested = False
#         self._hover_enabled = False
#         self._plot_mode = "passfail"
#         self._hide_annotation()
#         self.metric_plot_btn.setEnabled(False)
#         self.metric_plot_btn.setText("Plot Power/Energy")
#         self.progress.setValue(0)
#         self._update_plot()

#         self.run_btn.setEnabled(False)
#         self.stop_btn.setEnabled(True)
#         self.status.set_state("busy", "DUT shmoo running")
#         self.result_box.set_busy()

#         self._worker = DUTShmooWorker(
#             self.psu_channel_combo.currentIndex() + 1,
#             self._voltages_v,
#             self._freqs_hz,
#             self.v_settle.value(),
#             self.config_settle.value(),
#             self.point_delay.value(),
#             self.sample_interval.value(),
#             self.turn_off_cb.isChecked(),
#         )
#         self._worker.point_ready.connect(self._on_point)
#         self._worker.status_ready.connect(lambda s: self.status.set_state("busy", s))
#         self._worker.progress.connect(self.progress.setValue)
#         self._worker.finished.connect(self._on_done)
#         self._worker.start()

#     def _stop_shmoo(self):
#         if self._worker:
#             self._stop_requested = True
#             self._worker.stop()
#         self.stop_btn.setEnabled(False)
#         self.status.set_state("busy", "Stopping DUT shmoo")

#     def _on_point(self, result):
#         v_idx = result["v_idx"]
#         f_idx = result["f_idx"]
#         self._result_grid[v_idx][f_idx] = result
#         pass_fail = result.get("pass_fail")
#         if pass_fail == "pass":
#             self._color_grid[v_idx, f_idx] = 0
#         elif pass_fail == "fail":
#             self._color_grid[v_idx, f_idx] = 1
#         else:
#             self._color_grid[v_idx, f_idx] = 2

#         self.result_box.update(result)
#         self._update_plot()

#         parsed = (
#             f"V={result.get('voltage_v', 0):.3f}V "
#             f"F={result.get('actual_freq_hz', result.get('target_freq_hz', 0))/1e6:.4f}MHz "
#             f"{result.get('pass_fail', 'unknown')} "
#             f"P={(result.get('power_w') or 0) * 1000:.3f}mW "
#             f"E={(result.get('energy_j') or 0) * 1000:.4f}mJ"
#         )
#         tx = result.get("tx", b"")
#         rx = result.get("rx", b"")
#         if tx:
#             log_transaction("TX", "DUTShmoo", tx, parsed, result.get("status", ""))
#             self.log_signal.emit("TX", "DUTShmoo", tx, parsed,
#                                  result.get("status", ""))
#         if rx:
#             log_transaction("RX", "DUTShmoo", rx, parsed, result.get("status", ""))
#             self.log_signal.emit("RX", "DUTShmoo", rx, parsed,
#                                  result.get("status", ""))
#         if result.get("status") not in ("ok", None):
#             self.status.set_state("warning", parsed)

#     def _on_done(self):
#         self.run_btn.setEnabled(True)
#         self.stop_btn.setEnabled(False)
#         label = "DUT shmoo stopped" if self._stop_requested else "DUT shmoo complete"
#         self.status.set_state("idle", label)
#         self._worker = None
#         self._hover_enabled = (
#             not self._stop_requested and self._all_points_collected())
#         self.metric_plot_btn.setEnabled(self._hover_enabled)
#         self._update_plot()

#     def _all_points_collected(self):
#         if not self._result_grid:
#             return False
#         return all(result is not None
#                    for row in self._result_grid
#                    for result in row)

#     def _apply_theme(self):
#         rc = get_matplotlib_style(self._current_theme)
#         self._fig.set_facecolor(rc["figure.facecolor"])
#         for ax in self._fig.axes:
#             ax.set_facecolor(rc["axes.facecolor"])
#             for spine in ax.spines.values():
#                 spine.set_edgecolor(rc["axes.edgecolor"])
#             ax.xaxis.label.set_color(rc["axes.labelcolor"])
#             ax.yaxis.label.set_color(rc["axes.labelcolor"])
#             ax.title.set_color(rc["axes.titlecolor"])
#             ax.tick_params(colors=rc["xtick.color"])

#     def _init_plot(self):
#         self._fig.clear()
#         self._ax = self._fig.add_subplot(111)
#         self._hover_axes = [self._ax]
#         self._annot = None
#         self._hover_rect = None
#         self._apply_theme()
#         self._ax.set_title("DUT Shmoo")
#         self._ax.set_xlabel("Frequency (MHz)")
#         self._ax.set_ylabel("Voltage (V)")
#         self._ax.text(0.5, 0.5, "Run DUT shmoo to populate plot",
#                       ha="center", va="center", transform=self._ax.transAxes,
#                       color=get_matplotlib_style(self._current_theme)["text.color"])
#         self._canvas.draw_idle()

#     def _update_plot(self):
#         if self._color_grid is None:
#             self._init_plot()
#             return

#         self._plot_mode = "passfail"
#         if hasattr(self, "metric_plot_btn"):
#             self.metric_plot_btn.setText("Plot Power/Energy")
#         self._fig.clear()
#         self._ax = self._fig.add_subplot(111)
#         self._hover_axes = [self._ax]
#         self._annot = None
#         self._hover_rect = None
#         self._apply_theme()
#         cmap = mcolors.ListedColormap(["#30363D", "#3FB950", "#F85149", "#8B949E"])
#         norm = mcolors.BoundaryNorm([-1.5, -0.5, 0.5, 1.5, 2.5], cmap.N)
#         self._ax.imshow(self._color_grid, origin="lower", aspect="auto",
#                         interpolation="nearest", cmap=cmap, norm=norm)
#         self._ax.set_title("DUT Shmoo")
#         self._ax.set_xlabel("Frequency (MHz)")
#         self._ax.set_ylabel("Voltage (V)")
#         self._ax.set_xticks(range(len(self._freqs_hz)))
#         self._ax.set_xticklabels([f"{f/1e6:.3g}" for f in self._freqs_hz],
#                                  rotation=45, ha="right")
#         self._ax.set_yticks(range(len(self._voltages_v)))
#         self._ax.set_yticklabels([f"{v:.3g}" for v in self._voltages_v])

#         handles = [
#             mpatches.Patch(color="#3FB950", label="Pass"),
#             mpatches.Patch(color="#F85149", label="Fail"),
#             mpatches.Patch(color="#8B949E", label="Error / timeout"),
#         ]
#         rc = get_matplotlib_style(self._current_theme)
#         legend = self._ax.legend(handles=handles, loc="upper right", fontsize=8,
#                                  facecolor=rc["axes.facecolor"],
#                                  labelcolor=rc["text.color"])
#         legend.set_in_layout(False)
#         self._canvas.draw_idle()

#     def _metric_grid(self, key, scale):
#         grid = np.full((len(self._voltages_v), len(self._freqs_hz)), np.nan)
#         for v_idx, row in enumerate(self._result_grid or []):
#             for f_idx, result in enumerate(row):
#                 if not result:
#                     continue
#                 value = result.get(key)
#                 if value is not None:
#                     grid[v_idx, f_idx] = value * scale
#         return grid

#     def _metric_limits(self, grid):
#         valid = grid[~np.isnan(grid)]
#         if valid.size == 0:
#             return 0.0, 1.0
#         low = float(np.min(valid))
#         high = float(np.max(valid))
#         if high <= low:
#             high = low + 1.0
#         return low, high

#     def _format_axis(self, ax, title):
#         ax.set_title(title)
#         ax.set_xlabel("Frequency (MHz)")
#         ax.set_ylabel("Voltage (V)")
#         ax.set_xticks(range(len(self._freqs_hz)))
#         ax.set_xticklabels([f"{f/1e6:.3g}" for f in self._freqs_hz],
#                            rotation=45, ha="right")
#         ax.set_yticks(range(len(self._voltages_v)))
#         ax.set_yticklabels([f"{v:.3g}" for v in self._voltages_v])

#     def _plot_power_energy(self):
#         if not self._all_points_collected():
#             self.status.set_state("warning", "Complete DUT shmoo first")
#             return

#         self._plot_mode = "metrics"
#         self.metric_plot_btn.setText("Show Pass/Fail")
#         self._hide_annotation()
#         self._fig.clear()
#         power_ax = self._fig.add_subplot(121)
#         energy_ax = self._fig.add_subplot(122)
#         self._hover_axes = [power_ax, energy_ax]
#         self._annot = None
#         self._hover_rect = None
#         self._apply_theme()

#         metric_cmap = mcolors.LinearSegmentedColormap.from_list(
#             "navy_to_warm_orange", ["#001F54", "#F4A261"])
#         for ax, grid, title, unit in [
#             (power_ax, self._metric_grid("power_w", 1000.0),
#              "Power Shmoo", "mW"),
#             (energy_ax, self._metric_grid("energy_j", 1000.0),
#              "Energy Shmoo", "mJ"),
#         ]:
#             vmin, vmax = self._metric_limits(grid)
#             image = ax.imshow(grid, origin="lower", aspect="auto",
#                               interpolation="nearest", cmap=metric_cmap,
#                               vmin=vmin, vmax=vmax)
#             image.set_in_layout(False)
#             self._format_axis(ax, f"{title} ({unit})")
#             label = ax.text(
#                 0.99, 0.02, f"min {vmin:.3g}  max {vmax:.3g}",
#                 ha="right", va="bottom", transform=ax.transAxes,
#                 color=get_matplotlib_style(self._current_theme)["text.color"],
#                 fontsize=8)
#             label.set_in_layout(False)

#         self._canvas.draw_idle()

#     def _toggle_metric_plot(self):
#         if self._plot_mode == "metrics":
#             self._update_plot()
#         else:
#             self._plot_power_energy()

#     def _on_hover(self, event):
#         if (not self._hover_enabled or self._result_grid is None or
#                 event.inaxes not in self._hover_axes):
#             self._hide_annotation()
#             return
#         if event.xdata is None or event.ydata is None:
#             self._hide_annotation()
#             return

#         f_idx = int(round(event.xdata))
#         v_idx = int(round(event.ydata))
#         if (
#             v_idx < 0 or v_idx >= len(self._voltages_v) or
#             f_idx < 0 or f_idx >= len(self._freqs_hz)
#         ):
#             self._hide_annotation()
#             return

#         result = self._result_grid[v_idx][f_idx]
#         if not result:
#             self._hide_annotation()
#             return

#         text = self._tooltip_text(result)
#         active_ax = event.inaxes
#         if self._hover_rect is None:
#             self._hover_rect = mpatches.Rectangle(
#                 (f_idx - 0.5, v_idx - 0.5), 1.0, 1.0,
#                 fill=False, edgecolor="#00D4FF", linewidth=2.5,
#                 zorder=20)
#             self._hover_rect.set_in_layout(False)
#             active_ax.add_patch(self._hover_rect)
#         elif self._hover_rect.axes is not active_ax:
#             self._hover_rect.remove()
#             self._hover_rect = mpatches.Rectangle(
#                 (f_idx - 0.5, v_idx - 0.5), 1.0, 1.0,
#                 fill=False, edgecolor="#00D4FF", linewidth=2.5,
#                 zorder=20)
#             self._hover_rect.set_in_layout(False)
#             active_ax.add_patch(self._hover_rect)
#         else:
#             self._hover_rect.set_xy((f_idx - 0.5, v_idx - 0.5))
#             self._hover_rect.set_visible(True)

#         if self._annot is None:
#             self._annot = active_ax.text(
#                 0.015, 0.985, text,
#                 transform=active_ax.transAxes,
#                 ha="left",
#                 va="top",
#                 bbox=dict(boxstyle="round", fc="#FFFFFF", ec="#070707",
#                           alpha=0.98),
#                 color="#000000",
#                 fontsize=8,
#                 zorder=21,
#             )
#             self._annot.set_in_layout(False)
#         elif self._annot.axes is not active_ax:
#             self._annot.remove()
#             self._annot = active_ax.text(
#                 0.015, 0.985, text,
#                 transform=active_ax.transAxes,
#                 ha="left",
#                 va="top",
#                 bbox=dict(boxstyle="round", fc="#FFFFFF", ec="#0A0A0A",
#                           alpha=0.98),
#                 color="#000000",
#                 fontsize=8,
#                 zorder=21,
#             )
#             self._annot.set_in_layout(False)
#         else:
#             self._annot.set_text(text)
#             self._annot.set_visible(True)
#             self._annot.get_bbox_patch().set_facecolor("#FFFFFF")
#             self._annot.get_bbox_patch().set_edgecolor("#00D4FF")
#             self._annot.set_color("#000000")
#         active_ax.figure.canvas.draw_idle()

#     def _tooltip_text(self, result):
#         actual = result.get("actual_freq_hz")
#         power = result.get("power_w")
#         energy = result.get("energy_j")
#         current = result.get("current_a")
#         lines = [
#             f"V: {result.get('voltage_v', 0):.3f} V",
#             f"Target F: {result.get('target_freq_hz', 0)/1e6:.4f} MHz",
#         ]
#         if actual is not None:
#             lines.append(f"Actual F: {actual/1e6:.4f} MHz")
#         lines.append(
#             f"Div/Mult: {result.get('divisor', '-')}/{result.get('multiplier', '-')}")
#         lines.append(f"Result: {result.get('pass_fail', 'unknown')}")
#         if power is not None:
#             lines.append(f"Power: {power * 1000:.3f} mW")
#         if current is not None:
#             lines.append(f"Current: {current * 1000:.3f} mA")
#         if energy is not None:
#             lines.append(f"Energy: {energy * 1000:.4f} mJ")
#         return "\n".join(lines)

#     def _hide_annotation(self):
#         changed = False
#         if self._annot is not None and self._annot.get_visible():
#             self._annot.set_visible(False)
#             changed = True
#         if self._hover_rect is not None and self._hover_rect.get_visible():
#             self._hover_rect.set_visible(False)
#             changed = True
#         if changed:
#             self._canvas.draw_idle()

#     def set_theme(self, theme_name):
#         self._current_theme = theme_name
#         self._update_plot()

# gui/tabs/signal/dut_shmoo_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QSpinBox, QComboBox,
    QProgressBar, QSizePolicy, QScrollArea, QCheckBox,
)

import instruments.psu_2230g as psu
from gui.scale import sc
from gui.widgets import ResultBox, StatusIndicator
from peripherals import uart_handler as uart
from peripherals.chip_config import chip_config
from style.theme import get_matplotlib_style
from utils.session_logger import log_transaction


DUT_PACKET_SOF = 0x55
DUT_PACKET_ID = 0x10
DUT_PACKET_LEN = 0x02
DUT_ACK = 0x5A
DUT_PASS = 0x11
DUT_FAIL = 0x22
DUT_BASE_HZ = 10_000_000.0
MIN_DIVISOR = 1
MAX_DIVISOR = 255
MIN_MULTIPLIER = 2
MAX_MULTIPLIER = 255
MAX_SHMOO_POINTS = 250
UART_POLL_SLICE_S = 0.1
ACK_GUARD_TIMEOUT_S = 30.0
RESULT_GUARD_TIMEOUT_S = 300.0
DEFAULT_VOLTAGE_SETTLE_S = 0.500
DEFAULT_CONFIG_SETTLE_S = 1.000
DEFAULT_POINT_DELAY_S = 3.000


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
        values.append(round(v, 9))
        v += step
    if values and values[-1] < stop:
        values.append(round(stop, 9))
    return values


def _format_duration(seconds):
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f} s"
    return f"{seconds / 60:.1f} min"


def _best_clock_params(target_hz):
    best = None
    best_err = None
    target_hz = max(1.0, float(target_hz))
    for divisor in range(MIN_DIVISOR, MAX_DIVISOR + 1):
        denom = divisor + 1
        ideal_multiplier = int(round((target_hz * denom / DUT_BASE_HZ) - 1))
        for multiplier in (
            ideal_multiplier - 1,
            ideal_multiplier,
            ideal_multiplier + 1,
        ):
            if multiplier < MIN_MULTIPLIER or multiplier > MAX_MULTIPLIER:
                continue
            actual_hz = DUT_BASE_HZ * (multiplier + 1) / denom
            err = abs(actual_hz - target_hz)
            if best is None or err < best_err:
                best = divisor, multiplier, actual_hz
                best_err = err
    if best is None:
        best = (
            MAX_DIVISOR,
            MIN_MULTIPLIER,
            DUT_BASE_HZ * (MIN_MULTIPLIER + 1) / (MAX_DIVISOR + 1),
        )
    return best


class DUTShmooWorker(QThread):
    point_ready = pyqtSignal(dict)
    status_ready = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, psu_channel, voltages_v, freqs_hz, voltage_settle_s,
                 config_settle_s, point_delay_s, sample_interval_ms,
                 turn_off_when_done):
        super().__init__()
        self._psu_channel = psu_channel
        self._voltages_v = voltages_v
        self._freqs_hz = freqs_hz
        self._voltage_settle_s = voltage_settle_s
        self._config_settle_s = config_settle_s
        self._point_delay_s = point_delay_s
        self._sample_interval_ms = sample_interval_ms
        self._turn_off_when_done = turn_off_when_done
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

    def _read_until_expected(self, expected, guard_timeout_s):
        expected = tuple(expected)
        guard_timeout_s = max(UART_POLL_SLICE_S, float(guard_timeout_s))
        deadline = time.time() + guard_timeout_s
        rx = b""

        while not self._stop and time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            chunk = uart.read_raw(
                1, timeout_s=min(UART_POLL_SLICE_S, remaining))
            if not chunk:
                continue
            rx += chunk
            if chunk[0] in expected:
                return chunk[0], rx

        return None, rx

    def _run_dut_point(self, voltage_v, freq_hz):
        divisor, multiplier, actual_hz = _best_clock_params(freq_hz)
        packet = bytes([
            DUT_PACKET_SOF,
            DUT_PACKET_ID,
            DUT_PACKET_LEN,
            divisor,
            multiplier,
        ])
        result = {
            "voltage_v": voltage_v,
            "target_freq_hz": freq_hz,
            "actual_freq_hz": actual_hz,
            "divisor": divisor,
            "multiplier": multiplier,
            "tx": packet,
            "rx": b"",
            "status": "error",
            "pass_fail": "unknown",
        }

        if not uart.is_connected():
            result["status"] = "uart_not_connected"
            return result
        if not psu.is_connected():
            result["status"] = "psu_not_connected"
            return result

        psu.set_measurement_interval_ms(self._sample_interval_ms)
        psu.PSU_measure_start(self._psu_channel)
        t_start = time.time()
        try:
            uart.flush_rx()
            if not uart.send_raw(packet):
                result["status"] = "uart_send_error"
                return result

            ack_byte, ack_rx = self._read_until_expected(
                [DUT_ACK], ACK_GUARD_TIMEOUT_S)
            result["rx"] += ack_rx
            if ack_byte is None:
                result["status"] = "ack_timeout"
                return result

            final_byte, final_rx = self._read_until_expected(
                [DUT_PASS, DUT_FAIL], RESULT_GUARD_TIMEOUT_S)
            result["rx"] += final_rx
            if final_byte is None:
                result["status"] = "result_timeout"
                return result
            if final_byte == DUT_PASS:
                result["status"] = "ok"
                result["pass_fail"] = "pass"
            elif final_byte == DUT_FAIL:
                result["status"] = "ok"
                result["pass_fail"] = "fail"
        finally:
            measurement = psu.PSU_measure_stop()
            result.update({
                "meas_elapsed_s": time.time() - t_start,
                "psu_voltage_v": measurement.get("voltage_v"),
                "current_a": measurement.get("current_a"),
                "power_w": measurement.get("power_w"),
                "energy_j": measurement.get("energy_j"),
            })
        return result

    def run(self):
        total = max(1, len(self._voltages_v) * len(self._freqs_hz))
        done = 0

        for v_idx, voltage_v in enumerate(self._voltages_v):
            if self._stop:
                break

            self.status_ready.emit(
                f"Setting PSU CH{self._psu_channel} to {voltage_v:.3f} V")
            vset_result = psu.PSU_vset(self._psu_channel, voltage_v)
            if vset_result.get("status") != "ok":
                for f_idx, freq_hz in enumerate(self._freqs_hz):
                    done += 1
                    self.point_ready.emit({
                        "v_idx": v_idx,
                        "f_idx": f_idx,
                        "voltage_v": voltage_v,
                        "target_freq_hz": freq_hz,
                        "status": vset_result.get("status", "error"),
                        "pass_fail": "unknown",
                        "vset_result": vset_result,
                    })
                    self.progress.emit(int(done / total * 100))
                continue

            if not self._wait_s(self._voltage_settle_s):
                break

            self.status_ready.emit(f"Configuring chip at {voltage_v:.3f} V")
            config_result = chip_config()
            config_ok = (
                config_result.get("status") == "ok" and
                config_result.get("config_status") == "success"
            )
            if not config_ok:
                for f_idx, freq_hz in enumerate(self._freqs_hz):
                    done += 1
                    self.point_ready.emit({
                        "v_idx": v_idx,
                        "f_idx": f_idx,
                        "voltage_v": voltage_v,
                        "target_freq_hz": freq_hz,
                        "status": "chip_config_failed",
                        "pass_fail": "unknown",
                        "config_result": config_result,
                    })
                    self.progress.emit(int(done / total * 100))
                continue

            if not self._wait_s(self._config_settle_s):
                break

            for f_idx, freq_hz in enumerate(self._freqs_hz):
                if self._stop:
                    break

                self.status_ready.emit(
                    f"DUT shmoo {voltage_v:.3f} V, {freq_hz/1e6:.4f} MHz")
                point = self._run_dut_point(voltage_v, freq_hz)
                point.update({
                    "v_idx": v_idx,
                    "f_idx": f_idx,
                    "config_result": config_result,
                    "vset_result": vset_result,
                })
                done += 1
                self.point_ready.emit(point)
                self.progress.emit(int(done / total * 100))

                if self._stop:
                    break
                if f_idx < len(self._freqs_hz) - 1:
                    self._wait_s(self._point_delay_s)

        if self._turn_off_when_done and psu.is_connected():
            psu.PSU_vset(self._psu_channel, 0.0)


class DUTShmooTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._current_theme = "light"
        self._voltages_v = []
        self._freqs_hz = []
        self._result_grid = None
        self._color_grid = None
        self._stop_requested = False
        self._annot = None
        self._hover_rect = None
        self._hover_enabled = False

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
        self._canvas.mpl_connect("motion_notify_event", self._on_hover)
        self._init_plot()
        root.addWidget(self._canvas)
        root.addStretch()

    def _build_controls(self):
        grp = QGroupBox("DUT Shmoo")
        lay = QVBoxLayout(grp)

        psu_row = QHBoxLayout()
        psu_row.addWidget(QLabel("PSU channel:"))
        self.psu_channel_combo = QComboBox()
        self.psu_channel_combo.addItems(["CH1", "CH2", "CH3"])
        self.psu_channel_combo.setCurrentIndex(2)
        psu_row.addWidget(self.psu_channel_combo)
        psu_row.addStretch()
        lay.addLayout(psu_row)

        v_row = QHBoxLayout()
        v_row.addWidget(QLabel("Voltage start (V):"))
        self.v_start = QDoubleSpinBox()
        self.v_start.setRange(0.0, 30.0)
        self.v_start.setValue(0.8)
        self.v_start.setDecimals(3)
        self.v_start.valueChanged.connect(self._update_estimate)
        v_row.addWidget(self.v_start)

        v_row.addWidget(QLabel("stop:"))
        self.v_stop = QDoubleSpinBox()
        self.v_stop.setRange(0.0, 30.0)
        self.v_stop.setValue(1.2)
        self.v_stop.setDecimals(3)
        self.v_stop.valueChanged.connect(self._update_estimate)
        v_row.addWidget(self.v_stop)

        v_row.addWidget(QLabel("step:"))
        self.v_step = QDoubleSpinBox()
        self.v_step.setRange(0.001, 30.0)
        self.v_step.setValue(0.1)
        self.v_step.setDecimals(3)
        self.v_step.valueChanged.connect(self._update_estimate)
        v_row.addWidget(self.v_step)
        lay.addLayout(v_row)

        f_row = QHBoxLayout()
        f_row.addWidget(QLabel("Frequency start (MHz):"))
        self.f_start = QDoubleSpinBox()
        self.f_start.setRange(0.001, 1280.0)
        self.f_start.setValue(30.0)
        self.f_start.setDecimals(3)
        self.f_start.valueChanged.connect(self._update_estimate)
        f_row.addWidget(self.f_start)

        f_row.addWidget(QLabel("stop:"))
        self.f_stop = QDoubleSpinBox()
        self.f_stop.setRange(0.001, 1280.0)
        self.f_stop.setValue(100.0)
        self.f_stop.setDecimals(3)
        self.f_stop.valueChanged.connect(self._update_estimate)
        f_row.addWidget(self.f_stop)

        f_row.addWidget(QLabel("step:"))
        self.f_step = QDoubleSpinBox()
        self.f_step.setRange(0.001, 1280.0)
        self.f_step.setValue(10.0)
        self.f_step.setDecimals(3)
        self.f_step.valueChanged.connect(self._update_estimate)
        f_row.addWidget(self.f_step)
        lay.addLayout(f_row)

        timing_row = QHBoxLayout()
        timing_row.addWidget(QLabel("Voltage settle (s):"))
        self.v_settle = QDoubleSpinBox()
        self.v_settle.setRange(0.0, 60.0)
        self.v_settle.setValue(DEFAULT_VOLTAGE_SETTLE_S)
        self.v_settle.setDecimals(3)
        self.v_settle.setSingleStep(0.050)
        self.v_settle.valueChanged.connect(self._update_estimate)
        timing_row.addWidget(self.v_settle)

        timing_row.addWidget(QLabel("Config settle (s):"))
        self.config_settle = QDoubleSpinBox()
        self.config_settle.setRange(0.0, 60.0)
        self.config_settle.setValue(DEFAULT_CONFIG_SETTLE_S)
        self.config_settle.setDecimals(3)
        self.config_settle.setSingleStep(0.050)
        self.config_settle.valueChanged.connect(self._update_estimate)
        timing_row.addWidget(self.config_settle)

        timing_row.addWidget(QLabel("Point delay (s):"))
        self.point_delay = QDoubleSpinBox()
        self.point_delay.setRange(0.0, 60.0)
        self.point_delay.setValue(DEFAULT_POINT_DELAY_S)
        self.point_delay.setDecimals(3)
        self.point_delay.setSingleStep(0.010)
        self.point_delay.valueChanged.connect(self._update_estimate)
        timing_row.addWidget(self.point_delay)

        lay.addLayout(timing_row)

        read_row = QHBoxLayout()
        read_row.addWidget(QLabel("PSU sample (ms):"))
        self.sample_interval = QSpinBox()
        self.sample_interval.setRange(50, 10000)
        self.sample_interval.setSingleStep(50)
        self.sample_interval.setValue(psu.get_measurement_interval_ms())
        read_row.addWidget(self.sample_interval)

        self.turn_off_cb = QCheckBox("Set 0 V when done")
        self.turn_off_cb.setChecked(False)
        read_row.addWidget(self.turn_off_cb)
        read_row.addStretch()
        lay.addLayout(read_row)

        self.estimate_lbl = QLabel("")
        self.estimate_lbl.setStyleSheet("color: #8B949E; font-size: 11px;")
        lay.addWidget(self.estimate_lbl)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Run DUT Shmoo")
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
        self._update_estimate()
        return grp

    def _current_sweep_shape(self):
        voltages_v = _inclusive_range(
            self.v_start.value(), self.v_stop.value(), self.v_step.value())
        freqs_mhz = _inclusive_range(
            self.f_start.value(), self.f_stop.value(), self.f_step.value())
        freqs_hz = [mhz * 1_000_000.0 for mhz in freqs_mhz]
        points = len(voltages_v) * len(freqs_hz)
        inter_freq_delays = len(voltages_v) * max(0, len(freqs_hz) - 1)
        estimate_s = (
            len(voltages_v) * (
                self.v_settle.value() + 3.0 + self.config_settle.value()) +
            inter_freq_delays * self.point_delay.value()
        )
        return voltages_v, freqs_hz, estimate_s

    def _update_estimate(self):
        if not hasattr(self, "estimate_lbl"):
            return
        voltages_v, freqs_hz, estimate_s = self._current_sweep_shape()
        points = len(voltages_v) * len(freqs_hz)
        self.estimate_lbl.setText(
            f"Points: {points}  Configured delay time: {_format_duration(estimate_s)}")

    def _run_shmoo(self):
        if self._worker and self._worker.isRunning():
            return
        if not uart.is_connected():
            self.status.set_state("warning", "UART not connected")
            return
        if not psu.is_connected():
            self.status.set_state("warning", "PSU not connected")
            return

        self._voltages_v, self._freqs_hz, _ = self._current_sweep_shape()
        points = len(self._voltages_v) * len(self._freqs_hz)
        if points > MAX_SHMOO_POINTS:
            self.status.set_state(
                "warning",
                f"Too many points ({points}). Increase step size.")
            return

        self._result_grid = [[None for _ in self._freqs_hz]
                             for _ in self._voltages_v]
        self._color_grid = np.full((len(self._voltages_v), len(self._freqs_hz)),
                                   -1)
        self._stop_requested = False
        self._hover_enabled = False
        self._hide_annotation()
        self.progress.setValue(0)
        self._update_plot()

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status.set_state("busy", "DUT shmoo running")
        self.result_box.set_busy()

        self._worker = DUTShmooWorker(
            self.psu_channel_combo.currentIndex() + 1,
            self._voltages_v,
            self._freqs_hz,
            self.v_settle.value(),
            self.config_settle.value(),
            self.point_delay.value(),
            self.sample_interval.value(),
            self.turn_off_cb.isChecked(),
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
        self.status.set_state("busy", "Stopping DUT shmoo")

    def _on_point(self, result):
        v_idx = result["v_idx"]
        f_idx = result["f_idx"]
        self._result_grid[v_idx][f_idx] = result
        pass_fail = result.get("pass_fail")
        if pass_fail == "pass":
            self._color_grid[v_idx, f_idx] = 0
        elif pass_fail == "fail":
            self._color_grid[v_idx, f_idx] = 1
        else:
            self._color_grid[v_idx, f_idx] = 2

        self.result_box.update(result)
        self._update_plot()

        parsed = (
            f"V={result.get('voltage_v', 0):.3f}V "
            f"F={result.get('actual_freq_hz', result.get('target_freq_hz', 0))/1e6:.4f}MHz "
            f"{result.get('pass_fail', 'unknown')} "
            f"P={(result.get('power_w') or 0) * 1000:.3f}mW "
            f"E={(result.get('energy_j') or 0) * 1000:.4f}mJ"
        )
        tx = result.get("tx", b"")
        rx = result.get("rx", b"")
        if tx:
            log_transaction("TX", "DUTShmoo", tx, parsed, result.get("status", ""))
            self.log_signal.emit("TX", "DUTShmoo", tx, parsed,
                                 result.get("status", ""))
        if rx:
            log_transaction("RX", "DUTShmoo", rx, parsed, result.get("status", ""))
            self.log_signal.emit("RX", "DUTShmoo", rx, parsed,
                                 result.get("status", ""))
        if result.get("status") not in ("ok", None):
            self.status.set_state("warning", parsed)

    def _on_done(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        label = "DUT shmoo stopped" if self._stop_requested else "DUT shmoo complete"
        self.status.set_state("idle", label)
        self._worker = None
        self._hover_enabled = (
            not self._stop_requested and self._all_points_collected())
        self._update_plot()

    def _all_points_collected(self):
        if not self._result_grid:
            return False
        return all(result is not None
                   for row in self._result_grid
                   for result in row)

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
        self._annot = None
        self._hover_rect = None
        self._apply_theme()
        self._ax.set_title("DUT Shmoo")
        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("Voltage (V)")
        self._ax.text(0.5, 0.5, "Run DUT shmoo to populate plot",
                      ha="center", va="center", transform=self._ax.transAxes,
                      color=get_matplotlib_style(self._current_theme)["text.color"])
        self._canvas.draw_idle()

    def _update_plot(self):
        if self._color_grid is None:
            self._init_plot()
            return

        self._ax.clear()
        self._annot = None
        self._hover_rect = None
        self._apply_theme()
        cmap = mcolors.ListedColormap(["#30363D", "#3FB950", "#F85149", "#8B949E"])
        norm = mcolors.BoundaryNorm([-1.5, -0.5, 0.5, 1.5, 2.5], cmap.N)
        self._ax.imshow(self._color_grid, origin="lower", aspect="auto",
                        interpolation="nearest", cmap=cmap, norm=norm)
        self._ax.set_title("DUT Shmoo")
        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("Voltage (V)")
        self._ax.set_xticks(range(len(self._freqs_hz)))
        self._ax.set_xticklabels([f"{f/1e6:.3g}" for f in self._freqs_hz],
                                 rotation=45, ha="right")
        self._ax.set_yticks(range(len(self._voltages_v)))
        self._ax.set_yticklabels([f"{v:.3g}" for v in self._voltages_v])

        handles = [
            mpatches.Patch(color="#3FB950", label="Pass"),
            mpatches.Patch(color="#F85149", label="Fail"),
            mpatches.Patch(color="#8B949E", label="Error / timeout"),
        ]
        rc = get_matplotlib_style(self._current_theme)
        legend = self._ax.legend(handles=handles, loc="upper right", fontsize=8,
                                 facecolor=rc["axes.facecolor"],
                                 labelcolor=rc["text.color"])
        legend.set_in_layout(False)
        self._canvas.draw_idle()

    def _on_hover(self, event):
        if (not self._hover_enabled or self._result_grid is None or
                event.inaxes != self._ax):
            self._hide_annotation()
            return
        if event.xdata is None or event.ydata is None:
            self._hide_annotation()
            return

        f_idx = int(round(event.xdata))
        v_idx = int(round(event.ydata))
        if (
            v_idx < 0 or v_idx >= len(self._voltages_v) or
            f_idx < 0 or f_idx >= len(self._freqs_hz)
        ):
            self._hide_annotation()
            return

        result = self._result_grid[v_idx][f_idx]
        if not result:
            self._hide_annotation()
            return

        text = self._tooltip_text(result)
        if self._hover_rect is None:
            self._hover_rect = mpatches.Rectangle(
                (f_idx - 0.5, v_idx - 0.5), 1.0, 1.0,
                fill=False, edgecolor="#00D4FF", linewidth=2.5,
                zorder=20)
            self._hover_rect.set_in_layout(False)
            self._ax.add_patch(self._hover_rect)
        else:
            self._hover_rect.set_xy((f_idx - 0.5, v_idx - 0.5))
            self._hover_rect.set_visible(True)

        if self._annot is None:
            self._annot = self._ax.text(
                0.015, 0.985, text,
                transform=self._ax.transAxes,
                ha="left",
                va="top",
                bbox=dict(boxstyle="round", fc="#FFFFFF", ec="#00D4FF",
                          alpha=0.98),
                color="#000000",
                fontsize=8,
                zorder=21,
            )
            self._annot.set_in_layout(False)
        else:
            self._annot.set_text(text)
            self._annot.set_visible(True)
            self._annot.get_bbox_patch().set_facecolor("#FFFFFF")
            self._annot.get_bbox_patch().set_edgecolor("#00D4FF")
            self._annot.set_color("#000000")
        self._canvas.draw_idle()

    def _tooltip_text(self, result):
        actual = result.get("actual_freq_hz")
        power = result.get("power_w")
        energy = result.get("energy_j")
        current = result.get("current_a")
        lines = [
            f"V: {result.get('voltage_v', 0):.3f} V",
            f"Target F: {result.get('target_freq_hz', 0)/1e6:.4f} MHz",
        ]
        if actual is not None:
            lines.append(f"Actual F: {actual/1e6:.4f} MHz")
        lines.append(
            f"Div/Mult: {result.get('divisor', '-')}/{result.get('multiplier', '-')}")
        lines.append(f"Result: {result.get('pass_fail', 'unknown')}")
        if power is not None:
            lines.append(f"Power: {power * 1000:.3f} mW")
        if current is not None:
            lines.append(f"Current: {current * 1000:.3f} mA")
        if energy is not None:
            lines.append(f"Energy: {energy * 1000:.4f} mJ")
        return "\n".join(lines)

    def _hide_annotation(self):
        changed = False
        if self._annot is not None and self._annot.get_visible():
            self._annot.set_visible(False)
            changed = True
        if self._hover_rect is not None and self._hover_rect.get_visible():
            self._hover_rect.set_visible(False)
            changed = True
        if changed:
            self._canvas.draw_idle()

    def set_theme(self, theme_name):
        self._current_theme = theme_name
        self._update_plot()