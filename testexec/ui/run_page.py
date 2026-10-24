"""Koşu (operatör) sayfası."""
from __future__ import annotations

import threading
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from ..core import RunResult, Sequencer, StepResult
from . import theme
from .widgets import Card, Kpi, page_header, status_item

ROOT = Path(__file__).resolve().parents[2]


class Worker(QObject):
    step_started = Signal(int, str)
    step_done = Signal(int, object)
    sample = Signal(str, float)
    prompt_requested = Signal(str, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, station, seq_path, serial, operator):
        super().__init__()
        self.station, self.seq_path, self.serial, self.operator = station, seq_path, serial, operator
        self._evt = threading.Event()
        self._answer = None

    def answer(self, value):
        self._answer = value
        self._evt.set()

    def _prompt(self, message: str, kind: str):
        self._evt.clear()
        self.prompt_requested.emit(message, kind)
        self._evt.wait()
        return self._answer

    def run(self):
        try:
            st = self.station
            st.on_sample = lambda s, v: self.sample.emit(s, v)
            st.on_prompt = self._prompt
            seq = Sequencer(st)
            seq.on_step_start = lambda i, n: self.step_started.emit(i, n)
            seq.on_step_done = lambda i, r: self.step_done.emit(i, r)
            self.finished.emit(seq.run(Sequencer.load(self.seq_path), self.serial, self.operator))
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class PromptDialog(QDialog):
    def __init__(self, message: str, kind: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Operatör Girişi")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(14)
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size:15px;font-weight:600;")
        lay.addWidget(lbl)
        self.edit = None
        row = QHBoxLayout()
        row.addStretch()
        if kind == "text":
            self.edit = QLineEdit()
            self.edit.setPlaceholderText("Değer girin…")
            self.edit.returnPressed.connect(self.accept)
            lay.addWidget(self.edit)
            ok, no = QPushButton("Tamam"), QPushButton("İptal")
        else:
            ok, no = QPushButton("Evet"), QPushButton("Hayır")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        no.clicked.connect(self.reject)
        row.addWidget(no)
        row.addWidget(ok)
        lay.addLayout(row)


class RunPage(QWidget):
    run_saved = Signal(int)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.steps_spec: list[dict] = []
        self.cur_limits = (None, None)
        self.plot_data: list[float] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 8, 28, 24)
        outer.setSpacing(16)

        # KPI şeridi
        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        self.k_total = Kpi("Toplam Koşu")
        self.k_pass = Kpi("Başarı Oranı")
        self.k_fail = Kpi("Kalan")
        self.k_time = Kpi("Son Süre")
        for k in (self.k_total, self.k_pass, self.k_fail, self.k_time):
            kpis.addWidget(k)
        outer.addLayout(kpis)

        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)

        # --- sol ---
        left = QVBoxLayout()
        left.setSpacing(16)
        body.addLayout(left, 4)

        info = Card("Test Bilgileri")
        self.seq_combo = QComboBox()
        for p in sorted((ROOT / "sequences").glob("*.yaml")):
            self.seq_combo.addItem(p.stem, str(p))
        self.serial_edit = QLineEdit()
        self.serial_edit.setPlaceholderText("Seri numarası (barkod okutun, Enter)")
        self.op_edit = QLineEdit()
        self.op_edit.setPlaceholderText("Operatör adı")
        for text, w in (("Sekans", self.seq_combo), ("Seri No", self.serial_edit), ("Operatör", self.op_edit)):
            l = QLabel(text)
            l.setObjectName("muted")
            info.lay.addWidget(l)
            info.lay.addWidget(w)
        row = QHBoxLayout()
        self.start_btn = QPushButton("▶   BAŞLAT")
        self.start_btn.setObjectName("primary")
        self.stop_btn = QPushButton("■   DURDUR")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        row.addWidget(self.start_btn, 3)
        row.addWidget(self.stop_btn, 2)
        info.lay.addSpacing(6)
        info.lay.addLayout(row)
        left.addWidget(info)

        res = Card("Genel Sonuç")
        self.verdict = QLabel()
        self.verdict.setAlignment(Qt.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.step_lbl = QLabel("")
        self.step_lbl.setObjectName("muted")
        self.step_lbl.setAlignment(Qt.AlignCenter)
        res.lay.addWidget(self.verdict, 1)
        res.lay.addWidget(self.step_lbl)
        res.lay.addWidget(self.progress)
        left.addWidget(res, 1)

        # --- sağ ---
        right = QVBoxLayout()
        right.setSpacing(16)
        body.addLayout(right, 9)

        steps = Card("Test Adımları")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ADIM", "DURUM", "DEĞER", "LİMİT", "SÜRE"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        steps.lay.addWidget(self.table)
        right.addWidget(steps, 5)

        graph = Card("Canlı Veri", margins=(14, 12, 14, 12))
        tabs = QTabWidget()
        pg.setConfigOptions(antialias=True, background=theme.PANEL, foreground=theme.MUTED)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.12)
        self.plot.setLabel("bottom", "Örnek")
        self.curve = self.plot.plot(pen=pg.mkPen(theme.ACCENT, width=2.4),
                                    fillLevel=0, brush=pg.mkBrush(79, 140, 255, 34))
        dash = pg.mkPen(theme.FAIL, width=1.2, style=Qt.DashLine)
        self.line_lo = pg.InfiniteLine(angle=0, pen=dash)
        self.line_hi = pg.InfiniteLine(angle=0, pen=dash)
        self.plot.addItem(self.line_lo)
        self.plot.addItem(self.line_hi)
        self.line_lo.hide()
        self.line_hi.hide()
        tabs.addTab(self.plot, "Canlı Grafik")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        tabs.addTab(self.log, "Olay Günlüğü")
        self.traffic = QPlainTextEdit()
        self.traffic.setReadOnly(True)
        tabs.addTab(self.traffic, "Ham İletişim")
        graph.lay.addWidget(tabs)
        right.addWidget(graph, 5)

        self.seq_combo.currentIndexChanged.connect(self.load_steps)
        self.serial_edit.returnPressed.connect(self.start)
        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self._set_verdict("IDLE")
        self.load_steps()
        self.refresh_kpis()

    # ---- yardımcılar ----
    def _set_verdict(self, status: str):
        c = theme.STATUS_COLORS.get(status, theme.MUTED)
        self.verdict.setText(theme.STATUS_TR.get(status, status))
        self.verdict.setStyleSheet(
            f"font-size:44px;font-weight:800;letter-spacing:3px;color:{c};"
            f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {theme.a(c,'30')},stop:1 {theme.a(c,'0d')});"
            f"border:1px solid {theme.a(c,'66')};border-radius:14px;padding:22px;")

    def refresh_kpis(self):
        counts = self.ctx.repo.status_counts()
        total = sum(counts.values())
        p, f = counts.get("PASS", 0), total - counts.get("PASS", 0)
        self.k_total.set_value(str(total))
        self.k_pass.set_value(f"{100 * p / total:.1f}%" if total else "–",
                              theme.PASS if total and p / total >= .9 else theme.WARN)
        self.k_fail.set_value(str(f), theme.FAIL if f else theme.TEXT)

    def reload_sequences(self, select_path: str | None = None):
        cur = select_path or self.seq_combo.currentData()
        self.seq_combo.blockSignals(True)
        self.seq_combo.clear()
        for p in sorted((ROOT / "sequences").glob("*.yaml")):
            self.seq_combo.addItem(p.stem, str(p))
        if cur:
            i = self.seq_combo.findData(cur)
            if i >= 0:
                self.seq_combo.setCurrentIndex(i)
        self.seq_combo.blockSignals(False)
        self.load_steps()

    def load_steps(self):
        path = self.seq_combo.currentData()
        if not path:
            return
        self.steps_spec = Sequencer.load(path)["steps"]
        self.table.setRowCount(len(self.steps_spec))
        for i, s in enumerate(self.steps_spec):
            lim = s.get("limits", {})
            limtxt = f"{lim.get('min', '−∞')} … {lim.get('max', '+∞')} {lim.get('unit', '')}" if lim else ""
            self.table.setItem(i, 0, QTableWidgetItem(s["name"]))
            self.table.setItem(i, 1, status_item("PENDING"))
            for c, txt in ((2, ""), (3, limtxt), (4, "")):
                self.table.setItem(i, c, QTableWidgetItem(txt))

    def _log(self, msg: str):
        self.log.appendPlainText(msg)

    def set_busy(self, busy: bool):
        self.start_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        self.seq_combo.setEnabled(not busy)
        self.ctx.set_run_active(busy)

    # ---- akış ----
    def start(self):
        if self.thread:
            return
        seq = Sequencer.load(self.seq_combo.currentData())
        needs_serial = not any(s.get("store_as") == "serial" for s in seq["steps"])
        serial = self.serial_edit.text().strip()
        if needs_serial and not serial:
            self.serial_edit.setFocus()
            self._log("Seri numarası gerekli.")
            return
        if not self.ctx.ensure_connected():
            return
        self.load_steps()
        self.progress.setMaximum(len(self.steps_spec))
        self.progress.setValue(0)
        self._set_verdict("RUNNING")
        self.plot_data.clear()
        self.curve.setData([])
        self.traffic.clear()
        self.set_busy(True)
        self._log(f"── Başladı: SN={serial or '(operatörden)'} ──")

        self.worker = Worker(self.ctx.station, self.seq_combo.currentData(), serial, self.op_edit.text().strip())
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.step_started.connect(self.on_step_started)
        self.worker.step_done.connect(self.on_step_done)
        self.worker.sample.connect(self.on_sample)
        self.worker.prompt_requested.connect(self.on_prompt)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.thread.start()

    def stop(self):
        self.ctx.station.cancel()
        self._log("Durdurma istendi…")

    def on_prompt(self, message: str, kind: str):
        dlg = PromptDialog(message, kind, self)
        accepted = dlg.exec() == QDialog.Accepted
        if kind == "text":
            self.worker.answer(dlg.edit.text() if accepted else None)
        else:
            self.worker.answer(bool(accepted))

    def on_step_started(self, idx: int, name: str):
        self.table.setItem(idx, 1, status_item("RUNNING"))
        self.table.selectRow(idx)
        self.step_lbl.setText(name)
        self.plot_data.clear()
        self.curve.setData([])
        lim = self.steps_spec[idx].get("limits", {})
        for line, key in ((self.line_lo, "min"), (self.line_hi, "max")):
            if key in lim:
                line.setValue(lim[key])
                line.show()
            else:
                line.hide()
        self.plot.setTitle(name, color=theme.MUTED, size="10pt")

    def on_sample(self, step: str, v: float):
        self.plot_data.append(v)
        self.curve.setData(self.plot_data)

    def on_step_done(self, idx: int, r: StepResult):
        self.table.setItem(idx, 1, status_item(r.status.value))
        val = f"{r.value:g} {r.unit}" if isinstance(r.value, (int, float)) else (str(r.value) if r.value is not None else "")
        self.table.item(idx, 2).setText(val)
        self.table.item(idx, 4).setText(f"{r.duration:.2f} s")
        self.progress.setValue(idx + 1)
        self._log(f"[{theme.STATUS_TR.get(r.status.value)}] {r.name}  {val}  {r.message}")

    def on_finished(self, run: RunResult):
        rid = self.ctx.repo.save(run)
        self._set_verdict(run.status.value)
        self.step_lbl.setText(f"Kayıt #{rid} · SN {run.serial} · {run.finished - run.started:.1f} s")
        self.k_time.set_value(f"{run.finished - run.started:.1f} s")
        for ts, ch, d, data in run.traffic:
            self.traffic.appendPlainText(f"{ts % 86400:10.3f}  {ch:10} {d}  {data.hex(' ')}")
        self._log(f"── Bitti: {run.status.value} (kayıt #{rid}) ──")
        self._cleanup()
        self.refresh_kpis()
        self.run_saved.emit(rid)
        self.serial_edit.clear()
        self.serial_edit.setFocus()

    def on_failed(self, msg: str):
        self._set_verdict("ERROR")
        self._log(f"HATA: {msg}")
        self._cleanup()

    def _cleanup(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None
        self.set_busy(False)
