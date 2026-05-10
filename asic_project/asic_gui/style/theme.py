# style/theme.py
# Dark and light QSS themes for the ASIC characterization GUI.
# Designed for FHD / 2K / 4K screens with DPI-aware scaling.
# Color palette: deep navy dark mode, clean off-white light mode.
# Accent: electric cyan (#00D4FF) — inspired by oscilloscope traces.

DARK = """
/* ── Global ─────────────────────────────────────────────────── */
QWidget {
    background-color: #0D1117;
    color: #E6EDF3;
    font-family: "JetBrains Mono", "Consolas", "Courier New", monospace;
    font-size: 12px;
}
QMainWindow {
    background-color: #0D1117;
}

/* ── GroupBox ────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #30363D;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
    font-weight: 600;
    color: #8B949E;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #00D4FF;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
}

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {
    background-color: #161B22;
    color: #E6EDF3;
    border: 1px solid #30363D;
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #1F2937;
    border-color: #00D4FF;
    color: #00D4FF;
}
QPushButton:pressed {
    background-color: #00D4FF;
    color: #0D1117;
    border-color: #00D4FF;
}
QPushButton:disabled {
    background-color: #0D1117;
    color: #30363D;
    border-color: #21262D;
}
QPushButton#btn_primary {
    background-color: #00D4FF;
    color: #0D1117;
    border: none;
    font-weight: 700;
}
QPushButton#btn_primary:hover {
    background-color: #33DDFF;
}
QPushButton#btn_primary:pressed {
    background-color: #0099BB;
}
QPushButton#btn_danger {
    background-color: #21262D;
    color: #F85149;
    border: 1px solid #F85149;
}
QPushButton#btn_danger:hover {
    background-color: #F85149;
    color: #0D1117;
}
QPushButton#btn_success {
    background-color: #21262D;
    color: #3FB950;
    border: 1px solid #3FB950;
}
QPushButton#btn_success:hover {
    background-color: #3FB950;
    color: #0D1117;
}

/* ── LineEdit / SpinBox / ComboBox ───────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #161B22;
    color: #E6EDF3;
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #00D4FF;
    selection-color: #0D1117;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #00D4FF;
    background-color: #1C2333;
}
QLineEdit:read-only {
    background-color: #0D1117;
    color: #8B949E;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #8B949E;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #161B22;
    border: 1px solid #30363D;
    color: #E6EDF3;
    selection-background-color: #1F6FEB;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #21262D;
    border: none;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #30363D;
}

/* ── TabWidget ───────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #21262D;
    border-radius: 6px;
    background-color: #0D1117;
    top: -1px;
}
QTabBar::tab {
    background-color: #161B22;
    color: #8B949E;
    border: 1px solid #21262D;
    border-bottom: none;
    padding: 6px 14px;
    margin-right: 2px;
    border-radius: 5px 5px 0 0;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #0D1117;
    color: #00D4FF;
    border-color: #30363D;
    border-bottom: 2px solid #00D4FF;
}
QTabBar::tab:hover:!selected {
    background-color: #1C2333;
    color: #E6EDF3;
}

/* ── Table ───────────────────────────────────────────────────── */
QTableWidget {
    background-color: #0D1117;
    alternate-background-color: #161B22;
    gridline-color: #21262D;
    border: 1px solid #21262D;
    border-radius: 4px;
}
QTableWidget::item {
    padding: 4px 8px;
}
QTableWidget::item:selected {
    background-color: #1F2937;
    color: #00D4FF;
}
QHeaderView::section {
    background-color: #161B22;
    color: #8B949E;
    border: none;
    border-right: 1px solid #21262D;
    border-bottom: 1px solid #30363D;
    padding: 5px 8px;
    font-weight: 700;
    font-size: 10px;
    letter-spacing: 1px;
}

/* ── ScrollBar ───────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #0D1117;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #30363D;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #00D4FF;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #0D1117;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #30363D;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #00D4FF;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ── Labels ──────────────────────────────────────────────────── */
QLabel#label_value {
    color: #00D4FF;
    font-weight: 700;
    font-size: 13px;
}
QLabel#label_ok {
    color: #3FB950;
    font-weight: 700;
}
QLabel#label_error {
    color: #F85149;
    font-weight: 700;
}
QLabel#label_warn {
    color: #D29922;
    font-weight: 700;
}
QLabel#label_section {
    color: #8B949E;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}

/* ── RadioButton / CheckBox ──────────────────────────────────── */
QRadioButton, QCheckBox {
    color: #E6EDF3;
    spacing: 6px;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #30363D;
    border-radius: 7px;
    background-color: #161B22;
}
QCheckBox::indicator {
    border-radius: 3px;
}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background-color: #00D4FF;
    border-color: #00D4FF;
}
QRadioButton::indicator:hover, QCheckBox::indicator:hover {
    border-color: #00D4FF;
}

/* ── ProgressBar ─────────────────────────────────────────────── */
QProgressBar {
    background-color: #161B22;
    border: 1px solid #30363D;
    border-radius: 4px;
    text-align: center;
    color: #E6EDF3;
    font-size: 10px;
}
QProgressBar::chunk {
    background-color: #00D4FF;
    border-radius: 3px;
}

/* ── TextEdit ────────────────────────────────────────────────── */
QTextEdit, QPlainTextEdit {
    background-color: #0D1117;
    color: #E6EDF3;
    border: 1px solid #21262D;
    border-radius: 4px;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 11px;
}

/* ── DockWidget ──────────────────────────────────────────────── */
QDockWidget {
    color: #E6EDF3;
    font-weight: 700;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background-color: #161B22;
    padding: 5px 10px;
    border-bottom: 1px solid #30363D;
}

/* ── StatusBar ───────────────────────────────────────────────── */
QStatusBar {
    background-color: #010409;
    color: #8B949E;
    border-top: 1px solid #21262D;
    font-size: 11px;
}
QStatusBar::item {
    border: none;
}

/* ── ToolBar ─────────────────────────────────────────────────── */
QToolBar {
    background-color: #161B22;
    border-bottom: 1px solid #21262D;
    spacing: 4px;
    padding: 3px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px 8px;
    color: #8B949E;
    font-weight: 600;
}
QToolButton:hover {
    background-color: #1F2937;
    border-color: #30363D;
    color: #E6EDF3;
}
QToolButton:pressed, QToolButton:checked {
    background-color: #1C2333;
    border-color: #00D4FF;
    color: #00D4FF;
}

/* ── Splitter ────────────────────────────────────────────────── */
QSplitter::handle {
    background-color: #21262D;
}
QSplitter::handle:hover {
    background-color: #00D4FF;
}

/* ── MenuBar / Menu ──────────────────────────────────────────── */
QMenuBar {
    background-color: #161B22;
    color: #E6EDF3;
    border-bottom: 1px solid #21262D;
}
QMenuBar::item:selected {
    background-color: #1F2937;
}
QMenu {
    background-color: #161B22;
    border: 1px solid #30363D;
    color: #E6EDF3;
}
QMenu::item:selected {
    background-color: #1F6FEB;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background: #30363D;
    margin: 3px 0;
}

/* ── Tooltip ─────────────────────────────────────────────────── */
QToolTip {
    background-color: #1C2333;
    color: #E6EDF3;
    border: 1px solid #00D4FF;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 11px;
}

/* ── FrameCard (used as card containers in tabs) ─────────────── */
QFrame#card {
    background-color: #161B22;
    border: 1px solid #21262D;
    border-radius: 8px;
}
"""

