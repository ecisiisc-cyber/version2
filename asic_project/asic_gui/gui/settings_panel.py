# gui/settings_panel.py
# Always-visible left panel: UART + SMU + PSU connection controls.
# Wrapped in a QScrollArea so nothing clips on small/short screens.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import serial.tools.list_ports
from PyQt5.QtCore    import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QGroupBox, QScrollArea, QSizePolicy,
)
from gui.scale import sc, settings_panel_width

import peripherals.uart_handler as uart
import instruments.smu_2602b   as smu
import instruments.psu_2230g   as psu
from utils.session_logger import init_session, get_session_log_path


def _dot(color="#30363D"):
    lbl = QLabel("●")
    lbl.setStyleSheet(f"color: {color}; font-size: 13px;")
    lbl.setFixedWidth(sc(18))
    lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lbl


def _section_label(text):
    lbl = QLabel(text)
    lbl.setObjectName("label_section")
    return lbl


class SettingsPanel(QWidget):
    uart_connected = pyqtSignal(bool)
    smu_connected  = pyqtSignal(bool)
    psu_connected  = pyqtSignal(bool)
    log_message    = pyqtSignal(str, str, bytes, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(settings_panel_width())
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._uart_ok = False
        self._smu_ok  = False
        self._psu_ok  = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area prevents clipping on FHD laptop
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)
        lay.addWidget(self._build_uart_group())
        lay.addWidget(self._build_smu_group())
        lay.addWidget(self._build_psu_group())
        lay.addWidget(self._build_session_group())
        lay.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._port_timer = QTimer(self)
        self._port_timer.timeout.connect(self._refresh_ports)
        self._port_timer.start(3000)

    # ── UART ─────────────────────────────────────────────────────────────
    def _build_uart_group(self):
        grp = QGroupBox("UART — FPGA")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(6, 14, 6, 6)
        lay.setSpacing(5)
        lay.addWidget(_section_label("PORT"))

        row = QHBoxLayout()
        row.setSpacing(4)
        self.uart_port_combo = QComboBox()
        self.uart_port_combo.setEditable(True)
        self.uart_port_combo.setInsertPolicy(QComboBox.NoInsert)
        self.uart_port_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.uart_port_combo.setToolTip(
            "Serial COM port connected to the FPGA board.\n"
            "Refreshes every 3 s automatically.\n"
            "Select or type any COM port.\n"
            "Baud: 115200  |  RTS/CTS hardware flow control.")
        self._refresh_ports()
        self.uart_refresh_btn = QPushButton("⟳")
        self.uart_refresh_btn.setFixedWidth(sc(28))
        self.uart_refresh_btn.setToolTip("Refresh COM port list")
        self.uart_refresh_btn.clicked.connect(self._refresh_ports)
        row.addWidget(self.uart_port_combo)
        row.addWidget(self.uart_refresh_btn)
        lay.addLayout(row)

        baud_row = QHBoxLayout()
        baud_row.addWidget(QLabel("Baud:"))
        bl = QLabel("115200 RTS/CTS")
        bl.setStyleSheet("font-size: 10px; color: #00D4FF;")
        baud_row.addWidget(bl)
        baud_row.addStretch()
        lay.addLayout(baud_row)

        sr = QHBoxLayout()
        sr.setSpacing(4)
        self.uart_dot = _dot()
        self.uart_status_lbl = QLabel("UART disconnected")
        self.uart_status_lbl.setStyleSheet("color:#8B949E; font-size:10px;")
        self.uart_status_lbl.setWordWrap(True)
        self.uart_status_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sr.addWidget(self.uart_dot)
        sr.addWidget(self.uart_status_lbl)
        lay.addLayout(sr)

        self.uart_btn = QPushButton("Connect UART")
        self.uart_btn.setObjectName("btn_primary")
        self.uart_btn.setToolTip("Open COM port. Use Loopback tab to verify link.")
        self.uart_btn.clicked.connect(self._toggle_uart)
        lay.addWidget(self.uart_btn)
        return grp

    def _refresh_ports(self):
        current = self.uart_port_combo.currentText().strip()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        choices = []
        for port in ([current] if current else []) + ports:
            if port and port not in choices:
                choices.append(port)

        self.uart_port_combo.blockSignals(True)
        self.uart_port_combo.clear()
        self.uart_port_combo.addItems(choices)
        if current:
            self.uart_port_combo.setCurrentText(current)
        elif "COM9" in choices:
            self.uart_port_combo.setCurrentText("COM9")
        elif choices:
            self.uart_port_combo.setCurrentText(choices[0])
        self.uart_port_combo.blockSignals(False)

        if hasattr(self, "uart_status_lbl"):
            actual = uart.is_connected()
            if self._uart_ok and not actual:
                self._set_uart_status(False, "UART disconnected")
            elif actual and not self._uart_ok:
                self._set_uart_status(True, self._uart_label())

    def _toggle_uart(self):
        if not self._uart_ok:
            port = self.uart_port_combo.currentText().strip()
            if not port:
                self._set_uart_status(False, "No UART port")
                return
            ok = uart.connect(port, baud=115200, timeout=2.0, rtscts=True)
            if ok:
                self._set_uart_status(True, f"{port} @ 115200 RTS/CTS")
                tx_log, _ = init_session()
                self.log_path_lbl.setText(os.path.basename(tx_log))
            else:
                self._set_uart_status(False, uart.get_last_error() or "UART failed")
        else:
            uart.disconnect()
            self._set_uart_status(False, "UART disconnected")

    def _uart_label(self):
        info = uart.get_connection_info()
        flow = "RTS/CTS" if info.get("rtscts") else "no flow"
        return f"{info.get('port', 'UART')} @ {info.get('baud', 115200)} {flow}"

    def _set_uart_status(self, ok, label=""):
        self._uart_ok = ok
        c = "#3FB950" if ok else "#F85149"
        self.uart_dot.setStyleSheet(f"color:{c}; font-size:13px;")
        self.uart_status_lbl.setText(label)
        self.uart_status_lbl.setToolTip(label)
        self.uart_btn.setText("Disconnect UART" if ok else "Connect UART")
        self.uart_btn.setEnabled(True)
        self.uart_port_combo.setEnabled(not ok)
        self.uart_connected.emit(ok)

    # ── SMU ──────────────────────────────────────────────────────────────
    def _build_smu_group(self):
        grp = QGroupBox("SMU — 2602B")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(6, 14, 6, 6)
        lay.setSpacing(5)
        lay.addWidget(_section_label("VISA ADDRESS"))
        self.smu_visa_edit = QLineEdit("USB0::0x05E6::0x2602::INSTR")
        self.smu_visa_edit.setToolTip(
            "VISA address of the Keithley 2602B SMU.\n"
            "Format: USB0::VID::PID::SERIAL::INSTR")
        lay.addWidget(self.smu_visa_edit)
        sr = QHBoxLayout()
        sr.setSpacing(4)
        self.smu_dot = _dot()
        self.smu_status_lbl = QLabel("SMU disconnected")
        self.smu_status_lbl.setStyleSheet("color:#8B949E; font-size:10px;")
        self.smu_status_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sr.addWidget(self.smu_dot)
        sr.addWidget(self.smu_status_lbl)
        lay.addLayout(sr)
        self.smu_btn = QPushButton("Connect SMU")
        self.smu_btn.setToolTip("Connect to SMU via PyVISA over USB")
        self.smu_btn.clicked.connect(self._toggle_smu)
        lay.addWidget(self.smu_btn)
        return grp

    def _toggle_smu(self):
        if not self._smu_ok:
            ok = smu.connect(self.smu_visa_edit.text().strip())
            self._set_smu_status(ok, "SMU connected" if ok else "SMU failed")
        else:
            smu.disconnect()
            self._set_smu_status(False, "SMU disconnected")

    def _set_smu_status(self, ok, label=""):
        self._smu_ok = ok
        c = "#3FB950" if ok else "#F85149"
        self.smu_dot.setStyleSheet(f"color:{c}; font-size:13px;")
        self.smu_status_lbl.setText(label)
        self.smu_btn.setText("Disconnect SMU" if ok else "Connect SMU")
        self.smu_connected.emit(ok)

    # ── PSU ──────────────────────────────────────────────────────────────
    def _build_psu_group(self):
        grp = QGroupBox("PSU — 2230G")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(6, 14, 6, 6)
        lay.setSpacing(5)
        lay.addWidget(_section_label("VISA ADDRESS"))
        self.psu_visa_edit = QLineEdit("USB0::0x05E6::0x2230::INSTR")
        self.psu_visa_edit.setToolTip(
            "VISA address of the Keithley 2230G-30-1 PSU.\n"
            "3 channels: CH1/CH2 (0-30 V), CH3 (0-6 V).")
        lay.addWidget(self.psu_visa_edit)
        sr = QHBoxLayout()
        sr.setSpacing(4)
        self.psu_dot = _dot()
        self.psu_status_lbl = QLabel("PSU disconnected")
        self.psu_status_lbl.setStyleSheet("color:#8B949E; font-size:10px;")
        self.psu_status_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sr.addWidget(self.psu_dot)
        sr.addWidget(self.psu_status_lbl)
        lay.addLayout(sr)
        self.psu_btn = QPushButton("Connect PSU")
        self.psu_btn.setToolTip("Connect to PSU via PyVISA over USB")
        self.psu_btn.clicked.connect(self._toggle_psu)
        lay.addWidget(self.psu_btn)
        return grp

    def _toggle_psu(self):
        if not self._psu_ok:
            ok = psu.connect(self.psu_visa_edit.text().strip())
            self._set_psu_status(ok, "PSU connected" if ok else "PSU failed")
        else:
            psu.disconnect()
            self._set_psu_status(False, "PSU disconnected")

    def _set_psu_status(self, ok, label=""):
        self._psu_ok = ok
        c = "#3FB950" if ok else "#F85149"
        self.psu_dot.setStyleSheet(f"color:{c}; font-size:13px;")
        self.psu_status_lbl.setText(label)
        self.psu_btn.setText("Disconnect PSU" if ok else "Connect PSU")
        self.psu_connected.emit(ok)

    # ── Session ───────────────────────────────────────────────────────────
    def _build_session_group(self):
        grp = QGroupBox("Session")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(6, 14, 6, 6)
        lay.setSpacing(5)
        lay.addWidget(_section_label("LOG FILE"))
        self.log_path_lbl = QLabel("—")
        self.log_path_lbl.setWordWrap(True)
        self.log_path_lbl.setStyleSheet("font-size:9px; color:#8B949E;")
        lay.addWidget(self.log_path_lbl)
        self.new_session_btn = QPushButton("New Session")
        self.new_session_btn.setToolTip(
            "Create new timestamped CSV files.\n"
            "Previous files are kept on disk.")
        self.new_session_btn.clicked.connect(self._new_session)
        lay.addWidget(self.new_session_btn)
        self.open_folder_btn = QPushButton("Open Log Folder")
        self.open_folder_btn.setToolTip("Open the sessions/ folder in explorer")
        self.open_folder_btn.clicked.connect(self._open_folder)
        lay.addWidget(self.open_folder_btn)
        return grp

    def _new_session(self):
        init_session()
        p = get_session_log_path() or "—"
        self.log_path_lbl.setText(os.path.basename(p))

    def _open_folder(self):
        import subprocess, platform
        folder = os.path.abspath("sessions")
        os.makedirs(folder, exist_ok=True)
        if platform.system() == "Windows":
            os.startfile(folder)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
