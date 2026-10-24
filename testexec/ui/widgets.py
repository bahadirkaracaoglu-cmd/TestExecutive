"""Ortak arayüz bileşenleri."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QTableWidgetItem, QVBoxLayout)

from . import theme


def shadow(w, blur=28, alpha=90):
    e = QGraphicsDropShadowEffect(w)
    e.setBlurRadius(blur)
    e.setOffset(0, 6)
    e.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(e)


class Card(QFrame):
    def __init__(self, title: str = "", parent=None, margins=(18, 16, 18, 16)):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*margins)
        self.lay.setSpacing(10)
        if title:
            self.title = QLabel(title.upper())
            self.title.setObjectName("cardTitle")
            self.lay.addWidget(self.title)
        shadow(self)


class Kpi(QFrame):
    def __init__(self, label: str, value: str = "–", color: str = theme.TEXT, parent=None):
        super().__init__(parent)
        self.setObjectName("kpi")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        self.lbl = QLabel(label.upper())
        self.lbl.setObjectName("kpiLabel")
        self.val = QLabel(value)
        self.val.setObjectName("kpiValue")
        self.set_value(value, color)
        lay.addWidget(self.lbl)
        lay.addWidget(self.val)

    def set_value(self, text: str, color: str = theme.TEXT):
        self.val.setText(text)
        self.val.setStyleSheet(f"color:{color};")


class StatusDot(QLabel):
    """Bağlantı durumu çipi: ● ad"""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.setObjectName("chip")
        self.set_state(None)

    def set_state(self, ok):
        color = theme.MUTED if ok is None else (theme.PASS if ok else theme.FAIL)
        self.setText(f"<span style='color:{color}'>●</span>&nbsp;{self.name}")


def status_item(status: str) -> QTableWidgetItem:
    it = QTableWidgetItem(f"●  {theme.STATUS_TR.get(status, status)}")
    it.setForeground(QColor(theme.STATUS_COLORS.get(status, theme.MUTED)))
    f = it.font()
    f.setBold(True)
    it.setFont(f)
    return it


def page_header(title: str, sub: str = "") -> QHBoxLayout:
    lay = QHBoxLayout()
    box = QVBoxLayout()
    t = QLabel(title)
    t.setObjectName("pageTitle")
    box.addWidget(t)
    if sub:
        s = QLabel(sub)
        s.setObjectName("pageSub")
        box.addWidget(s)
    lay.addLayout(box)
    lay.addStretch()
    return lay