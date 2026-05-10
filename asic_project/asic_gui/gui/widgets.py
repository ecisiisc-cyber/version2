# gui/widgets.py
# Reusable widget helpers shared by all tab modules.

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtGui     import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QSizePolicy,
)
from gui.scale import sc


# ── Status indicator (dot + label) ────────────────────────────────────────
class StatusIndicator(QWidget):
    """Coloured dot + text label. Call set_state() to update."""

    STATES = {
        "ok":           ("#3FB950", "OK"),
        "error":        ("#F85149", "Error"),
        "warning":      ("#D29922", "Warning"),
        "idle":         ("#8B949E", "Idle"),
        "busy":         ("#00D4FF", "Busy…"),
        "disconnected": ("#30363D", "—"),
        # Custom states for chip config
        "success":      ("#3FB950", "Config Success"),
        "failed":       ("#F85149", "Config Failed"),
        "configuring":  ("#00D4FF", "Configuring…"),
        "unconfigured": ("#8B949E", "Unconfigured"),
    }

    def __init__(self, initial="idle", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("font-size: 14px;")
        self._lbl = QLabel("—")
        lay.addWidget(self._dot)
        lay.addWidget(self._lbl)
        lay.addStretch()
        self.set_state(initial)

    def set_state(self, state, custom_label=None):
        color, default_label = self.STATES.get(state, ("#8B949E", state))
        label = custom_label if custom_label is not None else default_label
        self._dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        self._lbl.setText(label)

    def set_custom(self, color, label):
        self._dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        self._lbl.setText(label)


# ── Hex display field ──────────────────────────────────────────────────────
class HexDisplay(QWidget):
    """Read-only labelled hex display for TX / RX bytes."""

    def __init__(self, label="TX", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lbl = QLabel(label + ":")
        lbl.setFixedWidth(sc(28))
        lbl.setObjectName("label_section")
        self._value = QLabel("—")
        self._value.setObjectName("label_value")
        self._value.setWordWrap(True)
        self._value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._value.setToolTip("Raw bytes sent/received — click to select all")
        lay.addWidget(lbl)
        lay.addWidget(self._value)

    def set_bytes(self, data: bytes):
        if data:
            self._value.setText(data.hex(" ").upper())
        else:
            self._value.setText("—")

    def set_text(self, text: str):
        self._value.setText(text)


# ── Value display (number + unit) ─────────────────────────────────────────
class ValueDisplay(QWidget):
    """Displays a numeric value with unit, styled as a metric readout."""

    def __init__(self, label, unit="", width=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(label + ":")
        lbl.setObjectName("label_section")
        if width:
            lbl.setFixedWidth(width)
        self._val = QLabel("—")
        self._val.setObjectName("label_value")
        self._val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._unit = QLabel(unit)
        self._unit.setStyleSheet("color: #8B949E;")
        lay.addWidget(lbl)
        lay.addWidget(self._val)
        lay.addWidget(self._unit)
        lay.addStretch()

    def set_value(self, v, fmt="{:.4f}"):
        if v is None:
            self._val.setText("—")
        else:
            try:
                self._val.setText(fmt.format(v))
            except Exception:
                self._val.setText(str(v))

    def set_error(self):
        self._val.setText("ERR")
        self._val.setObjectName("label_error")
        self._val.style().unpolish(self._val)
        self._val.style().polish(self._val)


# ── Voltage bar (ADC channel display) ─────────────────────────────────────
class VoltageBar(QWidget):
    """Horizontal progress bar showing ADC voltage (0–2500 mV)."""

    def __init__(self, channel_num, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lbl = QLabel(f"CH{channel_num}")
        lbl.setFixedWidth(sc(30))
        lbl.setObjectName("label_section")

        self._bar = QProgressBar()
        self._bar.setRange(0, 2500)
        self._bar.setValue(0)
        self._bar.setFixedHeight(sc(16))
        self._bar.setTextVisible(False)

        self._val_lbl = QLabel("  — mV")
        self._val_lbl.setObjectName("label_value")
        self._val_lbl.setFixedWidth(sc(90))

        lay.addWidget(lbl)
        lay.addWidget(self._bar)
        lay.addWidget(self._val_lbl)

    def set_voltage(self, mv):
        if mv is None:
            self._bar.setValue(0)
            self._val_lbl.setText("  — mV")
        else:
            self._bar.setValue(int(min(2500, max(0, mv))))
            self._val_lbl.setText(f"{mv:7.1f} mV")


# ── Result box (TX/RX + status below any form) ────────────────────────────
class ResultBox(QFrame):
    """
    Standard results section shown at the bottom of every tab's form.
    Contains TX hex, RX hex, and a status indicator.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setSpacing(4)
        self.tx = HexDisplay("TX")
        self.rx = HexDisplay("RX")
        self.status = StatusIndicator("idle")
        lay.addWidget(self.tx)
        lay.addWidget(self.rx)
        lay.addWidget(self.status)

    def update(self, result: dict):
        """Feed a peripheral result dict to auto-populate."""
        self.tx.set_bytes(result.get("tx", b""))
        self.rx.set_bytes(result.get("rx", b""))
        s = result.get("status", "idle")
        self.status.set_state(s if s in StatusIndicator.STATES else "idle",
                              custom_label=s)

    def set_busy(self):
        self.status.set_state("busy")
        self.tx.set_text("Sending…")
        self.rx.set_text("Waiting…")