LIGHT = """
/* ── Global ─────────────────────────────────────────────────── */
QWidget {
    background-color: #F5F7FA;
    color: #1A1D23;
    font-family: "JetBrains Mono", "Consolas", "Courier New", monospace;
    font-size: 12px;
}
QMainWindow {
    background-color: #EAEEF2;
}

/* ── GroupBox ────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #D0D7DE;
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 6px 6px 6px;
    font-weight: 600;
    color: #57606A;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #0078D4;
    font-size: 11px;
    letter-spacing: 1px;
}

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {
    background-color: #FFFFFF;
    color: #1A1D23;
    border: 1px solid #D0D7DE;
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #F0F6FF;
    border-color: #0078D4;
    color: #0078D4;
}
QPushButton:pressed {
    background-color: #0078D4;
    color: #FFFFFF;
}
QPushButton:disabled {
    color: #D0D7DE;
    border-color: #EAEEF2;
}
QPushButton#btn_primary {
    background-color: #0078D4;
    color: #FFFFFF;
    border: none;
    font-weight: 700;
}
QPushButton#btn_primary:hover {
    background-color: #0063B1;
}
QPushButton#btn_danger {
    color: #CF222E;
    border: 1px solid #CF222E;
}
QPushButton#btn_danger:hover {
    background-color: #CF222E;
    color: #FFFFFF;
}
QPushButton#btn_success {
    color: #1A7F37;
    border: 1px solid #1A7F37;
}
QPushButton#btn_success:hover {
    background-color: #1A7F37;
    color: #FFFFFF;
}

/* ── LineEdit / SpinBox / ComboBox ───────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #FFFFFF;
    color: #1A1D23;
    border: 1px solid #D0D7DE;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #0078D4;
}
QLineEdit:read-only {
    background-color: #F5F7FA;
    color: #57606A;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    color: #1A1D23;
    selection-background-color: #0078D4;
    selection-color: #FFFFFF;
}

/* ── TabWidget ───────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #D0D7DE;
    border-radius: 6px;
    background-color: #F5F7FA;
}
QTabBar::tab {
    background-color: #EAEEF2;
    color: #57606A;
    border: 1px solid #D0D7DE;
    border-bottom: none;
    padding: 6px 14px;
    margin-right: 2px;
    border-radius: 5px 5px 0 0;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #F5F7FA;
    color: #0078D4;
    border-bottom: 2px solid #0078D4;
}
QTabBar::tab:hover:!selected {
    background-color: #F0F6FF;
    color: #1A1D23;
}

/* ── Table ───────────────────────────────────────────────────── */
QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F5F7FA;
    gridline-color: #D0D7DE;
    border: 1px solid #D0D7DE;
    border-radius: 4px;
}
QTableWidget::item:selected {
    background-color: #F0F6FF;
    color: #0078D4;
}
QHeaderView::section {
    background-color: #F5F7FA;
    color: #57606A;
    border: none;
    border-right: 1px solid #D0D7DE;
    border-bottom: 1px solid #D0D7DE;
    padding: 5px 8px;
    font-weight: 700;
    font-size: 10px;
    letter-spacing: 1px;
}

/* ── Labels ──────────────────────────────────────────────────── */
QLabel#label_value {
    color: #0078D4;
    font-weight: 700;
    font-size: 13px;
}
QLabel#label_ok {
    color: #1A7F37;
    font-weight: 700;
}
QLabel#label_error {
    color: #CF222E;
    font-weight: 700;
}
QLabel#label_warn {
    color: #9A6700;
    font-weight: 700;
}
QLabel#label_section {
    color: #57606A;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}

/* ── RadioButton / CheckBox ──────────────────────────────────── */
QRadioButton, QCheckBox {
    color: #1A1D23;
    spacing: 6px;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #D0D7DE;
    border-radius: 7px;
    background-color: #FFFFFF;
}
QCheckBox::indicator { border-radius: 3px; }
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background-color: #0078D4;
    border-color: #0078D4;
}

/* ── ProgressBar ─────────────────────────────────────────────── */
QProgressBar {
    background-color: #EAEEF2;
    border: 1px solid #D0D7DE;
    border-radius: 4px;
    text-align: center;
    color: #1A1D23;
    font-size: 10px;
}
QProgressBar::chunk {
    background-color: #0078D4;
    border-radius: 3px;
}

/* ── StatusBar ───────────────────────────────────────────────── */
QStatusBar {
    background-color: #EAEEF2;
    color: #57606A;
    border-top: 1px solid #D0D7DE;
    font-size: 11px;
}

/* ── ToolBar ─────────────────────────────────────────────────── */
QToolBar {
    background-color: #EAEEF2;
    border-bottom: 1px solid #D0D7DE;
    spacing: 4px;
    padding: 3px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px 8px;
    color: #57606A;
    font-weight: 600;
}
QToolButton:hover {
    background-color: #F0F6FF;
    border-color: #D0D7DE;
    color: #1A1D23;
}
QToolButton:pressed, QToolButton:checked {
    background-color: #E8F0FE;
    border-color: #0078D4;
    color: #0078D4;
}

/* ── Tooltip ─────────────────────────────────────────────────── */
QToolTip {
    background-color: #1C2333;
    color: #E6EDF3;
    border: 1px solid #0078D4;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 11px;
}

/* ── FrameCard ───────────────────────────────────────────────── */
QFrame#card {
    background-color: #FFFFFF;
    border: 1px solid #D0D7DE;
    border-radius: 8px;
}

QScrollBar:vertical { background:#F5F7FA; width:8px; margin:0; }
QScrollBar::handle:vertical { background:#D0D7DE; border-radius:4px; min-height:20px; }
QScrollBar::handle:vertical:hover { background:#0078D4; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:#F5F7FA; height:8px; }
QScrollBar::handle:horizontal { background:#D0D7DE; border-radius:4px; min-width:20px; }
QScrollBar::handle:horizontal:hover { background:#0078D4; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }

QDockWidget::title { background-color:#EAEEF2; padding:5px 10px; border-bottom:1px solid #D0D7DE; }
QMenu { background-color:#FFFFFF; border:1px solid #D0D7DE; color:#1A1D23; }
QMenu::item:selected { background-color:#0078D4; color:#FFFFFF; }
QMenuBar { background-color:#EAEEF2; color:#1A1D23; border-bottom:1px solid #D0D7DE; }
QMenuBar::item:selected { background-color:#F0F6FF; }
"""


