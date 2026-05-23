# gui/tabs/power/pmic_tab.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from PyQt5.QtCore    import pyqtSignal, Qt, QThread
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QDoubleSpinBox, QLineEdit,
    QButtonGroup, QRadioButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QSplitter,
)

from peripherals.pmic        import (
    unlock_pmic,
    configure_buck_voltage_and_enable, configure_ldo_voltage_and_enable,
    disable_buck, disable_ldo,
    pmic_generic_write, pmic_generic_read,
)
from utils.pmic_vset_table   import vset_from_voltage, voltage_from_vset
from utils.pmic_registers    import BUCK_REGS, LDO_REGS, compute_opcodes
from workers.qthread_worker  import run_in_thread
from gui.widgets             import ResultBox, StatusIndicator
from utils.session_logger    import log_transaction
from gui.scale               import sc


class PMICVoltageSweepWorker(QThread):
    step_ready = pyqtSignal(object)

    def __init__(self, is_ldo, rail_num, parent=None):
        super().__init__(parent)
        self._is_ldo = is_ldo
        self._rail_num = rail_num
        self._stop = False

    def stop(self):
        self._stop = True

    def _wait_500ms(self):
        for _ in range(10):
            if self._stop:
                return False
            self.msleep(50)
        return True

    def _emit_step(self, label, result):
        result["sweep_step"] = label
        self.step_ready.emit(result)

    def run(self):
        set_fn = configure_ldo_voltage_and_enable if self._is_ldo else configure_buck_voltage_and_enable
        disable_fn = disable_ldo if self._is_ldo else disable_buck
        pattern = [
            ("off", None),
            ("1V", 1000.0),
            ("2V", 2000.0),
            ("1V", 1000.0),
            ("off", None),
        ]

        while not self._stop:
            for label, voltage_mv in pattern:
                if self._stop:
                    break
                result = disable_fn(self._rail_num) if voltage_mv is None else set_fn(
                    self._rail_num, voltage_mv)
                self._emit_step(label, result)
                if result.get("status") != "ok":
                    self._stop = True
                    break
                if not self._wait_500ms():
                    break


