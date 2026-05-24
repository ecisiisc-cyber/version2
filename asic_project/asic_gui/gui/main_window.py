# gui/main_window.py
# Main QMainWindow: toolbar, nested tabs, settings panel, log dock.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtCore    import Qt, pyqtSlot, QSize
from PyQt5.QtGui     import QIcon, QFont
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QTabWidget,
    QToolBar, QAction, QStatusBar, QLabel, QSplitter,
    QApplication, QMessageBox,
)
from gui.scale import sc

from gui.settings_panel import SettingsPanel
from gui.log_panel      import LogPanel
from style.theme        import get_theme

# Link & Config tabs
from gui.tabs.link_config.loopback_tab    import LoopbackTab
from gui.tabs.link_config.chip_config_tab import ChipConfigTab
from gui.tabs.link_config.raw_uart_tab    import RawUartTab

# Signal tabs
from gui.tabs.signal.level_setting_tab import LevelSettingTab
from gui.tabs.signal.awg_tab           import AWGTab
from gui.tabs.signal.clock_ber_tab     import ClockBERTab
from gui.tabs.signal.ber_shmoo_tab     import BERShmooTab
from gui.tabs.signal.dut_shmoo_tab     import DUTShmooTab
from gui.tabs.signal.adc_tab           import ADCTab

# Power tabs
from gui.tabs.power.pmic_tab import PMICTab
from gui.tabs.power.smu_tab  import SMUTab
from gui.tabs.power.psu_tab  import PSUTab


