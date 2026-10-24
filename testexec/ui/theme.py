"""Koyu 'enstrüman paneli' teması."""

BG = "#0b0f14"
SIDEBAR = "#0e131a"
PANEL = "#141a23"
PANEL2 = "#1a222d"
PANEL3 = "#222c39"
BORDER = "#263140"
TEXT = "#e8eef5"
MUTED = "#8593a6"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#3b76ea"
PASS = "#2ee6a0"
FAIL = "#ff5c6c"
WARN = "#ffb547"


def a(color: str, alpha_hex: str) -> str:
    """'#rrggbb' + 2 haneli hex alfa -> Qt'nin anlayacağı rgba() metni."""
    c = color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return f"rgba({r},{g},{b},{int(alpha_hex, 16)})"


STATUS_COLORS = {
    "PASS": PASS, "FAIL": FAIL, "ERROR": WARN, "SKIPPED": MUTED,
    "RUNNING": ACCENT, "PENDING": MUTED, "IDLE": MUTED,
}
STATUS_TR = {
    "PASS": "GEÇTİ", "FAIL": "KALDI", "ERROR": "HATA", "SKIPPED": "ATLANDI",
    "RUNNING": "KOŞUYOR", "PENDING": "BEKLİYOR", "IDLE": "HAZIR",
}

QSS = f"""
* {{ font-family: 'Segoe UI Variable', 'Segoe UI', 'Inter', sans-serif; font-size: 13px; color: {TEXT}; outline: none; }}
QMainWindow, QWidget#root, QStackedWidget {{ background: {BG}; }}
QWidget#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QLabel#logo {{ font-size: 22px; font-weight: 800; color: {ACCENT}; }}
QToolButton#nav {{ background: transparent; border: none; border-radius: 10px; color: {MUTED};
                  padding: 10px 4px; font-size: 11px; font-weight: 600; }}
QToolButton#nav:hover {{ background: {PANEL2}; color: {TEXT}; }}
QToolButton#nav:checked {{ background: {a(ACCENT,'22')}; color: {ACCENT}; }}
QWidget#header {{ background: {BG}; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 700; }}
QLabel#pageSub {{ color: {MUTED}; }}

QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#kpi {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#cardTitle {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1.2px; }}
QLabel#kpiValue {{ font-size: 24px; font-weight: 700; }}
QLabel#kpiLabel {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#chip {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 12px; padding: 4px 12px; color: {MUTED}; font-weight: 600; }}

QLineEdit, QComboBox, QSpinBox {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 12px; min-height: 18px; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; padding: 4px; }}

QPushButton {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 9px 18px; font-weight: 600; }}
QPushButton:hover {{ border-color: {ACCENT}; background: {PANEL3}; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; font-size: 14px; padding: 12px 18px; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#danger {{ background: {a(FAIL,'22')}; border: 1px solid {FAIL}; color: {FAIL}; font-size: 14px; padding: 12px 18px; }}
QPushButton#danger:hover {{ background: {a(FAIL,'44')}; }}
QPushButton:disabled {{ background: {PANEL}; color: {a(MUTED,'66')}; border-color: {BORDER}; }}

QTableWidget {{ background: transparent; border: none; gridline-color: transparent; alternate-background-color: {a(PANEL2,'44')};
               selection-background-color: {a(ACCENT,'26')}; selection-color: {TEXT}; }}
QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {a(BORDER,'66')}; }}
QHeaderView {{ background: transparent; border: none; }}
QTableCornerButton::section {{ background: transparent; border: none; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
                       padding: 8px; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 16px; font-weight: 600; margin-right: 4px; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QPlainTextEdit, QTextEdit {{ background: {PANEL}; border: none; font-family: 'Cascadia Mono', Consolas, monospace; font-size: 12px; }}
QProgressBar {{ background: {PANEL3}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QDialog {{ background: {PANEL}; }}
QMessageBox {{ background: {PANEL}; }}
QToolTip {{ background: {PANEL3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 8px; }}
"""
