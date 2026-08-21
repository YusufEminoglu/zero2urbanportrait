"""Palette-aware styling for the 02Urban Portrait dock.

Derives every surface and text colour from the active Qt palette so the dock
stays readable under QGIS light, dark, high-contrast, and custom themes while
keeping the cyan accent and dark hero-card identity.
"""
from __future__ import annotations

from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QApplication, QWidget


def _hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb)


def _mix(first: QColor, second: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, float(amount)))
    return QColor(
        round(first.red() * (1.0 - amount) + second.red() * amount),
        round(first.green() * (1.0 - amount) + second.green() * amount),
        round(first.blue() * (1.0 - amount) + second.blue() * amount),
    )


def _contrast_text(background: QColor) -> QColor:
    luminance = (
        0.2126 * background.red()
        + 0.7152 * background.green()
        + 0.0722 * background.blue()
    )
    return QColor("#102019") if luminance >= 150 else QColor("#FFFFFF")


def _relative_luminance(color: QColor) -> float:
    channels = []
    for value in (color.redF(), color.greenF(), color.blueF()):
        channels.append(
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: QColor, second: QColor) -> float:
    """Return the WCAG relative-luminance contrast ratio."""
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def dock_color_tokens(palette: QPalette | None = None) -> dict[str, str]:
    """Return the palette-derived colours used by the dock stylesheet."""
    active = palette or QApplication.palette()
    window = active.color(QPalette.ColorRole.Window)
    base = active.color(QPalette.ColorRole.Base)
    text = active.color(QPalette.ColorRole.WindowText)
    input_text = active.color(QPalette.ColorRole.Text)
    button = active.color(QPalette.ColorRole.Button)
    button_text = active.color(QPalette.ColorRole.ButtonText)
    highlight = active.color(QPalette.ColorRole.Highlight)
    disabled = active.color(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.WindowText,
    )
    dark = window.lightness() < 128

    white = QColor("#FFFFFF")
    cyan_accent = QColor("#06B6D4" if dark else "#0891B2")
    cyan_hover = QColor("#22D3EE" if dark else "#0E7490")
    cyan_text = _contrast_text(cyan_accent)
    cyan_soft = _mix(cyan_accent, window, 0.88 if dark else 0.92)

    hero_bg = QColor("#0F172A")  # always dark — intentional branding
    hero_text = QColor("#F8FAFC")
    hero_subtle = QColor("#94A3B8")

    surface = _mix(window, white, 0.07) if dark else _mix(window, base, 0.72)
    card = _mix(window, white, 0.12) if dark else base
    input_surface = _mix(base, white, 0.04) if dark else base
    border = _mix(text, surface, 0.76 if dark else 0.84)
    subtle = _mix(text, surface, 0.40 if dark else 0.37)

    error_bg = QColor("#7F1D1D" if dark else "#FFF1F2")
    error_border = QColor("#FCA5A5" if dark else "#FECDD3")
    error_text = QColor("#FECACA" if dark else "#B91C1C")

    warn_bg = _mix(QColor("#F59E0B"), window, 0.85 if dark else 0.92)

    if contrast_ratio(input_text, input_surface) < 4.5:
        input_text = QColor(text)
    if contrast_ratio(button_text, button) < 4.5:
        button_text = QColor(text)
    selection = highlight if highlight.isValid() else cyan_accent

    return {
        "surface": _hex(surface),
        "card": _hex(card),
        "input_surface": _hex(input_surface),
        "text": _hex(text),
        "input_text": _hex(input_text),
        "button": _hex(button),
        "button_text": _hex(button_text),
        "border": _hex(border),
        "subtle": _hex(subtle),
        "disabled": _hex(disabled),
        "accent": _hex(cyan_accent),
        "accent_hover": _hex(cyan_hover),
        "accent_text": _hex(cyan_text),
        "accent_soft": _hex(cyan_soft),
        "hero_bg": _hex(hero_bg),
        "hero_text": _hex(hero_text),
        "hero_subtle": _hex(hero_subtle),
        "error_bg": _hex(error_bg),
        "error_border": _hex(error_border),
        "error_text": _hex(error_text),
        "warn_bg": _hex(warn_bg),
        "selection": _hex(selection),
    }


