# gui/scale.py
# DPI-aware scaling helper.
# Call scale(n) to get a pixel value that looks correct on
# FHD (96 dpi), 2K (120 dpi), and 4K (192 dpi) screens.
#
# Usage:
#   from gui.scale import sc, font_size
#   widget.setFixedWidth(sc(230))
#   label.setStyleSheet(f"font-size: {font_size(11)}pt;")
#
# Must be initialised after QApplication is created:
#   from gui.scale import init_scale
#   init_scale(app)

from PyQt5.QtWidgets import QApplication

# Default: 1.0 (96 dpi baseline)
_factor = 1.0


def init_scale(app=None):
    """
    Compute scale factor from the primary screen's logical DPI.
    Call once after QApplication is created.
    96 dpi  → factor 1.00  (FHD laptop, standard)
    120 dpi → factor 1.25  (2K / 125% scaling)
    144 dpi → factor 1.50  (2K / 150% scaling)
    192 dpi → factor 2.00  (4K / 200% scaling)
    """
    global _factor
    if app is None:
        app = QApplication.instance()
    if app is None:
        return

    screen = app.primaryScreen()
    if screen is None:
        return

    # Use logical DPI (already accounts for OS display scaling)
    dpi = screen.logicalDotsPerInchX()
    _factor = dpi / 96.0

    # Clamp: never shrink below 0.85 (very low-DPI screens),
    # never expand above 2.5 (prevents absurd sizes on 8K)
    _factor = max(0.85, min(_factor, 2.5))
    print(f"[Scale] DPI={dpi:.0f}  factor={_factor:.3f}")


def sc(pixels: int) -> int:
    """Scale a pixel value by the DPI factor. Returns int."""
    return max(1, int(round(pixels * _factor)))


def scf(pixels: float) -> float:
    """Scale a pixel value, returning float (for font sizes etc)."""
    return pixels * _factor


def font_size(pt: int) -> int:
    """
    Return a font point size scaled for current DPI.
    Point sizes are resolution-independent in Qt, but we still
    scale them slightly so text stays comfortable across screens.
    Uses a gentler curve than sc() — only ±15% adjustment.
    """
    # On FHD (factor≈1.0) keep pt as-is.
    # On 4K (factor≈2.0) scale by √factor so text doesn't balloon.
    import math
    adjusted = pt * math.sqrt(_factor)
    return max(7, int(round(adjusted)))


def settings_panel_width() -> int:
    """Adaptive settings panel width."""
    # FHD: 200px, 2K: 220px, 4K: 240px
    return sc(200)


def get_factor() -> float:
    return _factor
