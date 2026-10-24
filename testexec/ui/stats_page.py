"""İstatistik / trend sayfası."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..analysis import summarize
from . import theme
from .widgets import Card, Kpi


class StatsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 8, 28, 24)
        outer.setSpacing(16)

        bar = QHBoxLayout()
        lbl = QLabel("Ölçüm:")
        lbl.setObjectName("muted")
        self.combo = QComboBox()
        self.combo.setMinimumWidth(280)
        refresh = QPushButton("⟳  Yenile")
        refresh.clicked.connect(self.refresh)
        self.combo.currentIndexChanged.connect(self.update_view)
        bar.addWidget(lbl)
        bar.addWidget(self.combo)
        bar.addWidget(refresh)
        bar.addStretch()
        outer.addLayout(bar)

        k = QHBoxLayout()
        k.setSpacing(14)
        self.k = {n: Kpi(n) for n in ("Örnek", "Ortalama", "Std Sapma", "Min", "Max", "Cp", "Cpk")}
        for w in self.k.values():
            k.addWidget(w)
        outer.addLayout(k)

        row = QHBoxLayout()
        row.setSpacing(16)
        outer.addLayout(row, 1)
        trend = Card("Trend", margins=(14, 12, 14, 12))
        self.trend = pg.PlotWidget()
        self.trend.showGrid(x=True, y=True, alpha=0.12)
        self.trend.setLabel("bottom", "Koşu sırası")
        trend.lay.addWidget(self.trend)
        row.addWidget(trend, 3)
        hist = Card("Dağılım", margins=(14, 12, 14, 12))
        self.hist = pg.PlotWidget()
        self.hist.showGrid(x=True, y=True, alpha=0.12)
        hist.lay.addWidget(self.hist)
        row.addWidget(hist, 2)
        self.refresh()

    def refresh(self):
        cur = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(self.ctx.repo.numeric_step_names())
        i = self.combo.findText(cur)
        if i >= 0:
            self.combo.setCurrentIndex(i)
        self.combo.blockSignals(False)
        self.update_view()

    def update_view(self):
        name = self.combo.currentText()
        self.trend.clear()
        self.hist.clear()
        if not name:
            for kpi in self.k.values():
                kpi.set_value("–")
            return
        vals = self.ctx.repo.step_history(name)
        lo, hi, unit = self.ctx.repo.step_limits(name)
        s = summarize(vals, lo, hi)
        fmt = lambda v: "–" if v is None else f"{v:.4g}"
        self.k["Örnek"].set_value(str(s.n))
        self.k["Ortalama"].set_value(f"{fmt(s.mean)} {unit}")
        self.k["Std Sapma"].set_value(fmt(s.std))
        self.k["Min"].set_value(fmt(s.minimum))
        self.k["Max"].set_value(fmt(s.maximum))
        self.k["Cp"].set_value(fmt(s.cp))
        cpk_color = theme.TEXT if s.cpk is None else (theme.PASS if s.cpk >= 1.33 else theme.WARN if s.cpk >= 1.0 else theme.FAIL)
        self.k["Cpk"].set_value(fmt(s.cpk), cpk_color)

        y = np.array(vals)
        self.trend.plot(y, pen=pg.mkPen(theme.ACCENT, width=2), symbol="o", symbolSize=6,
                        symbolBrush=theme.ACCENT, symbolPen=None)
        self.trend.addItem(pg.InfiniteLine(s.mean, angle=0, pen=pg.mkPen(theme.PASS, width=1)))
        dash = pg.mkPen(theme.FAIL, width=1.2, style=Qt.DashLine)
        for v in (lo, hi):
            if v is not None:
                self.trend.addItem(pg.InfiniteLine(v, angle=0, pen=dash))
        if len(y) > 1 and y.max() > y.min():
            counts, edges = np.histogram(y, bins=min(20, max(5, len(y) // 3)))
            self.hist.addItem(pg.BarGraphItem(x=(edges[:-1] + edges[1:]) / 2, height=counts,
                                              width=(edges[1] - edges[0]) * .9, brush=theme.ACCENT))
            for v in (lo, hi):
                if v is not None:
                    self.hist.addItem(pg.InfiniteLine(v, angle=90, pen=dash))