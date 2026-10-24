"""Ana pencere: kenar çubuğu + sayfalar + istasyon yönetimi."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPushButton, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from ..core import Station
from ..db import Repository
from . import theme
from .console_page import ConsolePage
from .dut_page import DutPage
from .history_page import HistoryPage
from .run_page import RunPage
from .stats_page import StatsPage
from .widgets import StatusDot

ROOT = Path(__file__).resolve().parents[2]

PAGES = [("▶", "Koşu", "Test Koşusu", "Testi başlatın, adımları ve canlı veriyi izleyin"),
         ("☰", "Geçmiş", "Geçmiş Sonuçlar", "Kayıtlı koşular, adım detayları ve rapor üretimi"),
         ("◔", "İstatistik", "İstatistik ve Trend", "Ölçüm dağılımı, trend ve süreç yeterliliği (Cp/Cpk)"),
         ("⇄", "Mesajlar", "DUT Mesajları ve Parametreler", "Mesaj kataloğu, payload parametre düzenleyici, preset ve otomatik sekans"),
         ("⌨", "Konsol", "Manuel Konsol", "Kanallara doğrudan mesaj gönderin, yanıtları okuyun")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Executive")
        self.resize(1480, 900)
        self.repo = Repository(f"sqlite:///{ROOT / 'testexec.db'}")
        self.station: Station | None = None
        self.run_active = False

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # --- kenar çubuğu ---
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(88)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 16, 10, 16)
        sl.setSpacing(6)
        logo = QLabel("TX")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        sl.addWidget(logo)
        sl.addSpacing(16)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, (icon, label, *_r) in enumerate(PAGES):
            b = QToolButton()
            b.setObjectName("nav")
            b.setText(f"{icon}\n{label}")
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setMinimumHeight(64)
            b.setSizePolicy(b.sizePolicy().horizontalPolicy(), b.sizePolicy().verticalPolicy())
            b.setStyleSheet("font-size:12px;")
            b.setFixedWidth(68)
            self.group.addButton(b, i)
            sl.addWidget(b)
        sl.addStretch()
        h.addWidget(side)

        # --- içerik ---
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        h.addLayout(content, 1)

        header = QWidget()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 20, 28, 12)
        hl.setSpacing(10)
        tbox = QVBoxLayout()
        tbox.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.sub = QLabel()
        self.sub.setObjectName("pageSub")
        tbox.addWidget(self.title)
        tbox.addWidget(self.sub)
        hl.addLayout(tbox)
        hl.addStretch()
        self.chips_box = QHBoxLayout()
        self.chips_box.setSpacing(8)
        hl.addLayout(self.chips_box)
        self.station_combo = QComboBox()
        for p in sorted((ROOT / "stations").glob("*.yaml")):
            self.station_combo.addItem(p.stem, str(p))
        self.station_combo.setMinimumWidth(190)
        self.connect_btn = QPushButton("Bağlan")
        self.connect_btn.clicked.connect(self.toggle_connection)
        hl.addWidget(self.station_combo)
        hl.addWidget(self.connect_btn)
        content.addWidget(header)

        self.stack = QStackedWidget()
        self.run_page = RunPage(self)
        self.history_page = HistoryPage(self)
        self.stats_page = StatsPage(self)
        self.dut_page = DutPage(self)
        self.console_page = ConsolePage(self)
        for p in (self.run_page, self.history_page, self.stats_page, self.dut_page, self.console_page):
            self.stack.addWidget(p)
        content.addWidget(self.stack, 1)

        self.toast_lbl = QLabel("")
        self.toast_lbl.setStyleSheet(f"background:{theme.PANEL3};border-top:1px solid {theme.BORDER};padding:6px 28px;color:{theme.MUTED};")
        content.addWidget(self.toast_lbl)

        self.group.idClicked.connect(self.goto)
        self.run_page.run_saved.connect(lambda _id: (self.history_page.refresh(), self.stats_page.refresh()))
        self.dut_page.sequence_created.connect(lambda p: self.run_page.reload_sequences(p))
        self.group.button(0).setChecked(True)
        self.goto(0)
        self.chips: dict[str, StatusDot] = {}
        QTimer.singleShot(200, self.connect_station)

    # ---- sayfa gezinme ----
    def goto(self, i: int):
        self.stack.setCurrentIndex(i)
        _, _, title, sub = PAGES[i]
        self.title.setText(title)
        self.sub.setText(sub)
        if i == 1:
            self.history_page.refresh()
        elif i == 2:
            self.stats_page.refresh()
        elif i == 3:
            self.dut_page.reload_targets()
        elif i == 4:
            self.console_page.reload_targets()

    def toast(self, msg: str):
        self.toast_lbl.setText(msg)

    # ---- istasyon bağlantısı ----
    def _rebuild_chips(self):
        while self.chips_box.count():
            w = self.chips_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.chips = {}
        if self.station:
            for name in self.station.transport_names():
                chip = StatusDot(name)
                chip.set_state(True)
                self.chips[name] = chip
                self.chips_box.addWidget(chip)

    def connect_station(self):
        path = self.station_combo.currentData()
        if not path:
            return
        try:
            st = Station.from_file(path)
            st.open()
        except Exception as e:
            QMessageBox.critical(self, "Bağlantı hatası", f"{type(e).__name__}: {e}")
            self.toast(f"Bağlantı başarısız: {e}")
            return
        self.station = st
        self._rebuild_chips()
        self.connect_btn.setText("Bağlantıyı Kes")
        self.station_combo.setEnabled(False)
        self.toast(f"{st.name} bağlı ({len(st.transport_names())} kanal)")
        self.dut_page.reload_targets()
        self.console_page.reload_targets()

    def disconnect_station(self):
        if self.station:
            self.station.close()
        self._rebuild_chips()
        self.connect_btn.setText("Bağlan")
        self.station_combo.setEnabled(True)
        self.toast("Bağlantı kesildi")
        self.dut_page.reload_targets()
        self.console_page.reload_targets()

    def toggle_connection(self):
        if self.run_active:
            return
        if self.station and self.station.connected:
            self.disconnect_station()
        else:
            self.connect_station()

    def ensure_connected(self) -> bool:
        if not (self.station and self.station.connected):
            self.connect_station()
        return bool(self.station and self.station.connected)

    def set_run_active(self, busy: bool):
        self.run_active = busy
        self.connect_btn.setEnabled(not busy)

    def closeEvent(self, e):
        if self.station:
            self.station.close()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.QSS)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())