def _dot_label(color, text):
    lbl = QLabel(f"● {text}")
    lbl.setStyleSheet(f"color: {color}; font-size: 11px; padding: 0 8px;")
    return lbl


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASIC Characterization Tool")
        # Minimum size: 75% of screen width x 65% of screen height
        screen = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(
            max(900, int(screen.width()  * 0.60)),
            max(600, int(screen.height() * 0.65)),
        )
        self.resize(
            int(screen.width()  * 0.80),
            int(screen.height() * 0.85),
        )
        self._current_theme = "light"
        self._plot_window   = None

        self._build_toolbar()
        self._build_central()
        self._build_log_dock()
        self._build_status_bar()
        self._wire_signals()

    # ── Toolbar ───────────────────────────────────────────────────────────
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)

        title_lbl = QLabel("  ASIC CHAR TOOL  ")
        title_lbl.setStyleSheet(
            "font-weight: 800; font-size: 13px; "
            "color: #00D4FF; letter-spacing: 2px;")
        tb.addWidget(title_lbl)
        tb.addSeparator()

        self._theme_action = QAction("🌙  Dark", self)
        self._theme_action.setToolTip("Toggle between dark and light theme")
        self._theme_action.triggered.connect(self._toggle_theme)
        tb.addAction(self._theme_action)

        tb.addSeparator()

        self._plot_action = QAction("📈  Plot Viewer", self)
        self._plot_action.setToolTip(
            "Open the shmoo / characterization plot viewer.\n"
            "Loads char_data CSV and generates:\n"
            "  • Pass/Fail shmoo\n"
            "  • Power shmoo\n"
            "  • Energy shmoo"
        )
        self._plot_action.triggered.connect(self._open_plot_window)
        tb.addAction(self._plot_action)

        tb.addSeparator()

        self._log_action = QAction("📋  Log Panel", self)
        self._log_action.setToolTip("Toggle the TX/RX log panel at the bottom")
        self._log_action.triggered.connect(self._toggle_log)
        tb.addAction(self._log_action)

    # ── Central widget ────────────────────────────────────────────────────
    def _build_central(self):
        central = QWidget()
        outer   = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Settings panel (left)
        self.settings = SettingsPanel()
        outer.addWidget(self.settings)

        # Vertical divider
        div = QWidget()
        div.setFixedWidth(sc(1))
        div.setStyleSheet("background-color: #21262D;")
        outer.addWidget(div)

        # Nested tab structure
        self._main_tabs = QTabWidget()
        self._main_tabs.setTabPosition(QTabWidget.North)

        # ── Link & Config ──────────────────────────────────────────────────
        lc_tabs = QTabWidget()
        self.loopback_tab    = LoopbackTab()
        self.chip_config_tab = ChipConfigTab()
        self.raw_uart_tab    = RawUartTab()
        lc_tabs.addTab(self.loopback_tab,    "Loopback")
        lc_tabs.addTab(self.chip_config_tab, "Chip Config")
        lc_tabs.addTab(self.raw_uart_tab,    "Raw UART")
        self._main_tabs.addTab(lc_tabs, "🔗  Link & Config")

        # ── Signal ─────────────────────────────────────────────────────────
        sig_tabs = QTabWidget()
        self.level_setting_tab = LevelSettingTab()
        self.awg_tab           = AWGTab()
        self.clock_ber_tab     = ClockBERTab()
        self.ber_shmoo_tab     = BERShmooTab()
        self.dut_shmoo_tab     = DUTShmooTab()
        self.adc_tab           = ADCTab()
        sig_tabs.addTab(self.level_setting_tab, "DAC")
        sig_tabs.addTab(self.awg_tab,           "AWG")
        sig_tabs.addTab(self.clock_ber_tab,     "Clock + BER")
        sig_tabs.addTab(self.ber_shmoo_tab,     "BER Shmoo")
        sig_tabs.addTab(self.dut_shmoo_tab,     "DUT Shmoo")
        sig_tabs.addTab(self.adc_tab,           "ADC")
        self._main_tabs.addTab(sig_tabs, "📡  Signal")

        # ── Power ──────────────────────────────────────────────────────────
        pwr_tabs = QTabWidget()
        self.pmic_tab = PMICTab()
        self.smu_tab  = SMUTab()
        self.psu_tab  = PSUTab()
        pwr_tabs.addTab(self.pmic_tab, "PMIC")
        pwr_tabs.addTab(self.smu_tab,  "SMU 2602B")
        pwr_tabs.addTab(self.psu_tab,  "PSU 2230G")
        self._main_tabs.addTab(pwr_tabs, "⚡  Power")

        outer.addWidget(self._main_tabs, stretch=1)
        self.setCentralWidget(central)

    # ── Log dock ──────────────────────────────────────────────────────────
    def _build_log_dock(self):
        self.log_panel = LogPanel(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_panel)
        self.log_panel.hide()  # hidden by default, toggled via toolbar

    # ── Status bar ────────────────────────────────────────────────────────
    def _build_status_bar(self):
        sb = self.statusBar()
        self._sb_uart = _dot_label("#30363D", "UART: —")
        self._sb_smu  = _dot_label("#30363D", "SMU: —")
        self._sb_psu  = _dot_label("#30363D", "PSU: —")
        for w in [self._sb_uart, self._sb_smu, self._sb_psu]:
            sb.addWidget(w)
        sb.addPermanentWidget(QLabel("ASIC Char Tool v1.0  "))

    # ── Signal wiring ─────────────────────────────────────────────────────
    def _wire_signals(self):
        # Settings → status bar
        self.settings.uart_connected.connect(self._on_uart_state)
        self.settings.smu_connected.connect(self._on_smu_state)
        self.settings.psu_connected.connect(self._on_psu_state)

        # All tabs → log panel
        log_tabs = [
            self.loopback_tab, self.chip_config_tab, self.raw_uart_tab,
            self.level_setting_tab, self.awg_tab, self.clock_ber_tab,
            self.ber_shmoo_tab, self.dut_shmoo_tab, self.adc_tab, self.pmic_tab,
        ]
        for tab in log_tabs:
            tab.log_signal.connect(self.log_panel.append)

    # ── Slots ─────────────────────────────────────────────────────────────
    @pyqtSlot(bool)
    def _on_uart_state(self, ok):
        c = "#3FB950" if ok else "#F85149"
        t = "UART: Connected" if ok else "UART: —"
        self._sb_uart.setText(f"● {t}")
        self._sb_uart.setStyleSheet(
            f"color: {c}; font-size: 11px; padding: 0 8px;")

    @pyqtSlot(bool)
    def _on_smu_state(self, ok):
        c = "#3FB950" if ok else "#F85149"
        t = "SMU: Connected" if ok else "SMU: —"
        self._sb_smu.setText(f"● {t}")
        self._sb_smu.setStyleSheet(
            f"color: {c}; font-size: 11px; padding: 0 8px;")

    @pyqtSlot(bool)
    def _on_psu_state(self, ok):
        c = "#3FB950" if ok else "#F85149"
        t = "PSU: Connected" if ok else "PSU: —"
        self._sb_psu.setText(f"● {t}")
        self._sb_psu.setStyleSheet(
            f"color: {c}; font-size: 11px; padding: 0 8px;")

    def _toggle_theme(self):
        self._current_theme = (
            "light" if self._current_theme == "dark" else "dark")
        QApplication.instance().setStyleSheet(
            get_theme(self._current_theme))
        icon = "🌙  Dark" if self._current_theme == "light" else "☀  Light"
        self._theme_action.setText(icon)
        # Propagate to embedded plots
        for tab in [self.level_setting_tab, self.clock_ber_tab,
                    self.ber_shmoo_tab, self.dut_shmoo_tab]:
            tab.set_theme(self._current_theme)

    def _toggle_log(self):
        if self.log_panel.isVisible():
            self.log_panel.hide()
        else:
            self.log_panel.show()

    def _open_plot_window(self):
        # Lazy import to avoid circular deps
        from gui.graph_window import GraphWindow
        if self._plot_window is None or not self._plot_window.isVisible():
            self._plot_window = GraphWindow(self._current_theme)
            self._plot_window.show()
        else:
            self._plot_window.raise_()
            self._plot_window.activateWindow()

    def closeEvent(self, event):
        import peripherals.uart_handler as uart
        import instruments.smu_2602b   as smu
        import instruments.psu_2230g   as psu
        uart.disconnect()
        smu.disconnect()
        psu.disconnect()
        event.accept()
