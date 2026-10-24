"""DUT Mesajları ve Parametre Düzenleme Sayfası.

Özellikler:
- DUT profili seçme, Excel/CSV'den içe aktarma, Excel şablonu dışa aktarma
- Mesaj arama ve grup filtreleme (yüzlerce mesaj için hızlı erişim)
- Seçili mesajın payload alanlarını (offset, boyut, tip) tablo üzerinde düzenleme:
    * Enum -> Açılır kutu (QComboBox)
    * Bits -> Onay kutuları (QCheckBox)
    * Sayı -> QLineEdit / ölçekli değer
    * Bytes (örn. 2-4. byte init_params) -> Hex düzenleyici
- Canlı çerçeve önizleme: Header (ID + Payload Len) | Payload (seçili alan vurgulu) | XOR Checksum
- Preset (parametre seti) yükleme ve kaydetme
- Seçili kanala doğrudan gönderme ve gelen cevabı alan alan (decoded) tabloda görme
- Katalogdan tek tıkla otomatik test sekansı üretme
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import codec
from ..dut import (Catalog, FieldDef, MessageDef, export_template_excel,
                   generate_sequence_from_catalog, import_catalog, save_catalog_yaml)
from . import theme
from .widgets import Card

ROOT = Path(__file__).resolve().parents[2]


class DutPage(QWidget):
    sequence_created = Signal(str)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.cat: Catalog | None = None
        self.cat_path: Path | None = None
        self.cur_msg: MessageDef | None = None
        self.field_Editors: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 8, 28, 24)
        outer.setSpacing(14)

        # --- Üst araç çubuğu: Profil, Preset, İçe/Dışa Aktarma, Sekans Üretimi ---
        top = QHBoxLayout()
        top.setSpacing(10)
        lbl_prof = QLabel("DUT Profili:")
        lbl_prof.setObjectName("muted")
        self.prof_combo = QComboBox()
        self.prof_combo.setMinimumWidth(200)
        self.prof_combo.currentIndexChanged.connect(self.on_profile_changed)

        btn_import = QPushButton("📥 Excel/CSV İçe Aktar")
        btn_import.clicked.connect(self.import_from_file)
        btn_tpl = QPushButton("📄 Örnek Excel Şablonu")
        btn_tpl.clicked.connect(self.export_template)
        btn_gen_seq = QPushButton("⚡ Otomatik Sekans Üret")
        btn_gen_seq.clicked.connect(self.generate_sequence)

        top.addWidget(lbl_prof)
        top.addWidget(self.prof_combo)
        top.addWidget(btn_import)
        top.addWidget(btn_tpl)
        top.addStretch()
        top.addWidget(btn_gen_seq)
        outer.addLayout(top)

        # --- Ana gövde: Sol (Mesaj Listesi) | Sağ (Parametre Düzenleyici + Çerçeve + Yanıt) ---
        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)

        # Sol Kart: Mesaj Kataloğu
        left_card = Card("Mesaj Kataloğu")
        left_card.setMinimumWidth(340)
        filter_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Mesaj veya ID ara…")
        self.search_edit.textChanged.connect(self.populate_messages)
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(110)
        self.group_combo.currentIndexChanged.connect(self.populate_messages)
        filter_row.addWidget(self.search_edit, 1)
        filter_row.addWidget(self.group_combo)
        left_card.lay.addLayout(filter_row)

        self.msg_tbl = QTableWidget(0, 4)
        self.msg_tbl.setHorizontalHeaderLabels(["MESAJ", "ID", "YÖN", "GRUP"])
        hh = self.msg_tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.msg_tbl.verticalHeader().hide()
        self.msg_tbl.verticalHeader().setDefaultSectionSize(32)
        self.msg_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.msg_tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.msg_tbl.setSelectionMode(QTableWidget.SingleSelection)
        self.msg_tbl.setShowGrid(False)
        self.msg_tbl.setAlternatingRowColors(True)
        self.msg_tbl.itemSelectionChanged.connect(self.on_msg_selected)
        left_card.lay.addWidget(self.msg_tbl, 1)
        split.addWidget(left_card)

        # Sağ taraf
        right_w = QWidget()
        right_lay = QVBoxLayout(right_w)
        right_lay.setContentsMargins(12, 0, 0, 0)
        right_lay.setSpacing(14)
        split.addWidget(right_w)
        split.setSizes([380, 960])

        # Sağ Üst: Payload Parametre Düzenleyici
        param_card = Card("Payload Parametreleri")
        pbar = QHBoxLayout()
        self.msg_title = QLabel("Bir mesaj seçin")
        self.msg_title.setStyleSheet("font-size:15px;font-weight:700;")
        pbar.addWidget(self.msg_title)
        pbar.addStretch()

        lbl_pre = QLabel("Preset:")
        lbl_pre.setObjectName("muted")
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(150)
        self.preset_combo.activated.connect(self.apply_selected_preset)
        btn_save_pre = QPushButton("💾 Preset Kaydet")
        btn_save_pre.clicked.connect(self.save_preset)
        btn_save_def = QPushButton("Varsayılan Yap")
        btn_save_def.clicked.connect(self.save_as_defaults)

        pbar.addWidget(lbl_pre)
        pbar.addWidget(self.preset_combo)
        pbar.addWidget(btn_save_pre)
        pbar.addWidget(btn_save_def)
        param_card.lay.addLayout(pbar)

        self.fields_tbl = QTableWidget(0, 6)
        self.fields_tbl.setHorizontalHeaderLabels(
            ["ALAN ADI", "BYTE ARALIĞI", "TİP", "DEĞER / PARAMETRE", "BİRİM", "HAM HEX (PAYLOAD)"]
        )
        fhh = self.fields_tbl.horizontalHeader()
        fhh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        fhh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        fhh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        fhh.setSectionResizeMode(3, QHeaderView.Stretch)
        fhh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        fhh.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.fields_tbl.verticalHeader().hide()
        self.fields_tbl.verticalHeader().setDefaultSectionSize(38)
        self.fields_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.fields_tbl.setSelectionMode(QTableWidget.NoSelection)
        self.fields_tbl.setShowGrid(False)
        self.fields_tbl.setAlternatingRowColors(True)
        param_card.lay.addWidget(self.fields_tbl, 1)

        # Canlı Çerçeve Önizleme ve Gönderme çubuğu
        frame_bar = QHBoxLayout()
        self.preview_lbl = QLabel("Çerçeve: –")
        self.preview_lbl.setStyleSheet(
            f"font-family:'Cascadia Mono',Consolas,monospace;font-size:12px;"
            f"background:{theme.PANEL2};border:1px solid {theme.BORDER};border-radius:8px;padding:8px 12px;"
        )
        self.preview_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        frame_bar.addWidget(self.preview_lbl, 1)

        lbl_ch = QLabel("Kanal:")
        lbl_ch.setObjectName("muted")
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(110)
        self.send_btn = QPushButton("▶  Mesajı Gönder")
        self.send_btn.setObjectName("primary")
        self.send_btn.clicked.connect(self.send_message)
        frame_bar.addWidget(lbl_ch)
        frame_bar.addWidget(self.target_combo)
        frame_bar.addWidget(self.send_btn)
        param_card.lay.addLayout(frame_bar)
        right_lay.addWidget(param_card, 6)

        # Sağ Alt: Gelen Cevap Çözümleyici
        rx_card = Card("Gelen Cevap (Çözülmüş Alanlar)")
        self.rx_status = QLabel("Henüz mesaj gönderilmedi")
        self.rx_status.setObjectName("muted")
        rx_card.lay.addWidget(self.rx_status)

        self.rx_tbl = QTableWidget(0, 5)
        self.rx_tbl.setHorizontalHeaderLabels(["ALAN ADI", "BYTE ARALIĞI", "ÇÖZÜLEN DEĞER", "HAM DEĞER", "BİRİM"])
        rhh = self.rx_tbl.horizontalHeader()
        rhh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        rhh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        rhh.setSectionResizeMode(2, QHeaderView.Stretch)
        rhh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        rhh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.rx_tbl.verticalHeader().hide()
        self.rx_tbl.verticalHeader().setDefaultSectionSize(34)
        self.rx_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rx_tbl.setShowGrid(False)
        self.rx_tbl.setAlternatingRowColors(True)
        rx_card.lay.addWidget(self.rx_tbl, 1)
        right_lay.addWidget(rx_card, 4)

        self.reload_profiles()

    # ---- Profil ve Katalog Yükleme ----
    def reload_profiles(self):
        prof_dir = ROOT / "dut_profiles"
        prof_dir.mkdir(exist_ok=True)
        self.prof_combo.blockSignals(True)
        self.prof_combo.clear()
        for p in sorted(prof_dir.glob("*.yaml")):
            self.prof_combo.addItem(p.stem, str(p))
        self.prof_combo.blockSignals(False)
        if self.prof_combo.count() > 0:
            self.on_profile_changed()

    def reload_targets(self):
        self.target_combo.clear()
        st = self.ctx.station
        if st and st.connected:
            self.target_combo.addItems(st.transport_names())
            idx = self.target_combo.findText("dut")
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)

    def on_profile_changed(self):
        path_str = self.prof_combo.currentData()
        if not path_str:
            return
        try:
            self.cat_path = Path(path_str)
            self.cat = Catalog.load(self.cat_path)
            if self.ctx.station:
                self.ctx.station.catalog = self.cat
        except Exception as e:
            QMessageBox.critical(self, "Katalog Hatası", str(e))
            return

        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("Tüm Gruplar", "")
        for g in self.cat.groups:
            self.group_combo.addItem(g, g)
        self.group_combo.blockSignals(False)

        self._refresh_presets()
        self.populate_messages()

    def _refresh_presets(self):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("— Varsayılan —", "")
        if self.cat:
            for pname in self.cat.presets:
                self.preset_combo.addItem(pname, pname)
        self.preset_combo.blockSignals(False)

    def populate_messages(self):
        if not self.cat:
            return
        q = self.search_edit.text().strip()
        grp = self.group_combo.currentData() or ""
        msgs = self.cat.search(q, grp)
        self.msg_tbl.setRowCount(len(msgs))
        for i, m in enumerate(msgs):
            it_name = QTableWidgetItem(m.name)
            it_name.setData(Qt.UserRole, m.name)
            it_id = QTableWidgetItem(f"0x{m.id:02X}")
            it_dir = QTableWidgetItem(m.direction.upper())
            it_dir.setForeground(QColor(theme.ACCENT if m.direction == "tx" else theme.PASS))
            it_grp = QTableWidgetItem(m.group)
            for c, it in enumerate((it_name, it_id, it_dir, it_grp)):
                self.msg_tbl.setItem(i, c, it)
        if msgs:
            self.msg_tbl.selectRow(0)
        else:
            self.cur_msg = None
            self.fields_tbl.setRowCount(0)
            self.preview_lbl.setText("Çerçeve: –")

    # ---- Mesaj Seçimi ve Alan Editörleri ----
    def on_msg_selected(self):
        rows = self.msg_tbl.selectionModel().selectedRows()
        if not rows or not self.cat:
            return
        mname = self.msg_tbl.item(rows[0].row(), 0).data(Qt.UserRole)
        self.cur_msg = self.cat.get(mname)
        m = self.cur_msg
        resp_txt = f"  →  Beklenen Cevap: {m.response}" if m.response else ""
        desc_txt = f"  ({m.description})" if m.description else ""
        self.msg_title.setText(f"{m.name} [ID: 0x{m.id:02X}]{resp_txt}{desc_txt}")
        self._build_field_table(m)
        self.update_preview()

    def _build_field_table(self, m: MessageDef, values: dict[str, Any] | None = None):
        self.field_Editors.clear()
        self.fields_tbl.setRowCount(len(m.fields))
        for i, f in enumerate(m.fields):
            val = values[f.name] if (values and f.name in values) else f.default_value()
            byte_range = f"[{f.offset}..*]" if f.is_rest else (
                f"Byte {f.offset}" if f.size == 1 else f"Byte {f.offset}..{f.end - 1} ({f.size}B)"
            )
            it_name = QTableWidgetItem(f.name)
            if f.description:
                it_name.setToolTip(f.description)
            self.fields_tbl.setItem(i, 0, it_name)
            self.fields_tbl.setItem(i, 1, QTableWidgetItem(byte_range))
            self.fields_tbl.setItem(i, 2, QTableWidgetItem(f.type))
            editor = self._make_editor(f, val)
            self.field_Editors[f.name] = editor
            self.fields_tbl.setCellWidget(i, 3, editor)
            self.fields_tbl.setItem(i, 4, QTableWidgetItem(f.unit))
            self.fields_tbl.setItem(i, 5, QTableWidgetItem(""))

    def _make_editor(self, f: FieldDef, val: Any) -> QWidget:
        if f.enum:
            cb = QComboBox()
            for k, v in f.enum.items():
                cb.addItem(f"{k} ({v})", k)
            cb.setStyleSheet("padding: 4px 10px; min-height: 16px;")
            idx = cb.findData(str(val))
            if idx < 0:
                for j, (_, v) in enumerate(f.enum.items()):
                    if v == val:
                        idx = j
                        break
            if idx >= 0:
                cb.setCurrentIndex(idx)
            cb.currentIndexChanged.connect(self.update_preview)
            return cb

        if f.type == "bits" and f.bits:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(4, 0, 4, 0)
            lay.setSpacing(8)
            checks: dict[str, QCheckBox] = {}
            init_dict = val if isinstance(val, dict) else {}
            for bname, bit_idx in f.bits.items():
                chk = QCheckBox(f"{bname}(b{bit_idx})")
                chk.setChecked(bool(init_dict.get(bname, False)))
                chk.stateChanged.connect(self.update_preview)
                lay.addWidget(chk)
                checks[bname] = chk
            lay.addStretch()
            w._bit_checks = checks  # type: ignore[attr-defined]
            return w

        ed = QLineEdit()
        ed.setStyleSheet("padding: 4px 10px; min-height: 16px;")
        if f.type == "bytes":
            hex_str = val.hex(" ").upper() if isinstance(val, (bytes, bytearray)) else str(val)
            ed.setText(hex_str)
            ed.setPlaceholderText(f"{f.size} byte hex (örn: 01 02 03)")
        else:
            ed.setText(str(val))
        ed.textChanged.connect(self.update_preview)
        return ed

    def collect_params(self) -> dict[str, Any]:
        if not self.cur_msg:
            return {}
        params: dict[str, Any] = {}
        for f in self.cur_msg.fields:
            w = self.field_Editors.get(f.name)
            if isinstance(w, QComboBox):
                params[f.name] = w.currentData()
            elif hasattr(w, "_bit_checks"):
                params[f.name] = {k: chk.isChecked() for k, chk in w._bit_checks.items()}
            elif isinstance(w, QLineEdit):
                txt = w.text().strip()
                if f.type in ("bytes", "ascii"):
                    params[f.name] = txt
                elif f.type.startswith("float") or f.scale != 1.0:
                    params[f.name] = float(txt or 0)
                else:
                    params[f.name] = int(txt or "0", 0)
        return params

    def update_preview(self):
        if not self.cat or not self.cur_msg:
            return
        try:
            params = self.collect_params()
            for i, f in enumerate(self.cur_msg.fields):
                raw_b = f.encode(params[f.name], self.cat.byte_order)
                it = self.fields_tbl.item(i, 5)
                if it:
                    it.setText(raw_b.hex(" ").upper())
            frame = self.cat.encode(self.cur_msg.name, params)
            raw_frame = codec.encode(frame)
            id_hex = raw_frame[:4].hex(" ").upper()
            len_hex = raw_frame[4:8].hex(" ").upper()
            pay_hex = frame.payload.hex(" ").upper() or "(boş)"
            xor_hex = f"{raw_frame[-1]:02X}"
            self.preview_lbl.setText(
                f"<span style='color:{theme.MUTED}'>ID(4B):</span> <b>{id_hex}</b>   "
                f"<span style='color:{theme.MUTED}'>Len(4B={len(frame.payload)}):</span> <b>{len_hex}</b>   "
                f"<span style='color:{theme.MUTED}'>Payload:</span> <b style='color:{theme.ACCENT}'>{pay_hex}</b>   "
                f"<span style='color:{theme.MUTED}'>XOR(1B):</span> <b style='color:{theme.PASS}'>{xor_hex}</b>"
            )
        except Exception as e:
            self.preview_lbl.setText(f"<span style='color:{theme.FAIL}'>Hata: {e}</span>")

    # ---- Preset ve Varsayılan Kayıt ----
    def apply_selected_preset(self):
        if not self.cat or not self.cur_msg:
            return
        pname = self.preset_combo.currentData()
        if not pname:
            self._build_field_table(self.cur_msg)
        else:
            vals = self.cat.presets.get(pname, {}).get(self.cur_msg.name, {})
            self._build_field_table(self.cur_msg, vals)
        self.update_preview()

    def save_preset(self):
        if not self.cat or not self.cur_msg or not self.cat_path:
            return
        name, ok = QInputDialog.getText(self, "Preset Kaydet", "Preset adı (örn. fabrika_init):")
        name = name.strip()
        if not ok or not name:
            return
        try:
            params = self.collect_params()
            self.cat.presets.setdefault(name, {})[self.cur_msg.name] = params
            save_catalog_yaml(self.cat, self.cat_path)
            self._refresh_presets()
            self.preset_combo.setCurrentText(name)
            self.ctx.toast(f"Preset '{name}' kaydedildi ({self.cat_path.name})")
        except Exception as e:
            QMessageBox.critical(self, "Preset Hatası", str(e))

    def save_as_defaults(self):
        if not self.cat or not self.cur_msg or not self.cat_path:
            return
        try:
            params = self.collect_params()
            for f in self.cur_msg.fields:
                if f.name in params:
                    f.default = params[f.name]
            save_catalog_yaml(self.cat, self.cat_path)
            self.ctx.toast(f"{self.cur_msg.name} varsayılan parametreleri güncellendi.")
        except Exception as e:
            QMessageBox.critical(self, "Kayıt Hatası", str(e))

    # ---- Mesaj Gönderme ve Cevap Çözümleme ----
    def send_message(self):
        if not self.cat or not self.cur_msg:
            return
        if self.ctx.run_active:
            QMessageBox.warning(self, "Meşgul", "Test koşusu devam ederken manuel mesaj gönderilemez.")
            return
        if not self.ctx.ensure_connected():
            return
        tname = self.target_combo.currentText()
        if not tname:
            self.reload_targets()
            tname = self.target_combo.currentText()
        if not tname:
            QMessageBox.warning(self, "Kanal Yok", "Aktif haberleşme kanalı bulunamadı.")
            return

        try:
            params = self.collect_params()
            out_frame = self.cat.encode(self.cur_msg.name, params)
            raw_bytes = codec.encode(out_frame)
            t = self.ctx.station.transport(tname)
            t.write(raw_bytes)

            dec = codec.StreamDecoder()
            deadline = time.monotonic() + 1.0
            frames = []
            while not frames and time.monotonic() < deadline:
                frames = dec.feed(t.read(256, 0.05))

            if not frames:
                self.rx_status.setText(f"TX {self.cur_msg.name} gönderildi — Yanıt gelmedi (timeout)")
                self.rx_status.setStyleSheet(f"color:{theme.WARN};font-weight:600;")
                self.rx_tbl.setRowCount(0)
                return

            rx_f = frames[0]
            decoded = self.cat.decode(rx_f, name=self.cur_msg.response)
            rx_def = self.cat.get(decoded.name)
            self.rx_status.setText(
                f"✓ Yanıt: {decoded.name} (ID: 0x{decoded.id:02X}, {len(rx_f.payload)} byte) — "
                f"Ham: {rx_f.payload.hex(' ').upper()}"
            )
            self.rx_status.setStyleSheet(f"color:{theme.PASS};font-weight:600;")
            self.rx_tbl.setRowCount(len(rx_def.fields))
            for i, rf in enumerate(rx_def.fields):
                rng = f"[{rf.offset}..*]" if rf.is_rest else (
                    f"Byte {rf.offset}" if rf.size == 1 else f"Byte {rf.offset}..{rf.end - 1}"
                )
                val = decoded.values.get(rf.name)
                raw_v = decoded.raw.get(rf.name)
                val_s = val.hex(" ").upper() if isinstance(val, bytes) else (
                    f"{val:.4g}" if isinstance(val, float) else str(val)
                )
                raw_s = raw_v.hex(" ").upper() if isinstance(raw_v, bytes) else str(raw_v)
                self.rx_tbl.setItem(i, 0, QTableWidgetItem(rf.name))
                self.rx_tbl.setItem(i, 1, QTableWidgetItem(rng))
                it_val = QTableWidgetItem(val_s)
                it_val.setForeground(QColor(theme.ACCENT))
                self.rx_tbl.setItem(i, 2, it_val)
                self.rx_tbl.setItem(i, 3, QTableWidgetItem(raw_s))
                self.rx_tbl.setItem(i, 4, QTableWidgetItem(rf.unit))
        except Exception as e:
            self.rx_status.setText(f"Hata: {e}")
            self.rx_status.setStyleSheet(f"color:{theme.FAIL};font-weight:600;")

    # ---- Excel/CSV İçe Aktarma ve Otomatik Sekans ----
    def import_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Mesaj Tablosu Seç", str(ROOT), "Tablolar (*.xlsx *.xlsm *.csv)"
        )
        if not path:
            return
        dut_name, ok = QInputDialog.getText(self, "DUT Adı", "Yeni DUT profili adı:", text=Path(path).stem)
        if not ok or not dut_name.strip():
            return
        try:
            cat = import_catalog(path, dut_name=dut_name.strip())
            out_path = ROOT / "dut_profiles" / f"{dut_name.strip()}.yaml"
            save_catalog_yaml(cat, out_path)
            self.reload_profiles()
            idx = self.prof_combo.findText(dut_name.strip())
            if idx >= 0:
                self.prof_combo.setCurrentIndex(idx)
            self.ctx.toast(f"'{dut_name}' profili ({len(cat.messages)} mesaj) içe aktarıldı.")
        except Exception as e:
            QMessageBox.critical(self, "İçe Aktarma Hatası", str(e))

    def export_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Örnek Excel Şablonu Kaydet", str(ROOT / "dut_mesaj_sablonu.xlsx"), "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            export_template_excel(path, self.cat)
            self.ctx.toast(f"Excel şablonu kaydedildi: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Şablon Hatası", str(e))

    def generate_sequence(self):
        if not self.cat or not self.cat_path:
            return
        grp = self.group_combo.currentData() or ""
        preset = self.preset_combo.currentData() or ""
        rel_prof = f"dut_profiles/{self.cat_path.name}"
        seq = generate_sequence_from_catalog(
            self.cat, transport=self.target_combo.currentText() or "dut",
            group=grp, preset=preset, dut_profile_path=rel_prof,
        )
        if not seq["steps"]:
            QMessageBox.information(self, "Bilgi", "Seçili filtrede gönderilecek (TX) mesaj yok.")
            return
        out_name = f"auto_{self.cat_path.stem}" + (f"_{grp}" if grp else "") + ".yaml"
        out_path = ROOT / "sequences" / out_name
        out_path.write_text(yaml.safe_dump(seq, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.sequence_created.emit(str(out_path))
        self.ctx.toast(f"{len(seq['steps'])} adımlı sekans üretildi: sequences/{out_name}")