class PMICTab(QWidget):
    log_signal = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._sweep_worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(12, 12, 12, 12)
        inner_lay.setSpacing(10)

        inner_lay.addWidget(self._build_unlock_group())
        inner_lay.addWidget(self._build_regulator_group())
        inner_lay.addWidget(self._build_readback_group())
        inner_lay.addWidget(self._build_generic_group())

        self.result_box = ResultBox()
        inner_lay.addWidget(self.result_box)
        inner_lay.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll)

    # ── Unlock ────────────────────────────────────────────────────────────
    def _build_unlock_group(self):
        grp = QGroupBox("PMIC Unlock  (MCP16701)")
        lay = QVBoxLayout(grp)

        info = QLabel(
            "Must be called before writing any voltage register.\n"
            "TX: AA 04 04 AA 07 D3 DD  (hardcoded unlock sequence)"
        )
        info.setStyleSheet("color: #8B949E; font-size: 11px;")
        lay.addWidget(info)

        row = QHBoxLayout()
        self.unlock_btn = QPushButton("🔓  Unlock PMIC")
        self.unlock_btn.setObjectName("btn_primary")
        self.unlock_btn.setToolTip(
            "Send unlock sequence to MCP16701 PMIC.\n\n"
            "TX: AA 04 04 AA 07 D3 DD\n"
            "  SOF 0xAA = Write\n"
            "  ID  0x04 = PMIC\n"
            "  LEN 0x04 = 4 data bytes\n"
            "  CMD 0xAA = write command\n"
            "  OPCODE_H 0x07, OPCODE_L 0xD3 = unlock register\n"
            "  VALUE 0xDD = unlock code\n\n"
            "RX: 5A 5A"
        )
        self.unlock_btn.clicked.connect(self._unlock)
        self.unlock_status = StatusIndicator("idle")
        row.addWidget(self.unlock_btn)
        row.addWidget(self.unlock_status)
        row.addStretch()
        lay.addLayout(row)
        return grp

    # ── Regulator control ─────────────────────────────────────────────────
    def _build_regulator_group(self):
        grp = QGroupBox("Regulator Voltage Control")
        lay = QVBoxLayout(grp)

        # Radio buttons: Buck 1-8, LDO 1-4
        rail_row = QHBoxLayout()
        self._rail_group = QButtonGroup(self)
        self._rail_btns  = {}

        buck_box = QGroupBox("Buck")
        buck_lay = QHBoxLayout(buck_box)
        for i in range(1, 9):
            rb = QRadioButton(f"B{i}")
            rb.setToolTip(
                f"Select Buck regulator {i}.\n"
                f"VSET0: 0x{BUCK_REGS[i]['VSET0']:03X}  "
                f"VSET1: 0x{BUCK_REGS[i]['VSET1']:03X}\n"
                "Voltage range: 600–3300 mV\n"
                "Both VSET0 and VSET1 are written with the same code."
            )
            if i == 1:
                rb.setChecked(True)
            self._rail_group.addButton(rb, i)
            self._rail_btns[("buck", i)] = rb
            buck_lay.addWidget(rb)
        rail_row.addWidget(buck_box)

        ldo_box = QGroupBox("LDO")
        ldo_lay = QHBoxLayout(ldo_box)
        for i in range(1, 5):
            rb = QRadioButton(f"L{i}")
            rb.setToolTip(
                f"Select LDO regulator {i}.\n"
                f"VSET0: 0x{LDO_REGS[i]['VSET0']:03X}  "
                f"VSET1: 0x{LDO_REGS[i]['VSET1']:03X}\n"
                "Voltage range: 600–3300 mV\n"
                "Both VSET0 and VSET1 are written with the same code."
            )
            self._rail_group.addButton(rb, 100 + i)  # 101-104 = LDO 1-4
            self._rail_btns[("ldo", i)] = rb
            ldo_lay.addWidget(rb)
        rail_row.addWidget(ldo_box)
        lay.addLayout(rail_row)

        # Voltage input
        volt_row = QHBoxLayout()
        volt_row.addWidget(QLabel("Target Voltage (mV):"))
        self.volt_spin = QDoubleSpinBox()
        self.volt_spin.setRange(600.0, 3300.0)
        self.volt_spin.setDecimals(1)
        self.volt_spin.setSingleStep(25.0)
        self.volt_spin.setValue(1000.0)
        self.volt_spin.setToolTip(
            "Target output voltage in mV.\n"
            "Buck range: 600–3300 mV\n"
            "LDO  range: 600–3300 mV\n\n"
            "The nearest valid VSET code will be used (non-linear table).\n"
            "See 'Nearest valid' label for the resolved voltage."
        )
        self.volt_spin.valueChanged.connect(self._update_vset_preview)
        volt_row.addWidget(self.volt_spin)
        lay.addLayout(volt_row)

        # Nearest valid preview
        self.nearest_lbl = QLabel("Nearest valid: — mV  (VSET = 0x--)")
        self.nearest_lbl.setObjectName("label_value")
        lay.addWidget(self.nearest_lbl)
        self._update_vset_preview()

        # Buttons
        btn_row = QHBoxLayout()
        self.set_volt_btn = QPushButton("Enable")
        self.set_volt_btn.setObjectName("btn_primary")
        self.set_volt_btn.setToolTip(
            "Unlock PMIC, write VSET0/VSET1, read both back, then enable.\n"
            "If VSET readback does not match, retry from unlock."
        )
        self.set_volt_btn.clicked.connect(self._set_voltage)

        self.disable_btn = QPushButton("Disable")
        self.disable_btn.setObjectName("btn_danger")
        self.disable_btn.setToolTip(
            "Unlock PMIC, write the selected regulator enable register to off,\n"
            "then read back the enable register to verify."
        )
        self.disable_btn.clicked.connect(self._disable_regulator)

        self.sweep_btn = QPushButton("Voltage Sweep")
        self.sweep_btn.setObjectName("btn_success")
        self.sweep_btn.setToolTip(
            "Repeat on the selected rail: off, 1 V, 2 V, 1 V, off.\n"
            "Each state is held for 500 ms until Stop Sweep is clicked."
        )
        self.sweep_btn.clicked.connect(self._start_voltage_sweep)

        self.stop_sweep_btn = QPushButton("Stop Sweep")
        self.stop_sweep_btn.setObjectName("btn_danger")
        self.stop_sweep_btn.setEnabled(False)
        self.stop_sweep_btn.clicked.connect(self._stop_voltage_sweep)

        btn_row.addWidget(self.set_volt_btn)
        btn_row.addWidget(self.disable_btn)
        btn_row.addWidget(self.sweep_btn)
        btn_row.addWidget(self.stop_sweep_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.sweep_status = StatusIndicator("idle")
        lay.addWidget(self.sweep_status)
        return grp

    # ── Readback table ────────────────────────────────────────────────────
    def _build_readback_group(self):
        grp = QGroupBox("Read Back All Regulators")
        lay = QVBoxLayout(grp)

        self.readall_btn = QPushButton("🔄  Read All Regulators")
        self.readall_btn.setToolTip(
            "Read VSET0 register of every Buck (1–8) and LDO (1–4).\n"
            "Decodes each VSET code to voltage in mV.\n"
            "Useful for verifying current regulator state."
        )
        self.readall_btn.clicked.connect(self._read_all)
        lay.addWidget(self.readall_btn)

        self.readall_table = QTableWidget(12, 4)
        self.readall_table.setHorizontalHeaderLabels(
            ["Rail", "Reg Addr", "VSET Code", "Voltage (mV)"])
        self.readall_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.readall_table.setFixedHeight(sc(260))
        self.readall_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.readall_table.verticalHeader().setVisible(False)

        # Pre-populate rail names
        rails = (
            [(f"Buck {i}", BUCK_REGS[i]["VSET0"]) for i in range(1, 9)] +
            [(f"LDO {i}",  LDO_REGS[i]["VSET0"])  for i in range(1, 5)]
        )
        for row, (name, addr) in enumerate(rails):
            self.readall_table.setItem(row, 0, QTableWidgetItem(name))
            self.readall_table.setItem(row, 1,
                QTableWidgetItem(f"0x{addr:03X}"))
            self.readall_table.setItem(row, 2, QTableWidgetItem("—"))
            self.readall_table.setItem(row, 3, QTableWidgetItem("—"))
        lay.addWidget(self.readall_table)
        return grp

    # ── Generic read/write ────────────────────────────────────────────────
    def _build_generic_group(self):
        grp = QGroupBox("Generic Register Access")
        lay = QVBoxLayout(grp)

        addr_row = QHBoxLayout()
        addr_row.addWidget(QLabel("Register Address (hex, 10-bit):"))
        self.generic_addr = QLineEdit("0x22F")
        self.generic_addr.setToolTip(
            "10-bit PMIC register address in hex.\n"
            "Format: 0xXXX  (e.g. 0x22F for Buck3 VSET0)\n"
            "Range: 0x000 – 0x3FF\n\n"
            "OPCODE_H and OPCODE_L will be computed automatically:\n"
            "  OPCODE_H = (1<<2) | (addr[9:8])\n"
            "  OPCODE_L = addr[7:0]"
        )
        self.generic_addr.textChanged.connect(self._update_opcode_preview)
        addr_row.addWidget(self.generic_addr)
        lay.addLayout(addr_row)

        # Opcode preview
        self.opcode_preview = QLabel("OPCODE_H: 0x--   OPCODE_L: 0x--")
        self.opcode_preview.setObjectName("label_value")
        lay.addWidget(self.opcode_preview)
        self._update_opcode_preview()

        val_row = QHBoxLayout()
        val_row.addWidget(QLabel("Value (hex):"))
        self.generic_val = QLineEdit("0x00")
        self.generic_val.setToolTip(
            "Single byte value to write, in hex.\n"
            "Format: 0xXX  (e.g. 0xA0)\n"
            "Range: 0x00 – 0xFF"
        )
        val_row.addWidget(self.generic_val)
        lay.addLayout(val_row)

        self.read_result_lbl = QLabel("Read result: —")
        self.read_result_lbl.setObjectName("label_value")
        lay.addWidget(self.read_result_lbl)

        btn_row = QHBoxLayout()
        wr_btn = QPushButton("Write Register")
        wr_btn.setToolTip(
            "Write the specified value to the register address.\n"
            "TX: AA 04 04 AA [OPCODE_H][OPCODE_L][VALUE]\n"
            "RX: 5A 5A"
        )
        wr_btn.clicked.connect(self._generic_write)
        rd_btn = QPushButton("Read Register")
        rd_btn.setToolTip(
            "Read one byte from the register address.\n"
            "TX: 55 04 04 55 [OPCODE_H][OPCODE_L] 00\n"
            "RX: 5A [value]"
        )
        rd_btn.clicked.connect(self._generic_read)
        btn_row.addWidget(wr_btn)
        btn_row.addWidget(rd_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        return grp

    # ── Helpers ───────────────────────────────────────────────────────────
    def _update_vset_preview(self):
        mv = self.volt_spin.value()
        rail_id = self._rail_group.checkedId()
        is_ldo = rail_id >= 100
        code, actual, _ = vset_from_voltage(mv, is_ldo=is_ldo)
        self.nearest_lbl.setText(
            f"Nearest valid: {actual:.4f} mV  (VSET = 0x{code:02X})")

    def _update_opcode_preview(self):
        try:
            addr = int(self.generic_addr.text(), 16)
            h, l = compute_opcodes(addr)
            self.opcode_preview.setText(
                f"OPCODE_H: 0x{h:02X}   OPCODE_L: 0x{l:02X}")
        except Exception:
            self.opcode_preview.setText("OPCODE_H: 0x--   OPCODE_L: 0x--")

    def _rail_info(self):
        """Return (is_ldo, rail_num) from current radio selection."""
        rid = self._rail_group.checkedId()
        if rid >= 100:
            return True, rid - 100
        return False, rid

    # ── Actions ───────────────────────────────────────────────────────────
    def _unlock(self):
        self.unlock_btn.setEnabled(False)
        self.unlock_status.set_state("busy")
        self._thread, _ = run_in_thread(
            unlock_pmic,
            on_result=self._on_unlock,
            on_error=lambda tb: (
                self.unlock_btn.setEnabled(True),
                self.unlock_status.set_state("error")),
            parent=self,
        )

    def _on_unlock(self, result):
        self.unlock_btn.setEnabled(True)
        ok = result.get("status") == "ok"
        self.unlock_status.set_state("ok" if ok else "error",
                                     "Unlocked ✓" if ok else "Failed ✗")
        self.result_box.update(result)
        log_transaction("TX", "PMIC", result.get("tx", b""),
                        "unlock_pmic()", result.get("status", ""))
        self.log_signal.emit("TX", "PMIC", result.get("tx", b""),
                             "unlock_pmic()", result.get("status", ""))

    def _set_voltage(self):
        is_ldo, num = self._rail_info()
        mv = self.volt_spin.value()
        self.set_volt_btn.setEnabled(False)
        self.disable_btn.setEnabled(False)
        self.result_box.set_busy()
        fn = configure_ldo_voltage_and_enable if is_ldo else configure_buck_voltage_and_enable
        self._thread, _ = run_in_thread(
            fn, num, mv,
            on_result=self._on_voltage_set,
            on_error=self._on_regulator_error,
            parent=self,
        )

    def _on_voltage_set(self, result):
        self.set_volt_btn.setEnabled(True)
        self.disable_btn.setEnabled(True)
        self.result_box.update(result)
        actual = result.get("actual_mv", 0)
        vset   = result.get("vset_code", 0)
        attempts = result.get("attempt_count", 0)
        rail = f"{result.get('rail_type', '?')} {result.get('rail_num', '?')}"
        parsed = (
            f"enable {rail} actual={actual:.4f}mV "
            f"VSET=0x{vset:02X} attempts={attempts}"
        )
        log_transaction("TX", "PMIC", result.get("tx", b""),
                        parsed, result.get("status", ""))
        self.log_signal.emit("TX", "PMIC", result.get("tx", b""),
                             parsed, result.get("status", ""))

    def _disable_regulator(self):
        is_ldo, num = self._rail_info()
        self.set_volt_btn.setEnabled(False)
        self.disable_btn.setEnabled(False)
        self.result_box.set_busy()
        fn = disable_ldo if is_ldo else disable_buck
        self._thread, _ = run_in_thread(
            fn, num,
            on_result=self._on_regulator_disabled,
            on_error=self._on_regulator_error,
            parent=self,
        )

    def _on_regulator_disabled(self, result):
        self.set_volt_btn.setEnabled(True)
        self.disable_btn.setEnabled(True)
        self.result_box.update(result)
        rail = f"{result.get('rail_type', '?')} {result.get('rail_num', '?')}"
        value = result.get("enable_value", 0)
        parsed = f"disable {rail} value=0x{value:02X}"
        log_transaction("TX", "PMIC", result.get("tx", b""),
                        parsed, result.get("status", ""))
        self.log_signal.emit("TX", "PMIC", result.get("tx", b""),
                             parsed, result.get("status", ""))

    def _on_regulator_error(self, tb):
        self.set_volt_btn.setEnabled(True)
        self.disable_btn.setEnabled(True)
        self.sweep_btn.setEnabled(True)
        self.stop_sweep_btn.setEnabled(False)
        self.result_box.status.set_custom("#F85149", tb.splitlines()[-1])

    def _start_voltage_sweep(self):
        if self._sweep_worker and self._sweep_worker.isRunning():
            return

        is_ldo, num = self._rail_info()
        self.set_volt_btn.setEnabled(False)
        self.disable_btn.setEnabled(False)
        self.sweep_btn.setEnabled(False)
        self.stop_sweep_btn.setEnabled(True)
        self.sweep_status.set_state("busy", "Voltage sweep running")
        self.result_box.set_busy()

        self._sweep_worker = PMICVoltageSweepWorker(is_ldo, num, parent=self)
        self._sweep_worker.step_ready.connect(self._on_sweep_step)
        self._sweep_worker.finished.connect(self._on_sweep_finished)
        self._sweep_worker.start()

    def _stop_voltage_sweep(self):
        if self._sweep_worker:
            self._sweep_worker.stop()
        self.stop_sweep_btn.setEnabled(False)
        self.sweep_status.set_state("busy", "Stopping sweep")

    def _on_sweep_step(self, result):
        self.result_box.update(result)
        step = result.get("sweep_step", "?")
        rail = f"{result.get('rail_type', '?')} {result.get('rail_num', '?')}"
        status = result.get("status", "")
        self.sweep_status.set_state(
            "ok" if status == "ok" else "error",
            f"Sweep {rail}: {step}"
        )
        parsed = f"sweep {rail} step={step}"
        log_transaction("TX", "PMIC", result.get("tx", b""),
                        parsed, status)
        self.log_signal.emit("TX", "PMIC", result.get("tx", b""),
                             parsed, status)

    def _on_sweep_finished(self):
        self.set_volt_btn.setEnabled(True)
        self.disable_btn.setEnabled(True)
        self.sweep_btn.setEnabled(True)
        self.stop_sweep_btn.setEnabled(False)
        self.sweep_status.set_state("idle", "Sweep stopped")
        self._sweep_worker = None

    def _read_all(self):
        self.readall_btn.setEnabled(False)
        self._thread, _ = run_in_thread(
            self._read_all_worker,
            on_result=self._on_read_all,
            on_error=lambda _: self.readall_btn.setEnabled(True),
            parent=self,
        )

    @staticmethod
    def _read_all_worker():
        results = {}
        for i in range(1, 9):
            r = pmic_generic_read(BUCK_REGS[i]["VSET0"])
            results[f"buck_{i}"] = r
        for i in range(1, 5):
            r = pmic_generic_read(LDO_REGS[i]["VSET0"])
            results[f"ldo_{i}"] = r
        return results

    def _on_read_all(self, result):
        self.readall_btn.setEnabled(True)
        row = 0
        for i in range(1, 9):
            r = result.get(f"buck_{i}", {})
            v = r.get("value_read")
            mv = r.get("voltage_mv")
            self.readall_table.setItem(row, 2,
                QTableWidgetItem(f"0x{v:02X}" if v is not None else "—"))
            self.readall_table.setItem(row, 3,
                QTableWidgetItem(f"{mv:.4f}" if mv is not None else "—"))
            row += 1
        for i in range(1, 5):
            r = result.get(f"ldo_{i}", {})
            v = r.get("value_read")
            mv = r.get("voltage_mv")
            self.readall_table.setItem(row, 2,
                QTableWidgetItem(f"0x{v:02X}" if v is not None else "—"))
            self.readall_table.setItem(row, 3,
                QTableWidgetItem(f"{mv:.4f}" if mv is not None else "—"))
            row += 1

    def _generic_write(self):
        try:
            addr = int(self.generic_addr.text(), 16)
            val  = int(self.generic_val.text(), 16)
        except ValueError:
            return
        self._thread, _ = run_in_thread(
            pmic_generic_write, addr, val,
            on_result=lambda r: self.result_box.update(r),
            on_error=None,
            parent=self,
        )

    def _generic_read(self):
        try:
            addr = int(self.generic_addr.text(), 16)
        except ValueError:
            return
        self._thread, _ = run_in_thread(
            pmic_generic_read, addr,
            on_result=self._on_generic_read,
            on_error=None,
            parent=self,
        )

    def _on_generic_read(self, result):
        self.result_box.update(result)
        v  = result.get("value_read")
        mv = result.get("voltage_mv")
        if v is not None:
            self.read_result_lbl.setText(
                f"Read result: 0x{v:02X}  ({v})  → {mv:.4f} mV"
                if mv is not None else
                f"Read result: 0x{v:02X}  ({v})"
            )
