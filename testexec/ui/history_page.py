"""Geçmiş sonuçlar ve rapor üretimi."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QCheckBox, QApplication)

from .. import reports
from . import theme
from .widgets import Card, page_header, status_item


class HistoryPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.runs = []
        self.current = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 8, 28, 24)
        outer.setSpacing(16)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Seri no ara…")
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self.refresh)
        refresh = QPushButton("⟳  Yenile")
        refresh.clicked.connect(self.refresh)
        self.traffic_chk = QCheckBox("Ham iletişimi rapora ekle")
        self.btn_pdf = QPushButton("PDF Rapor")
        self.btn_html = QPushButton("HTML Rapor")
        self.btn_xlsx = QPushButton("Excel (Listelenenler)")
        self.btn_pdf.clicked.connect(lambda: self.export("pdf"))
        self.btn_html.clicked.connect(lambda: self.export("html"))
        self.btn_xlsx.clicked.connect(lambda: self.export("xlsx"))
        for w in (self.search, refresh):
            bar.addWidget(w)
        bar.addStretch()
        for w in (self.traffic_chk, self.btn_pdf, self.btn_html, self.btn_xlsx):
            bar.addWidget(w)
        outer.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)

        runs_card = Card("Test Koşuları")
        self.runs_tbl = QTableWidget(0, 6)
        self.runs_tbl.setHorizontalHeaderLabels(["#", "TARİH", "SERİ NO", "SEKANS", "OPERATÖR", "SONUÇ"])
        self._style_table(self.runs_tbl, stretch=3)
        self.runs_tbl.itemSelectionChanged.connect(self.on_select)
        runs_card.lay.addWidget(self.runs_tbl)
        body.addWidget(runs_card, 6)

        right = QVBoxLayout()
        right.setSpacing(16)
        body.addLayout(right, 5)
        det = Card("Adım Detayı")
        self.det_title = QLabel("Bir koşu seçin")
        self.det_title.setObjectName("muted")
        det.lay.addWidget(self.det_title)
        self.steps_tbl = QTableWidget(0, 4)
        self.steps_tbl.setHorizontalHeaderLabels(["ADIM", "DURUM", "DEĞER", "LİMİT"])
        self._style_table(self.steps_tbl, stretch=0)
        self.steps_tbl.itemSelectionChanged.connect(self.on_step_select)
        det.lay.addWidget(self.steps_tbl)
        right.addWidget(det, 3)
        gr = Card("Ölçüm Grafiği", margins=(14, 12, 14, 12))
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.12)
        self.curve = self.plot.plot(pen=pg.mkPen(theme.ACCENT, width=2.2))
        dash = pg.mkPen(theme.FAIL, width=1.2, style=Qt.DashLine)
        self.lo = pg.InfiniteLine(angle=0, pen=dash)
        self.hi = pg.InfiniteLine(angle=0, pen=dash)
        for l in (self.lo, self.hi):
            self.plot.addItem(l)
            l.hide()
        gr.lay.addWidget(self.plot)
        right.addWidget(gr, 2)
        self._enable_exports(False)
        self.refresh()

    @staticmethod
    def _style_table(t: QTableWidget, stretch: int):
        hh = t.horizontalHeader()
        for i in range(t.columnCount()):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(stretch, QHeaderView.Stretch)
        t.verticalHeader().hide()
        t.verticalHeader().setDefaultSectionSize(34)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setSelectionMode(QTableWidget.SingleSelection)
        t.setShowGrid(False)
        t.setAlternatingRowColors(True)

    def _enable_exports(self, has_run: bool):
        self.btn_pdf.setEnabled(has_run)
        self.btn_html.setEnabled(has_run)
        self.btn_xlsx.setEnabled(bool(self.runs))

    def refresh(self, *_):
        self.runs = self.ctx.repo.list_runs(300, self.search.text().strip() or None)
        self.runs_tbl.setRowCount(len(self.runs))
        for i, r in enumerate(self.runs):
            vals = [str(r.id), r.started.strftime("%d.%m.%Y %H:%M:%S"), r.serial, r.sequence, r.operator]
            for c, v in enumerate(vals):
                self.runs_tbl.setItem(i, c, QTableWidgetItem(v))
            self.runs_tbl.setItem(i, 5, status_item(r.status))
        self.current = None
        self.steps_tbl.setRowCount(0)
        self._enable_exports(False)

    def on_select(self):
        rows = self.runs_tbl.selectionModel().selectedRows()
        if not rows:
            return
        run = self.ctx.repo.get_run(self.runs[rows[0].row()].id)
        self.current = run
        self.det_title.setText(f"#{run.id} · SN {run.serial} · {run.sequence}")
        steps = sorted(run.steps, key=lambda s: s.idx)
        self.steps_tbl.setRowCount(len(steps))
        for i, s in enumerate(steps):
            val = f"{s.value_num:.4g} {s.unit}" if s.value_num is not None else (s.value_text or "")
            lim = f"{s.low if s.low is not None else '−∞'} … {s.high if s.high is not None else '+∞'}" \
                if (s.low is not None or s.high is not None) else ""
            self.steps_tbl.setItem(i, 0, QTableWidgetItem(s.name))
            self.steps_tbl.setItem(i, 1, status_item(s.status))
            self.steps_tbl.setItem(i, 2, QTableWidgetItem(val))
            self.steps_tbl.setItem(i, 3, QTableWidgetItem(lim))
        self._steps = steps
        self.curve.setData([])
        self.lo.hide()
        self.hi.hide()
        self._enable_exports(True)

    def on_step_select(self):
        rows = self.steps_tbl.selectionModel().selectedRows()
        if not rows or not self.current:
            return
        s = self._steps[rows[0].row()]
        y = np.frombuffer(s.series, dtype="<f8") if s.series else np.array([])
        self.curve.setData(y)
        for line, v in ((self.lo, s.low), (self.hi, s.high)):
            if v is not None:
                line.setValue(v)
                line.show()
            else:
                line.hide()
        self.plot.setTitle(s.name, color=theme.MUTED, size="10pt")

    def export(self, kind: str):
        run = self.current
        try:
            if kind == "xlsx":
                full = [self.ctx.repo.get_run(r.id) for r in self.runs]
                path, _ = QFileDialog.getSaveFileName(self, "Excel kaydet", "test_sonuclari.xlsx", "Excel (*.xlsx)")
                if path:
                    reports.save_excel(full, path)
            else:
                ext = kind
                path, _ = QFileDialog.getSaveFileName(self, "Rapor kaydet", f"rapor_{run.serial}_{run.id}.{ext}",
                                                      f"{ext.upper()} (*.{ext})")
                if not path:
                    return
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    (reports.save_pdf if kind == "pdf" else reports.save_html)(run, path, self.traffic_chk.isChecked())
                finally:
                    QApplication.restoreOverrideCursor()
            if path:
                self.ctx.toast(f"Kaydedildi: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Rapor hatası", str(e))