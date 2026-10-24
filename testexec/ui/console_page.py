"""Manuel konsol: operatör kanallara/cihazlara doğrudan mesaj gönderir."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from . import theme
from .widgets import Card


class ConsolePage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 8, 28, 24)
        outer.setSpacing(16)

        card = Card("Manuel Konsol")
        bar = QHBoxLayout()
        self.target = QComboBox()
        self.target.setMinimumWidth(200)
        self.mode = QComboBox()
        self.mode.addItems(["SCPI / Metin (\\n)", "Metin (\\r\\n)", "Metin (sonlandırıcısız)", "HEX", "DUT Çerçevesi (ID + hex payload)"])
        self.mode.setMinimumWidth(260)
        clear = QPushButton("Temizle")
        clear.clicked.connect(lambda: self.out.clear())
        for t, w in (("Hedef", self.target), ("Biçim", self.mode)):
            l = QLabel(t)
            l.setObjectName("muted")
            bar.addWidget(l)
            bar.addWidget(w)
        bar.addStretch()
        bar.addWidget(clear)
        card.lay.addLayout(bar)

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        card.lay.addWidget(self.out, 1)

        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Komut / mesaj yazın ve Enter'a basın — örn: *IDN?   |   DUT çerçevesi için: 0x01 veya 0x10 AABB")
        self.inp.returnPressed.connect(self.send)
        self.send_btn = QPushButton("Gönder")
        self.send_btn.setObjectName("primary")
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.inp, 1)
        row.addWidget(self.send_btn)
        card.lay.addLayout(row)
        outer.addWidget(card, 1)

    def reload_targets(self):
        self.target.clear()
        st = self.ctx.station
        if st and st.connected:
            self.target.addItems(st.transport_names())

    def _print(self, tag: str, text: str, color: str):
        self.out.appendHtml(f"<span style='color:{theme.MUTED}'>{time.strftime('%H:%M:%S')}</span> "
                            f"<b style='color:{color}'>{tag}</b> {text}")

    def send(self):
        st = self.ctx.station
        if not (st and st.connected):
            self._print("!!", "İstasyon bağlı değil.", theme.WARN)
            return
        if self.ctx.run_active:
            self._print("!!", "Test koşarken konsol kullanılamaz.", theme.WARN)
            return
        text = self.inp.text().strip()
        if not text or not self.target.currentText():
            return
        t = st.transport(self.target.currentText())
        mode = self.mode.currentIndex()
        try:
            if mode == 3:
                data = bytes.fromhex(text)
            elif mode == 4:
                from .. import codec
                parts = text.split()
                data = codec.encode(codec.Frame(int(parts[0], 0), bytes.fromhex("".join(parts[1:]))))
            else:
                data = text.encode() + (b"\n" if mode == 0 else b"\r\n" if mode == 1 else b"")
            self._print("TX", data.hex(" ") if mode >= 3 else text, theme.ACCENT)
            t.write(data)
            time.sleep(0.05)
            resp = t.read_until(b"\n", 1.0) if mode in (0, 1, 2) else t.read(512, 1.0)
            if not resp:
                self._print("RX", "(yanıt yok)", theme.MUTED)
            elif mode == 4:
                from .. import codec
                try:
                    for f in codec.StreamDecoder().feed(resp):
                        self._print("RX", f"ID=0x{f.message_id:X} payload={f.payload.hex(' ')}", theme.PASS)
                except Exception:
                    self._print("RX", resp.hex(" "), theme.PASS)
            else:
                self._print("RX", resp.hex(" ") if mode == 3 else resp.decode(errors="replace").strip(), theme.PASS)
        except Exception as e:
            self._print("ERR", f"{type(e).__name__}: {e}", theme.FAIL)
        self.inp.clear()