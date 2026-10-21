"""Zentrales Design des LiedManager (Warm-Anthrazit-Flächen + Bronze-Akzent).

Alles, was irgendwo gleich aussehen soll, kommt von hier: Farben, Maße und die
Stylesheet-Bausteine. Die Zustände sind überall nach demselben Muster aufgebaut:

    normal   -> neutrale Kontur (BORDER) bzw. Bronze-Kontur bei bedienbaren Elementen
    hover    -> Kontur wird heller (ACCENT) und die Fläche minimal heller
    gedrückt -> Fläche dunkler, Kontur ACCENT_LIGHT
    Fokus    -> Kontur ACCENT (Eingabefelder) / ACCENT_LIGHT (Tastatur-Fokus bei Buttons)
    gewählt  -> Kontur ACCENT + leichte Bronze-Tönung der Fläche
"""
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import QApplication

from paths import ASSETS_DIR

# ----------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------
CARD_BG = "#1A1817"          # Fenster-Hintergrund
SURFACE = "#232120"          # Eingabefelder, Panel-Oberkante
SURFACE_LOW = "#1E1B19"      # Panel-Unterkante
SURFACE_HOVER_TOP = "#2A2725"
SURFACE_HOVER_BOTTOM = "#221F1D"
SURFACE_PRESSED = "#171413"
BORDER = "#312D2A"           # neutrale Kontur
TRACK_BG = "#34302C"         # Schienen (Fortschritt, Pegel)

TEXT_PRIMARY = "#F2ECE5"
TEXT_SECONDARY = "#B3AAA2"
TEXT_LABEL = "#D9D1C9"
TEXT_MUTED = "#857D75"

ACCENT = "#C08A53"           # Bronze
ACCENT_LIGHT = "#D9A46A"
ACCENT_GLOW = "#EBC08A"
ACCENT_DEEP = "#8F6236"
ACCENT_BORDER = "#7A5838"    # Kontur bedienbarer Elemente im Ruhezustand
ACCENT_TINT = "#2E251C"      # Fläche gewählter Elemente

PILL_TEXT = "#E2C9A6"
TRACK_NAME_COLOR = "#F2D9B8"

REC_RED = "#F0654A"
REC_RUNNING_BG = "#2B1F18"
REC_TIME_RUNNING = "#E8BE88"

# ----------------------------------------------------------------------
# Maße & Schrift
# ----------------------------------------------------------------------
BTN = 44
GAP = 12
RADIUS = 12
PANEL_RADIUS = 16
FS = 14
FS_SMALL = 12
# Schriften: Fraunces ist die Wunschschrift und wird verwendet, sobald sie als Datei in ui/assets/fonts
# liegt (siehe load_bundled_fonts) oder installiert ist. Sonst greifen Georgia bzw. Arial – beide sind
# auf jedem Windows- und macOS-System vorhanden. Alle Texte im Programm sind damit überall lesbar.
SERIF_FAMILIES = ["Fraunces", "Georgia", "Times New Roman", "serif"]
SERIF = ", ".join(f'"{name}"' if " " in name else name for name in SERIF_FAMILIES)
BODY_FAMILIES = ["Arial", "Helvetica Neue", "Helvetica", "sans-serif"]
SAFE_FAMILIES = ("Arial", "Georgia")   # auf Windows und macOS immer installiert (wird im Smoke-Test geprüft)

PANEL_GRADIENT = (
    f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SURFACE}, stop:1 {SURFACE_LOW})"
)
PANEL_GRADIENT_HOVER = (
    f"qlineargradient(x1:0, y1:0, x2:0, y2:1, "
    f"stop:0 {SURFACE_HOVER_TOP}, stop:1 {SURFACE_HOVER_BOTTOM})"
)
ACCENT_GRADIENT = (
    f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT_LIGHT}, stop:1 {ACCENT})"
)
ACCENT_GRADIENT_HOVER = (
    f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {ACCENT_GLOW}, stop:1 {ACCENT_LIGHT})"
)


def body_font() -> QFont:
    font = QFont()
    font.setFamilies(BODY_FAMILIES)
    return font


