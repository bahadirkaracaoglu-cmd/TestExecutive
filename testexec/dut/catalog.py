"""DUT mesaj kataloğu: YAML ile tanımlanan mesajları kodlar/çözer.

Çerçeve (ID | Len | Payload | XOR) `codec` modülünde; burada payload'ın içindeki
alanlar (offset, boyut, tip, enum, ölçek, bit) yönetilir.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from .. import codec

INT_TYPES = {f"{p}{n}": (p == "int", n // 8) for p in ("int", "uint") for n in (8, 16, 24, 32, 40, 48, 56, 64)}
FLOAT_TYPES = {"float32": "f", "float64": "d"}
OTHER_TYPES = {"bytes", "ascii", "bits"}
REST = "rest"  # size: rest -> payload'ın geri kalanı


class CatalogError(ValueError):
    pass


def parse_hex(value: Union[str, bytes, bytearray, list]) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, list):
        return bytes(value)
    s = re.sub(r"(?i)0x|[\s,_:-]", "", str(value))
    try:
        return bytes.fromhex(s)
    except ValueError as e:
        raise CatalogError(f"geçersiz hex değer: {value!r}") from e


@dataclass
class FieldDef:
    name: str
    offset: int
    size: Union[int, str, None] = None
    type: str = "uint8"
    enum: dict[str, int] = field(default_factory=dict)
    bits: dict[str, int] = field(default_factory=dict)
    scale: float = 1.0
    bias: float = 0.0
    unit: str = ""
    default: Any = None
    description: str = ""

    def __post_init__(self):
        t = self.type
        if t not in INT_TYPES and t not in FLOAT_TYPES and t not in OTHER_TYPES:
            raise CatalogError(f"alan '{self.name}': bilinmeyen tip '{t}'")
        if t in INT_TYPES:
            self.size = INT_TYPES[t][1]
        elif t in FLOAT_TYPES:
            self.size = 4 if t == "float32" else 8
        elif t == "bits" and self.size in (None, 0):
            self.size = 1
        if self.size == REST:
            if t not in ("bytes", "ascii"):
                raise CatalogError(f"alan '{self.name}': 'rest' yalnızca bytes/ascii için")
        elif not isinstance(self.size, int) or self.size <= 0:
            raise CatalogError(f"alan '{self.name}': geçersiz boyut {self.size!r}")
        if self.offset < 0:
            raise CatalogError(f"alan '{self.name}': negatif offset")
        self.enum = {str(k): int(v) for k, v in self.enum.items()}
        self.bits = {str(k): int(v) for k, v in self.bits.items()}

    @property
    def is_rest(self) -> bool:
        return self.size == REST

    @property
    def end(self) -> int:
        return self.offset + (0 if self.is_rest else self.size)

    # -- değer <-> bytes --
    def encode(self, value: Any, order: str) -> bytes:
        t = self.type
        if t in INT_TYPES:
            signed = INT_TYPES[t][0]
            raw = self._to_raw_int(value)
            try:
                return raw.to_bytes(self.size, order, signed=signed)
            except OverflowError:
                raise CatalogError(f"alan '{self.name}': {raw} değeri {t} aralığı dışında") from None
        if t in FLOAT_TYPES:
            fmt = ("<" if order == "little" else ">") + FLOAT_TYPES[t]
            return struct.pack(fmt, (float(value) - self.bias) / self.scale)
        if t == "bits":
            return self._bits_to_int(value).to_bytes(self.size, order)
        if t == "ascii":
            data = str(value).encode("ascii")
            return data if self.is_rest else data[:self.size].ljust(self.size, b"\x00")
        data = parse_hex(value)
        if not self.is_rest and len(data) != self.size:
            raise CatalogError(f"alan '{self.name}': {self.size} byte bekleniyor, {len(data)} verildi")
        return data

    def decode(self, data: bytes, order: str) -> tuple[Any, Any]:
        """(kullanıcı değeri, ham değer) döner."""
        t = self.type
        if t in INT_TYPES:
            raw = int.from_bytes(data, order, signed=INT_TYPES[t][0])
            if self.enum:
                for k, v in self.enum.items():
                    if v == raw:
                        return k, raw
                return raw, raw
            if self.scale != 1.0 or self.bias != 0.0:
                return raw * self.scale + self.bias, raw
            return raw, raw
        if t in FLOAT_TYPES:
            fmt = ("<" if order == "little" else ">") + FLOAT_TYPES[t]
            raw = struct.unpack(fmt, data)[0]
            return raw * self.scale + self.bias, raw
        if t == "bits":
            raw = int.from_bytes(data, order)
            if self.bits:
                return {k: bool(raw >> b & 1) for k, b in self.bits.items()}, raw
            return raw, raw
        if t == "ascii":
            return data.rstrip(b"\x00").decode("ascii", errors="replace"), data
        return data, data

    def _to_raw_int(self, value: Any) -> int:
        if isinstance(value, str):
            key = value.strip()
            for k, v in self.enum.items():
                if k.lower() == key.lower():
                    return v
            try:
                return int(key, 0)
            except ValueError:
                raise CatalogError(f"alan '{self.name}': '{value}' enum/sayı değil "
                                   f"(geçerli: {list(self.enum)})") from None
        if self.scale != 1.0 or self.bias != 0.0:
            return int(round((float(value) - self.bias) / self.scale))
        return int(value)

    def _bits_to_int(self, value: Any) -> int:
        if isinstance(value, dict):
            out = 0
            for k, on in value.items():
                if k not in self.bits:
                    raise CatalogError(f"alan '{self.name}': bilinmeyen bit '{k}' (geçerli: {list(self.bits)})")
                if on:
                    out |= 1 << self.bits[k]
            return out
        if isinstance(value, str):
            return int(value, 0)
        return int(value)

    def default_value(self) -> Any:
        if self.default is not None:
            return self.default
        t = self.type
        if t in ("bytes",):
            return b"\x00" * (0 if self.is_rest else self.size)
        if t == "ascii":
            return ""
        if t == "bits":
            return {k: False for k in self.bits} if self.bits else 0
        if self.enum and self.type in INT_TYPES:
            return next(iter(self.enum))
        return 0


@dataclass
class MessageDef:
    name: str
    id: int
    direction: str = "tx"  # tx: DUT'a gönderilen, rx: DUT'tan gelen
    response: Optional[str] = None
    group: str = ""
    description: str = ""
    length: Optional[int] = None  # sabit payload uzunluğu (yoksa alanlardan hesaplanır)
    fields: list[FieldDef] = field(default_factory=list)

    def __post_init__(self):
        if self.direction not in ("tx", "rx", "both"):
            raise CatalogError(f"mesaj '{self.name}': direction tx/rx/both olmalı")
        names = set()
        for f in self.fields:
            if f.name in names:
                raise CatalogError(f"mesaj '{self.name}': '{f.name}' alanı tekrar ediyor")
            names.add(f.name)
        fixed = sorted((f for f in self.fields if not f.is_rest), key=lambda f: f.offset)
        for a, b in zip(fixed, fixed[1:]):
            if b.offset < a.end:
                raise CatalogError(f"mesaj '{self.name}': '{a.name}' ve '{b.name}' alanları çakışıyor")
        rests = [f for f in self.fields if f.is_rest]
        if len(rests) > 1:
            raise CatalogError(f"mesaj '{self.name}': en fazla bir 'rest' alanı olabilir")
        if rests and fixed and rests[0].offset < fixed[-1].end:
            raise CatalogError(f"mesaj '{self.name}': 'rest' alanı diğer alanlardan sonra olmalı")
        if self.length is not None and fixed and fixed[-1].end > self.length:
            raise CatalogError(f"mesaj '{self.name}': alanlar tanımlı length={self.length} değerini aşıyor")

    @property
    def min_length(self) -> int:
        if self.length is not None:
            return self.length
        return max((f.end for f in self.fields), default=0)

    def field(self, name: str) -> FieldDef:
        for f in self.fields:
            if f.name == name:
                return f
        raise CatalogError(f"mesaj '{self.name}': '{name}' alanı yok (alanlar: {[f.name for f in self.fields]})")


@dataclass
class DecodedMessage:
    name: str
    id: int
    values: dict[str, Any]
    raw: dict[str, Any]
    extra: bytes = b""  # kataloğun tanımlamadığı fazla payload byte'ları
    payload: bytes = b""

    def __getitem__(self, k):
        return self.values[k]


class Catalog:
    def __init__(self, name: str = "", byte_order: str = "little"):
        if byte_order not in ("little", "big"):
            raise CatalogError("byte_order little/big olmalı")
        self.name = name
        self.byte_order = byte_order
        self.messages: dict[str, MessageDef] = {}
        self._by_id: dict[int, list[MessageDef]] = {}
        self.presets: dict[str, dict[str, dict[str, Any]]] = {}  # preset -> mesaj -> parametreler

    # ---- yükleme ----
    def add(self, msg: MessageDef) -> None:
        if msg.name in self.messages:
            raise CatalogError(f"mesaj adı tekrar ediyor: {msg.name}")
        self.messages[msg.name] = msg
        self._by_id.setdefault(msg.id, []).append(msg)

    @classmethod
    def from_dict(cls, d: dict, base: Optional["Catalog"] = None) -> "Catalog":
        cat = base or cls(d.get("dut", ""), d.get("byte_order", "little"))
        for name, m in (d.get("messages") or {}).items():
            m = dict(m)
            fields = []
            for fd in m.pop("fields", []) or []:
                fd = dict(fd)
                try:
                    fields.append(FieldDef(**fd))
                except TypeError as e:
                    raise CatalogError(f"mesaj '{name}' alan tanımı hatalı: {e}") from e
            if "id" not in m:
                raise CatalogError(f"mesaj '{name}': id eksik")
            m["id"] = int(m["id"], 0) if isinstance(m["id"], str) else int(m["id"])
            try:
                cat.add(MessageDef(name=name, fields=fields, **m))
            except TypeError as e:
                raise CatalogError(f"mesaj '{name}' tanımı hatalı: {e}") from e
        for pname, content in (d.get("presets") or {}).items():
            cat.presets.setdefault(pname, {}).update(content)
        return cat

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Catalog":
        """Tek YAML dosyası veya bir klasördeki tüm *.yaml dosyaları (gruplara bölünmüş katalog)."""
        p = Path(path)
        files = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
        if not files:
            raise CatalogError(f"katalog dosyası bulunamadı: {path}")
        head = yaml.safe_load(files[0].read_text(encoding="utf-8")) or {}
        cat = cls(head.get("dut", p.stem), head.get("byte_order", "little"))
        for f in files:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            for m in (data.get("messages") or {}).values():
                if isinstance(m, dict):
                    m.setdefault("group", f.stem)
            cls.from_dict(data, cat)
        cat.validate()
        return cat

    def validate(self) -> None:
        for m in self.messages.values():
            if m.response and m.response not in self.messages:
                raise CatalogError(f"mesaj '{m.name}': response '{m.response}' katalogda yok")

    # ---- sorgu ----
    def get(self, name: str) -> MessageDef:
        try:
            return self.messages[name]
        except KeyError:
            raise CatalogError(f"katalogda '{name}' mesajı yok") from None

    def search(self, text: str = "", group: str = "") -> list[MessageDef]:
        t = text.lower()
        return [m for m in self.messages.values()
                if (not group or m.group == group)
                and (not t or t in m.name.lower() or t in m.description.lower() or t == f"0x{m.id:x}")]

    @property
    def groups(self) -> list[str]:
        return sorted({m.group for m in self.messages.values() if m.group})

    # ---- kodlama / çözme ----
    def build_payload(self, msg: MessageDef, params: Optional[dict[str, Any]] = None) -> bytes:
        params = dict(params or {})
        unknown = set(params) - {f.name for f in msg.fields}
        if unknown:
            raise CatalogError(f"mesaj '{msg.name}': bilinmeyen parametre(ler) {sorted(unknown)}")
        buf = bytearray(msg.min_length)
        for f in msg.fields:
            value = params[f.name] if f.name in params else f.default_value()
            data = f.encode(value, self.byte_order)
            if len(buf) < f.offset + len(data):
                buf.extend(b"\x00" * (f.offset + len(data) - len(buf)))
            buf[f.offset:f.offset + len(data)] = data
        return bytes(buf)

    def encode(self, name: str, params: Optional[dict[str, Any]] = None,
               preset: Optional[str] = None) -> codec.Frame:
        msg = self.get(name)
        merged: dict[str, Any] = {}
        if preset:
            if preset not in self.presets:
                raise CatalogError(f"preset '{preset}' yok (mevcut: {list(self.presets)})")
            merged.update(self.presets[preset].get(name, {}))
        merged.update(params or {})
        return codec.Frame(msg.id, self.build_payload(msg, merged))

    def identify(self, message_id: int, direction: Optional[str] = None) -> Optional[MessageDef]:
        cands = self._by_id.get(message_id, [])
        if direction:
            cands = [m for m in cands if m.direction in (direction, "both")] or cands
        return cands[0] if cands else None

    def decode(self, frame: codec.Frame, name: Optional[str] = None) -> DecodedMessage:
        msg = self.get(name) if name else self.identify(frame.message_id, "rx")
        if msg is None:
            raise CatalogError(f"katalogda tanımsız mesaj ID'si: 0x{frame.message_id:X}")
        if msg.id != frame.message_id:
            raise CatalogError(f"ID uyuşmuyor: '{msg.name}' 0x{msg.id:X} bekler, 0x{frame.message_id:X} geldi")
        p = frame.payload
        if len(p) < msg.min_length:
            raise CatalogError(f"'{msg.name}' payload'ı kısa: {len(p)} < {msg.min_length}")
        values: dict[str, Any] = {}
        raw: dict[str, Any] = {}
        covered = 0
        for f in msg.fields:
            end = len(p) if f.is_rest else f.end
            values[f.name], raw[f.name] = f.decode(p[f.offset:end], self.byte_order)
            covered = max(covered, end)
        fixed_len = msg.length if msg.length is not None else covered
        return DecodedMessage(msg.name, msg.id, values, raw, p[max(covered, fixed_len):], p)

    def decode_bytes(self, data: bytes) -> DecodedMessage:
        return self.decode(codec.decode(data))