def get_theme(name="dark"):
    return DARK if name == "dark" else LIGHT


def get_matplotlib_style(name="dark"):
    """Return matplotlib rcParams dict matching the GUI theme."""
    if name == "dark":
        return {
            "figure.facecolor":  "#0D1117",
            "axes.facecolor":    "#161B22",
            "axes.edgecolor":    "#30363D",
            "axes.labelcolor":   "#E6EDF3",
            "axes.titlecolor":   "#E6EDF3",
            "xtick.color":       "#8B949E",
            "ytick.color":       "#8B949E",
            "grid.color":        "#21262D",
            "text.color":        "#E6EDF3",
            "lines.color":       "#00D4FF",
            "figure.edgecolor":  "#0D1117",
        }
    else:
        return {
            "figure.facecolor":  "#F5F7FA",
            "axes.facecolor":    "#FFFFFF",
            "axes.edgecolor":    "#D0D7DE",
            "axes.labelcolor":   "#1A1D23",
            "axes.titlecolor":   "#1A1D23",
            "xtick.color":       "#57606A",
            "ytick.color":       "#57606A",
            "grid.color":        "#EAEEF2",
            "text.color":        "#1A1D23",
            "lines.color":       "#0078D4",
            "figure.edgecolor":  "#F5F7FA",
        }


def build_scaled_theme(name="dark"):
    """
    Return QSS with font-size px replaced by DPI-aware pt values.
    Call after init_scale(app) has been called.
    """
    import re
    try:
        from gui.scale import font_size, get_factor
        get_factor()  # will throw if not initialised
    except Exception:
        return get_theme(name)

    base = get_theme(name)

    def px_to_pt(m):
        px = int(m.group(1))
        # Convert px → pt using DPI-aware font_size().
        # We subtract 2 because CSS px ≈ pt + 2 for body text at 96dpi.
        pt = font_size(max(6, px - 2))
        return f"font-size: {pt}pt;"

    return re.sub(r'font-size:\s*(\d+)px;', px_to_pt, base)