def load_bundled_fonts() -> list:
    """Registriert Schriftdateien (.ttf/.otf) aus ui/assets/fonts, damit sie unabhängig vom System verfügbar sind.

    Der Ordner ist optional: Wer z. B. Fraunces (Lizenz: OFL) dort ablegt, bekommt sie auf Windows und
    macOS gleich – ohne Installation. Fehlt der Ordner, passiert nichts. Rückgabe: die geladenen Familien.
    """
    folder = ASSETS_DIR / "fonts"
    loaded = []
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in (".ttf", ".otf"):
                font_id = QFontDatabase.addApplicationFont(str(path))
                if font_id >= 0:
                    loaded += QFontDatabase.applicationFontFamilies(font_id)
    return loaded


def resolve_family(candidates) -> str:
    """Erste tatsächlich vorhandene Schriftfamilie aus ``candidates`` (leer, wenn keine installiert ist)."""
    installed = set(QFontDatabase.families())
    return next((name for name in candidates if name in installed), "")


def _asset(name: str) -> str:
    """Pfad für ``url(...)`` im Stylesheet (Anführungszeichen, da der Pfad Leerzeichen enthalten kann)."""
    return '"' + (ASSETS_DIR / name).as_posix() + '"'


# ----------------------------------------------------------------------
# Stylesheet-Bausteine
# ----------------------------------------------------------------------
def panel_style(name: str) -> str:
    return f"""
        QFrame#{name} {{
            background: {PANEL_GRADIENT};
            border: 1px solid {BORDER};
            border-radius: {PANEL_RADIUS}px;
        }}
        QFrame#{name} QLabel {{ border: 0; background: transparent; }}
    """


def round_button_style(background=None, hover_background=None, border=None,
                       hover_border=None, radius=None) -> str:
    background = background or PANEL_GRADIENT
    hover_background = hover_background or (
        PANEL_GRADIENT_HOVER if background == PANEL_GRADIENT else background
    )
    border = border or ACCENT_BORDER
    hover_border = hover_border or ACCENT
    radius = BTN // 2 if radius is None else radius
    return f"""
        QPushButton {{
            background: {background};
            border: 1px solid {border};
            border-radius: {radius}px;
            padding: 0;
        }}
        QPushButton:hover {{ border-color: {hover_border}; background: {hover_background}; }}
        QPushButton:pressed {{ border-color: {ACCENT_LIGHT}; background: {SURFACE_PRESSED}; }}
        QPushButton:focus {{ border-color: {ACCENT_LIGHT}; }}
        QPushButton:disabled {{ border-color: {BORDER}; }}
    """


