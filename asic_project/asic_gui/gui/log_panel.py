# gui/log_panel.py
# Bottom dockable TX/RX log panel.
# Colour-coded rows: TX=blue, RX=green, ERROR=red.
# Circular buffer: max 1000 rows.

import datetime
from PyQt5.QtCore    import Qt, pyqtSlot
from PyQt5.QtGui     import QColor, QFont
from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractScrollArea, QFileDialog,
)
from gui.scale import sc

MAX_ROWS = 1000

# Colours (dark theme defaults; light theme overrides via stylesheet)
COL_TX    = QColor("#1C2D3F")
COL_RX    = QColor("#1A2E1A")
COL_ERROR = QColor("#2D1B1B")
COL_TEXT  = QColor("#E6EDF3")


class LogPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("TX / RX Log", parent)
        self.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable |
            QDockWidget.DockWidgetMovable  |
            QDockWidget.DockWidgetFloatable
        )
        self._paused = False
        self._row_count = 0

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # ── Toolbar ───────────────────────────────────────────────────────
        bar = QHBoxLayout()
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setFixedWidth(sc(90))
        self.pause_btn.setToolTip("Pause/resume auto-scroll to latest entry")
        self.pause_btn.clicked.connect(self._toggle_pause)

        clear_btn = QPushButton("✕ Clear")
        clear_btn.setFixedWidth(sc(80))
        clear_btn.setToolTip("Clear all log entries from view (does not delete CSV)")
        clear_btn.clicked.connect(self._clear)

        export_btn = QPushButton("↓ Export")
        export_btn.setFixedWidth(sc(90))
        export_btn.setToolTip("Export visible log to a CSV file")
        export_btn.clicked.connect(self._export)

        bar.addWidget(self.pause_btn)
        bar.addWidget(clear_btn)
        bar.addWidget(export_btn)
        bar.addStretch()
        lay.addLayout(bar)

        # ── Table ─────────────────────────────────────────────────────────
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Timestamp", "Dir", "Peripheral", "Raw Hex", "Parsed", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch)
        for col, w in [(0, 160), (1, 40), (2, 110), (5, 70)]:
            self.table.setColumnWidth(col, w)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        lay.addWidget(self.table)

        self.setWidget(container)
        self.setMinimumHeight(sc(150))

    # ── Public API ─────────────────────────────────────────────────────────
    @pyqtSlot(str, str, bytes, str, str)
    def append(self, direction, peripheral, raw_bytes, parsed, status):
        """Add one log row. Called from any thread via signal."""
        if self._paused:
            return

        # Circular buffer: drop oldest if full
        if self.table.rowCount() >= MAX_ROWS:
            self.table.removeRow(0)

        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        hex_str = raw_bytes.hex(" ").upper() if raw_bytes else ""

        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, val in enumerate(
                [ts, direction, peripheral, hex_str, parsed, status]):
            item = QTableWidgetItem(str(val))
            item.setForeground(COL_TEXT)
            self.table.setItem(row, col, item)

        # Row background
        if direction == "TX":
            bg = COL_TX
        elif status in ("error", "invalid", "timeout", "mismatch"):
            bg = COL_ERROR
        else:
            bg = COL_RX

        for col in range(6):
            self.table.item(row, col).setBackground(bg)

        self.table.scrollToBottom()

    # ── Slots ──────────────────────────────────────────────────────────────
    def _toggle_pause(self):
        self._paused = not self._paused
        self.pause_btn.setText("▶ Resume" if self._paused else "⏸ Pause")

    def _clear(self):
        self.table.setRowCount(0)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Log", "log_export.csv", "CSV Files (*.csv)")
        if not path:
            return
        import csv
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["Timestamp", "Dir", "Peripheral",
                 "Raw Hex", "Parsed", "Status"])
            for row in range(self.table.rowCount()):
                writer.writerow(
                    [self.table.item(row, col).text()
                     for col in range(6)])
