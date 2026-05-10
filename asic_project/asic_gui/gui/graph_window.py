# gui/graph_window.py
# Separate plot window for shmoo and characterization plots.
# Launched from toolbar. Loads char_data CSV.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np

from PyQt5.QtCore    import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QFileDialog,
    QGroupBox, QCheckBox, QSizePolicy,
)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavToolbar,
)

from style.theme import get_matplotlib_style, get_theme

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False


def _load(path):
    if not PANDAS_OK:
        return None
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def _shmoo_axes(df):
    freqs = sorted(df["frequency_hz"].unique())
    volts = sorted(df["voltage_v"].unique())
    return freqs, volts


class PlotTab(QWidget):
    """Base class: matplotlib figure + nav toolbar + load button."""

    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self._theme = theme
        self._df    = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Top bar
        bar = QHBoxLayout()
        self.load_btn = QPushButton("📂  Load CSV")
        self.load_btn.setToolTip(
            "Load a characterization data CSV file.\n"
            "Expected columns: voltage_v, frequency_hz, pass_fail,\n"
            "power_w, energy_j, ber, timestamp"
        )
        self.load_btn.clicked.connect(self._load_csv)
        self.file_lbl = QLabel("No file loaded")
        self.file_lbl.setStyleSheet("color: #8B949E; font-size: 11px;")
        bar.addWidget(self.load_btn)
        bar.addWidget(self.file_lbl)
        bar.addStretch()
        self._add_bar_extras(bar)
        root.addLayout(bar)

        # Figure
        self._fig    = Figure(figsize=(10, 6), tight_layout=True)
        self._ax     = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._nav    = NavToolbar(self._canvas, self)
        root.addWidget(self._nav)
        root.addWidget(self._canvas)

        self._init_plot()

    def _add_bar_extras(self, bar):
        """Subclasses add extra controls to the top bar here."""
        pass

    def _load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Characterization CSV", "sessions",
            "CSV Files (*.csv)")
        if not path:
            return
        df = _load(path)
        if df is None:
            self.file_lbl.setText("pandas not installed")
            return
        self._df = df
        self.file_lbl.setText(os.path.basename(path))
        self._plot()

    def _apply_theme(self):
        rc = get_matplotlib_style(self._theme)
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
        self._ax.set_title("Load a CSV file to plot")
        self._canvas.draw_idle()

    def _plot(self):
        pass  # override in subclass

    def set_theme(self, theme):
        self._theme = theme
        if self._df is not None:
            self._plot()
        else:
            self._init_plot()


# ── Pass/Fail Shmoo ───────────────────────────────────────────────────────────
class PassFailShmooTab(PlotTab):
    def _plot(self):
        if self._df is None:
            return
        df = self._df
        if not all(c in df.columns for c in
                   ["voltage_v", "frequency_hz", "pass_fail"]):
            self.file_lbl.setText("Missing required columns")
            return

        freqs, volts = _shmoo_axes(df)
        grid = np.full((len(volts), len(freqs)), np.nan)
        for _, row in df.iterrows():
            try:
                vi = volts.index(row["voltage_v"])
                fi = freqs.index(row["frequency_hz"])
                pf = str(row["pass_fail"]).strip().lower()
                grid[vi, fi] = 1.0 if pf in ("pass","1","true") else 0.0
            except Exception:
                pass

        self._ax.clear()
        self._apply_theme()
        cmap = mcolors.ListedColormap(["#F85149", "#3FB950"])
        norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5], cmap.N)
        im = self._ax.imshow(
            grid, aspect="auto", origin="lower", cmap=cmap, norm=norm,
            extent=[-0.5, len(freqs)-0.5, -0.5, len(volts)-0.5])
        self._ax.set_xticks(range(len(freqs)))
        self._ax.set_xticklabels(
            [f"{f/1e6:.2f}" for f in freqs], rotation=45, ha="right", fontsize=8)
        self._ax.set_yticks(range(len(volts)))
        self._ax.set_yticklabels([f"{v:.3f}" for v in volts], fontsize=8)
        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("Core Voltage (V)")
        self._ax.set_title("Pass / Fail Shmoo Plot")
        cbar = self._fig.colorbar(im, ax=self._ax, ticks=[0, 1])
        cbar.ax.set_yticklabels(["Fail", "Pass"])
        # Cell annotations
        rc = get_matplotlib_style(self._theme)
        for vi in range(len(volts)):
            for fi in range(len(freqs)):
                v = grid[vi, fi]
                if not np.isnan(v):
                    self._ax.text(fi, vi, "P" if v==1 else "F",
                                  ha="center", va="center",
                                  fontsize=7, color="white", fontweight="bold")
        self._canvas.draw_idle()