def pill_button_style(radius: int = BTN // 2, font_size: int = FS) -> str:
    """Beschriftete, umschaltbare Pille (Audio 1 / Audio 2)."""
    return f"""
        QPushButton {{
            color: {PILL_TEXT};
            background: {PANEL_GRADIENT};
            border: 1px solid {ACCENT_BORDER};
            border-radius: {radius}px;
            font-size: {font_size}px;
            font-weight: 500;
            padding: 0 16px;
        }}
        QPushButton:hover {{
            border-color: {ACCENT}; color: {TEXT_PRIMARY}; background: {PANEL_GRADIENT_HOVER};
        }}
        QPushButton:pressed {{ border-color: {ACCENT_LIGHT}; background: {SURFACE_PRESSED}; }}
        QPushButton:checked {{
            border-color: {ACCENT}; color: {TEXT_PRIMARY}; background: {ACCENT_TINT};
        }}
        QPushButton:focus {{ border-color: {ACCENT_LIGHT}; }}
        QPushButton:disabled {{ color: {TEXT_MUTED}; border-color: {BORDER}; }}
    """


def primary_button_style(name: str, radius: int = RADIUS) -> str:
    return f"""
        QPushButton#{name} {{
            color: {CARD_BG};
            font-size: {FS}px;
            font-weight: 600;
            padding: 0 24px;
            background: {ACCENT_GRADIENT};
            border: 1px solid {ACCENT_LIGHT};
            border-radius: {radius}px;
        }}
        QPushButton#{name}:hover {{ background: {ACCENT_GRADIENT_HOVER}; border-color: {ACCENT_GLOW}; }}
        QPushButton#{name}:pressed {{ background: {ACCENT}; border-color: {ACCENT_LIGHT}; }}
        QPushButton#{name}:focus {{ border-color: {ACCENT_GLOW}; }}
    """


def input_style(selector: str, padding: str = "0 12px", color: str = TEXT_PRIMARY,
                weight=None, background: str = SURFACE, font_size: int = FS,
                right_padding=None) -> str:
    weight_css = f"font-weight: {weight};" if weight else ""
    if right_padding is not None:
        top_bottom, _, left = padding.partition(" ")
        padding = f"{top_bottom} {right_padding}px 0 {left}" if left else padding
    return f"""
        {selector} {{
            background: {background};
            border: 1px solid {BORDER};
            border-radius: {RADIUS}px;
            padding: {padding};
            color: {color};
            font-size: {font_size}px;
            placeholder-text-color: {TEXT_MUTED};
            selection-background-color: {ACCENT_DEEP};
            selection-color: {TEXT_PRIMARY};
            {weight_css}
        }}
        {selector}:hover {{ border: 1px solid {ACCENT_BORDER}; }}
        {selector}:focus {{ border: 1px solid {ACCENT}; }}
        {selector}:disabled {{ color: {TEXT_MUTED}; border: 1px solid {BORDER}; }}
    """


def combo_style() -> str:
    return f"""
        QComboBox {{
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: {RADIUS}px;
            padding: 0 36px 0 12px;
            color: {TEXT_PRIMARY};
            font-size: {FS}px;
            combobox-popup: 0;
        }}
        QComboBox:hover {{ border: 1px solid {ACCENT_BORDER}; }}
        QComboBox:focus, QComboBox:on {{ border: 1px solid {ACCENT}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: center right;
            width: 32px; border: 0; background: transparent;
        }}
        QComboBox::down-arrow {{ image: url({_asset("chevron-down.svg")}); width: 14px; height: 14px; }}
        QComboBox QAbstractItemView {{
            background: {SURFACE};
            color: {TEXT_PRIMARY};
            border: 1px solid {ACCENT_BORDER};
            border-radius: 10px;
            padding: 4px;
            outline: 0;
            selection-background-color: {ACCENT_TINT};
            selection-color: {ACCENT_LIGHT};
        }}
        QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 0 8px; border-radius: 6px; }}
        QComboBox QAbstractItemView::item:hover {{ background: rgba(255,255,255,0.05); }}
    """


def spinbox_style() -> str:
    arrows = f"""
        QSpinBox::up-button, QSpinBox::down-button {{
            subcontrol-origin: border; width: 28px; border: 0; background: transparent;
        }}
        QSpinBox::up-button {{ subcontrol-position: top right; margin: 1px 1px 0 0;
            border-top-right-radius: {RADIUS - 1}px; }}
        QSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 1px 1px 0;
            border-bottom-right-radius: {RADIUS - 1}px; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: rgba(255,255,255,0.06); }}
        QSpinBox::up-arrow {{ image: url({_asset("chevron-up.svg")}); width: 10px; height: 10px; }}
        QSpinBox::down-arrow {{ image: url({_asset("chevron-down.svg")}); width: 10px; height: 10px; }}
    """
    return input_style("QSpinBox", "0 12px", right_padding=34) + arrows


def checkbox_style() -> str:
    return f"""
        QCheckBox {{ color: {TEXT_LABEL}; font-size: {FS}px; spacing: 10px; background: transparent; }}
        QCheckBox:hover {{ color: {TEXT_PRIMARY}; }}
        QCheckBox::indicator {{
            width: 18px; height: 18px;
            border: 1px solid {ACCENT_BORDER}; border-radius: 6px; background: {SURFACE};
        }}
        QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
        QCheckBox::indicator:focus {{ border-color: {ACCENT_LIGHT}; }}
        QCheckBox::indicator:checked {{
            background: {ACCENT}; border-color: {ACCENT}; image: url({_asset("check-dark.svg")});
        }}
        QCheckBox::indicator:checked:hover {{ background: {ACCENT_LIGHT}; border-color: {ACCENT_LIGHT}; }}
    """


def list_style() -> str:
    return f"""
        QListWidget {{
            background: {SURFACE};
            border: 1px solid {ACCENT};
            border-radius: {RADIUS}px;
            color: {TEXT_PRIMARY};
            font-size: {FS}px;
            padding: 4px;
            outline: 0;
        }}
        QListWidget::item {{ padding: 8px 10px; border-radius: 8px; border: 1px solid transparent; }}
        QListWidget::item:hover {{ background: rgba(255,255,255,0.04); border: 1px solid {BORDER}; }}
        QListWidget::item:selected {{
            background: {ACCENT_TINT}; color: {ACCENT_LIGHT}; border: 1px solid {ACCENT_BORDER};
        }}
    """


def caption_style() -> str:
    return (f"font-size: {FS_SMALL}px; font-weight: 500; color: {TEXT_SECONDARY}; "
            f"background: transparent; border: 0;")


def hint_style() -> str:
    return f"font-size: {FS_SMALL}px; color: {TEXT_MUTED}; background: transparent; border: 0;"


def _global_stylesheet() -> str:
    outline = f"""
        color: {PILL_TEXT}; background: {PANEL_GRADIENT}; border: 1px solid {ACCENT_BORDER};
        border-radius: 10px; padding: 0 18px; min-height: 34px; min-width: 84px;
        font-size: {FS}px; font-weight: 500;
    """
    return f"""
        QDialog, QMessageBox {{ background: {CARD_BG}; }}
        QToolTip {{
            background: {SURFACE}; color: {TEXT_PRIMARY};
            border: 1px solid {ACCENT_BORDER}; padding: 5px 8px;
        }}
        QMessageBox QLabel {{ color: {TEXT_PRIMARY}; font-size: {FS}px; }}
        QMessageBox QPushButton {{ {outline} }}
        QMessageBox QPushButton:hover {{ border-color: {ACCENT}; color: {TEXT_PRIMARY}; }}
        QMessageBox QPushButton:pressed {{ background: {SURFACE_PRESSED}; border-color: {ACCENT_LIGHT}; }}
        QMessageBox QPushButton:default {{ border-color: {ACCENT}; }}
        QMenu {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; color: {TEXT_PRIMARY}; }}
        QMenu::item {{ padding: 6px 20px; border-radius: 6px; }}
        QMenu::item:selected {{ background: {ACCENT_TINT}; color: {ACCENT_LIGHT}; }}
        QMenu::item:disabled {{ color: {TEXT_MUTED}; }}
        QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px 2px 2px 0; }}
        QScrollBar::handle:vertical {{ background: {TRACK_BG}; border-radius: 3px; min-height: 28px; margin: 0 2px; }}
        QScrollBar::handle:vertical:hover {{ background: {ACCENT_BORDER}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; width: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0 2px 2px 2px; }}
        QScrollBar::handle:horizontal {{ background: {TRACK_BG}; border-radius: 3px; min-width: 28px; margin: 2px 0; }}
        QScrollBar::handle:horizontal:hover {{ background: {ACCENT_BORDER}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ height: 0; width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    """


def apply_theme(app: QApplication) -> None:
    """Einheitlicher Look auf allen Plattformen: Fusion-Stil + dunkle Palette + Basis-Stylesheet."""
    app.setStyle("Fusion")

    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: CARD_BG,
        QPalette.ColorRole.WindowText: TEXT_PRIMARY,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: SURFACE_LOW,
        QPalette.ColorRole.Text: TEXT_PRIMARY,
        QPalette.ColorRole.Button: SURFACE,
        QPalette.ColorRole.ButtonText: TEXT_PRIMARY,
        QPalette.ColorRole.ToolTipBase: SURFACE,
        QPalette.ColorRole.ToolTipText: TEXT_PRIMARY,
        QPalette.ColorRole.Highlight: ACCENT_DEEP,
        QPalette.ColorRole.HighlightedText: TEXT_PRIMARY,
        QPalette.ColorRole.PlaceholderText: TEXT_MUTED,
        QPalette.ColorRole.Link: ACCENT_LIGHT,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(TEXT_MUTED))
    app.setPalette(palette)

    load_bundled_fonts()  # vor dem Setzen der Schrift, damit mitgelieferte Dateien greifen
    app.setFont(body_font())
    app.setStyleSheet(_global_stylesheet())
