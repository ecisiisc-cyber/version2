#!/usr/bin/env python3
"""
main_gui.py — ASIC Characterization GUI Entry Point
=====================================================
Run from the project root (parent of both asic_auto/ and asic_gui/):

    python asic_gui/main_gui.py

The characterization package (asic_auto/) must be on the path.
This script adds it automatically.
"""

import sys
import os

# ── Path setup ────────────────────────────────────────────────────────────────
# Allow imports from both asic_gui/ and asic_auto/ (the char package)
_HERE     = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)            # parent dir (project root)
_CHAR_PKG = os.path.join(_PKG_ROOT, "asic_auto")  # characterization package

for p in [_HERE, _PKG_ROOT, _CHAR_PKG]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Qt DPI scaling (must be set before QApplication) ─────────────────────────
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt5.QtCore    import Qt, QCoreApplication
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui     import QFont

# Enable DPI-aware scaling for FHD / 2K / 4K screens
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,   True)

from style.theme     import get_theme, build_scaled_theme
from gui.scale       import init_scale, font_size
from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ASIC Char Tool")
    app.setOrganizationName("Lab")

    # ── Initialise DPI scale factor AFTER app is created ─────────────────
    init_scale(app)

    # ── Base font: size adapts to DPI ─────────────────────────────────────
    base_pt = font_size(9)
    font = QFont()
    from PyQt5.QtGui import QFontDatabase
    available = QFontDatabase().families()
    for family in ["JetBrains Mono", "Consolas", "Courier New"]:
        if family in available:
            font.setFamily(family)
            break
    else:
        font.setStyleHint(QFont.Monospace)
    font.setPointSize(base_pt)
    app.setFont(font)

    # ── Theme with DPI-scaled font sizes ──────────────────────────────────
    app.setStyleSheet(build_scaled_theme("light"))

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