# ── Power Shmoo ───────────────────────────────────────────────────────────────
class PowerShmooTab(PlotTab):
    def _plot(self):
        self._plot_heatmap("power_w", "Power (W)", "viridis", "Power Shmoo")

    def _plot_heatmap(self, col, cbar_label, cmap, title):
        if self._df is None:
            return
        df = self._df
        if col not in df.columns:
            self.file_lbl.setText(f"Column '{col}' not found")
            return
        freqs, volts = _shmoo_axes(df)
        grid = np.full((len(volts), len(freqs)), np.nan)
        for _, row in df.iterrows():
            try:
                vi = volts.index(row["voltage_v"])
                fi = freqs.index(row["frequency_hz"])
                grid[vi, fi] = float(row[col])
            except Exception:
                pass
        self._ax.clear()
        self._apply_theme()
        im = self._ax.imshow(
            grid, aspect="auto", origin="lower", cmap=cmap,
            extent=[-0.5, len(freqs)-0.5, -0.5, len(volts)-0.5])
        self._ax.set_xticks(range(len(freqs)))
        self._ax.set_xticklabels(
            [f"{f/1e6:.2f}" for f in freqs], rotation=45, ha="right", fontsize=8)
        self._ax.set_yticks(range(len(volts)))
        self._ax.set_yticklabels([f"{v:.3f}" for v in volts], fontsize=8)
        self._ax.set_xlabel("Frequency (MHz)")
        self._ax.set_ylabel("Core Voltage (V)")
        self._ax.set_title(title)
        cbar = self._fig.colorbar(im, ax=self._ax)
        cbar.set_label(cbar_label)
        rc = get_matplotlib_style(self._theme)
        for vi in range(len(volts)):
            for fi in range(len(freqs)):
                v = grid[vi, fi]
                if not np.isnan(v):
                    self._ax.text(fi, vi, f"{v:.3f}",
                                  ha="center", va="center",
                                  fontsize=6, color="white")
        self._canvas.draw_idle()


class EnergyShmooTab(PowerShmooTab):
    def _plot(self):
        self._plot_heatmap("energy_j", "Energy (J)", "plasma", "Energy Shmoo")


# ── Graph window ──────────────────────────────────────────────────────────────
class GraphWindow(QMainWindow):
    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plot Viewer — Characterization Data")
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(
            max(800, int(screen.width()  * 0.50)),
            max(550, int(screen.height() * 0.60)),
        )
        self.resize(
            int(screen.width()  * 0.65),
            int(screen.height() * 0.75),
        )
        self._theme = theme

        tabs = QTabWidget()
        self._pf_tab  = PassFailShmooTab(theme)
        self._pw_tab  = PowerShmooTab(theme)
        self._en_tab  = EnergyShmooTab(theme)

        tabs.addTab(self._pf_tab, "Pass / Fail Shmoo")
        tabs.addTab(self._pw_tab, "Power Shmoo")
        tabs.addTab(self._en_tab, "Energy Shmoo")
        self.setCentralWidget(tabs)
        self.setStyleSheet(get_theme(theme))

    def set_theme(self, theme):
        self._theme = theme
        self.setStyleSheet(get_theme(theme))
        for t in [self._pf_tab, self._pw_tab, self._en_tab]:
            t.set_theme(theme)