def dock_stylesheet(palette: QPalette | None = None) -> str:
    """Build the full dock stylesheet from the current application palette."""
    t = dock_color_tokens(palette)
    return """
QWidget#studioShell, QWidget#tabPage {
    background: %(surface)s;
    color: %(text)s;
}
QFrame#heroCard {
    background: %(hero_bg)s;
    border: 1px solid #1e293b;
    border-radius: 14px;
}
QLabel#heroTitle {
    color: %(hero_text)s;
    font-size: 18px;
    font-weight: 700;
}
QLabel#heroSubtitle {
    color: %(hero_subtle)s;
    font-size: 11px;
}
QLabel#localBadge {
    background: #164e63;
    color: #67e8f9;
    border-radius: 9px;
    padding: 4px 8px;
    font-size: 9px;
    font-weight: 700;
}
QLabel#workflowStrip {
    background: %(accent_soft)s;
    color: %(accent)s;
    border: 1px solid %(accent_soft)s;
    border-radius: 8px;
    padding: 8px;
    font-size: 10px;
    font-weight: 700;
}
QFrame#stepperContainer {
    background: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
    padding: 4px;
}
QLabel#stepGuideLabel {
    background: %(accent_soft)s;
    color: %(accent)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 10px;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid %(border)s;
    border-radius: 10px;
    background: %(surface)s;
    top: -1px;
}
QTabBar::tab {
    background: %(card)s;
    color: %(subtle)s;
    border: 1px solid %(border)s;
    padding: 9px 18px;
    min-width: 72px;
    font-weight: 600;
}
QTabBar::tab:first { border-top-left-radius: 8px; }
QTabBar::tab:last { border-top-right-radius: 8px; }
QTabBar::tab:selected {
    background: %(input_surface)s;
    color: %(accent)s;
    border-bottom-color: %(input_surface)s;
}
QGroupBox {
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 11px;
    margin-top: 13px;
    padding: 12px 9px 9px 9px;
    font-weight: 700;
    color: %(text)s;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: %(text)s;
}
QLabel#imagePreview {
    background: #091225;
    color: %(hero_subtle)s;
    border: 1px solid #1e293b;
    border-radius: 9px;
}
QLabel#mutedHint {
    color: %(subtle)s;
    font-size: 10px;
}
QLabel#successHint {
    color: %(accent)s;
    background: %(accent_soft)s;
    border-radius: 6px;
    padding: 5px 7px;
    font-size: 10px;
}
QLabel#tabIntro {
    color: %(text)s;
    background: %(accent_soft)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 9px;
}
QListWidget, QComboBox, QSpinBox, QDoubleSpinBox {
    background: %(input_surface)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 5px;
    selection-background-color: %(accent_soft)s;
}
QListWidget::item { padding: 5px; border-radius: 4px; }
QListWidget::item:selected { background: %(accent_soft)s; }
QPushButton {
    background: %(card)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: 7px;
    padding: 7px 10px;
    font-weight: 600;
}
QPushButton:hover {
    background: %(accent_soft)s;
    border-color: %(accent)s;
    color: %(accent)s;
}
QPushButton:pressed { background: %(accent_soft)s; }
QPushButton:disabled {
    background: %(input_surface)s;
    color: %(disabled)s;
    border-color: %(border)s;
}
QPushButton#accentButton {
    background: %(accent_soft)s;
    color: %(accent)s;
    border-color: %(accent)s;
}
QPushButton#primaryButton {
    background: %(accent)s;
    color: %(accent_text)s;
    border-color: %(accent)s;
    padding: 9px 13px;
    font-weight: 700;
}
QPushButton#primaryButton:hover {
    background: %(accent_hover)s;
    border-color: %(accent_hover)s;
}
QCheckBox { color: %(text)s; spacing: 7px; padding: 2px; }
QProgressBar { background: %(border)s; border: none; border-radius: 2px; }
QProgressBar::chunk { background: %(accent)s; border-radius: 2px; }
QLabel#statusCard {
    color: %(text)s;
    background: %(card)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 8px 10px;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: %(border)s;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip {
    background: %(card)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    padding: 4px;
}
""" % t


def apply_adaptive_theme(widget: QWidget) -> None:
    """Apply the active QGIS/Qt palette without overriding font preferences."""
    widget.setStyleSheet(dock_stylesheet(widget.palette()))
