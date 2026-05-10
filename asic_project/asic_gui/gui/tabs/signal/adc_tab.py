# gui/tabs/signal/adc_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import Qt, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QButtonGroup, QRadioButton,
    QSizePolicy,
    QScrollArea,)

from peripherals.adc         import adc_write, adc_read, adc_read_channel, adc_scan_all
from workers.qthread_worker  import run_in_thread
from gui.widgets             import ResultBox, ValueDisplay, VoltageBar
from utils.session_logger    import log_transaction


class ADCTab(QWidget):
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

        # ── Channel select ────────────────────────────────────────────────
        ch_grp = QGroupBox("Channel Selection")
        ch_lay = QHBoxLayout(ch_grp)
        self._ch_group = QButtonGroup(self)
        for i in range(8):
            rb = QRadioButton(f"CH{i}")
            rb.setToolTip(
                f"Select ADC channel {i} for single conversion.\n"
                "Range: CH0–CH7 (0–7)\n"
                "Reference: 2.5 V unipolar\n"
                "Resolution: 16-bit (0–65535 counts)\n"
                f"Voltage formula: (raw / 65535) × 2500 mV"
            )
            if i == 0:
                rb.setChecked(True)
            self._ch_group.addButton(rb, i)
            ch_lay.addWidget(rb)
        root.addWidget(ch_grp)

        # ── Single conversion ─────────────────────────────────────────────
        conv_grp = QGroupBox("Single Conversion")
        conv_lay = QHBoxLayout(conv_grp)

        self.trig_btn = QPushButton("⚡ Trigger")
        self.trig_btn.setToolTip(
            "Trigger ADC conversion on the selected channel.\n\n"
            "TX: AA 20 03 A1 [CH] FF\n"
            "  SOF 0xAA = Write\n"
            "  ID  0x20 = ADC\n"
            "  CMD 0xA1 = trigger conversion\n"
            "  CH  = channel 0–7\n"
            "  0xFF = ignored\n\n"
            "RX: 5A 5A (conversion takes ~4.1 µs)\n"
            "Wait 5 ms before reading result."
        )
        self.trig_btn.clicked.connect(self._trigger)

        self.read_btn = QPushButton("📖 Read Result")
        self.read_btn.setToolTip(
            "Read last conversion result.\n\n"
            "TX: 55 20 01 A2\n"
            "RX: 5A [MSB] [LSB]\n"
            "Voltage = (raw / 65535) × 2500 mV"
        )
        self.read_btn.clicked.connect(self._read)

        self.trig_read_btn = QPushButton("▶ Trigger + Read")
        self.trig_read_btn.setObjectName("btn_primary")
        self.trig_read_btn.setToolTip(
            "Trigger conversion, wait 5 ms, then read result.\n"
            "Convenience wrapper combining both steps.")
        self.trig_read_btn.clicked.connect(self._trig_read)

        conv_lay.addWidget(self.trig_btn)
        conv_lay.addWidget(self.read_btn)
        conv_lay.addWidget(self.trig_read_btn)
        root.addWidget(conv_grp)

        # ── Single result display ─────────────────────────────────────────
        single_grp = QGroupBox("Single Channel Result")
        single_lay = QVBoxLayout(single_grp)
        self.raw_disp   = ValueDisplay("Raw (dec)", "",    width=110)
        self.hex_disp   = ValueDisplay("Raw (hex)", "",    width=110)
        self.bin_disp   = ValueDisplay("Binary",    "",    width=110)
        self.volt_disp  = ValueDisplay("Voltage",   "mV",  width=110)
        for w in [self.raw_disp, self.hex_disp, self.bin_disp, self.volt_disp]:
            single_lay.addWidget(w)
        root.addWidget(single_grp)

        # ── All-channel scan ──────────────────────────────────────────────
        scan_grp = QGroupBox("Scan All 8 Channels")
        scan_lay = QVBoxLayout(scan_grp)

        self.scan_btn = QPushButton("🔄  Scan All Channels")
        self.scan_btn.setObjectName("btn_success")
        self.scan_btn.setToolTip(
            "Read all 8 ADC channels sequentially.\n"
            "Triggers conversion on CH0 → read → CH1 → read → … → CH7.\n"
            "Each conversion: 5 ms wait.\n"
            "Total time: ~40 ms"
        )
        self.scan_btn.clicked.connect(self._scan_all)
        scan_lay.addWidget(self.scan_btn)

        self._volt_bars = []
        for i in range(8):
            bar = VoltageBar(i)
            self._volt_bars.append(bar)
            scan_lay.addWidget(bar)
        root.addWidget(scan_grp)

        self.result_box = ResultBox()
        root.addWidget(self.result_box)
        root.addStretch()

    def _selected_channel(self):
        return self._ch_group.checkedId()

    def _trigger(self):
        ch = self._selected_channel()
        self.trig_btn.setEnabled(False)
        self._thread, _ = run_in_thread(
            adc_write, ch,
            on_result=lambda r: self._log_and_enable(r, self.trig_btn),
            on_error=lambda _: self.trig_btn.setEnabled(True),
            parent=self,
        )

    def _read(self):
        self.read_btn.setEnabled(False)
        self._thread, _ = run_in_thread(
            adc_read,
            on_result=self._on_single,
            on_error=lambda _: self.read_btn.setEnabled(True),
            parent=self,
        )

    def _trig_read(self):
        ch = self._selected_channel()
        for b in [self.trig_btn, self.read_btn, self.trig_read_btn]:
            b.setEnabled(False)
        self.result_box.set_busy()
        self._thread, _ = run_in_thread(
            adc_read_channel, ch,
            on_result=self._on_single_full,
            on_error=self._on_error,
            parent=self,
        )

    def _on_single(self, result):
        self.read_btn.setEnabled(True)
        self._display_single(result)
        self.result_box.update(result)
        self._emit_log(result)

    def _on_single_full(self, result):
        for b in [self.trig_btn, self.read_btn, self.trig_read_btn]:
            b.setEnabled(True)
        self._display_single(result)
        self.result_box.update(result)
        self._emit_log(result)

    def _display_single(self, result):
        raw = result.get("raw")
        mv  = result.get("voltage_mv")
        if raw is not None:
            self.raw_disp.set_value(raw, "{:.0f}")
            self.hex_disp.set_value(None)
            self.hex_disp._val.setText(f"0x{raw:04X}")
            self.bin_disp.set_value(None)
            self.bin_disp._val.setText(result.get("binary", "—"))
            self.volt_disp.set_value(mv, "{:.3f}")

    def _scan_all(self):
        self.scan_btn.setEnabled(False)
        self._thread, _ = run_in_thread(
            adc_scan_all,
            on_result=self._on_scan,
            on_error=lambda _: self.scan_btn.setEnabled(True),
            parent=self,
        )

    def _on_scan(self, result):
        self.scan_btn.setEnabled(True)
        channels = result.get("channels", {})
        for i, bar in enumerate(self._volt_bars):
            ch_data = channels.get(i, {})
            bar.set_voltage(ch_data.get("voltage_mv"))
        log_transaction("TX", "ADC", b"", "adc_scan_all()", "ok")
        self.log_signal.emit("TX", "ADC", b"", "adc_scan_all()", "ok")

    def _log_and_enable(self, result, btn):
        btn.setEnabled(True)
        self.result_box.update(result)
        self._emit_log(result)

    def _emit_log(self, result):
        ch = result.get("channel", "?")
        mv = result.get("voltage_mv")
        parsed = (f"CH{ch} raw={result.get('raw')} "
                  f"volt={mv:.3f}mV" if mv is not None else f"CH{ch}")
        log_transaction("TX", "ADC", result.get("tx", b""),
                        parsed, result.get("status", ""))
        log_transaction("RX", "ADC", result.get("rx", b""),
                        parsed, result.get("status", ""))
        self.log_signal.emit("TX", "ADC", result.get("tx", b""),
                             parsed, result.get("status", ""))
        self.log_signal.emit("RX", "ADC", result.get("rx", b""),
                             parsed, result.get("status", ""))

    def _on_error(self, tb):
        for b in [self.trig_btn, self.read_btn, self.trig_read_btn]:
            b.setEnabled(True)
        self.result_box.status.set_custom("#F85149", tb.splitlines()[-1])
