"""DUT frame codec.

Frame layout (see messageType.txt):
    messageID  : 4 byte
    messageLen : 4 byte (payload length only)
    payload    : n byte
    checksum   : 1 byte (XOR of all preceding bytes)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

# Tek yerden değiştirilebilir protokol ayarları
BYTE_ORDER = "<"  # "<" little endian, ">" big endian
HEADER_SIZE = 8
CHECKSUM_SIZE = 1
_HEADER = struct.Struct(BYTE_ORDER + "II")


class FrameError(ValueError):
    pass


@dataclass
class Frame:
    message_id: int
    payload: bytes = b""


def xor_checksum(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
    return c


def encode(frame: Frame) -> bytes:
    body = _HEADER.pack(frame.message_id, len(frame.payload)) + frame.payload
    return body + bytes([xor_checksum(body)])


def decode(data: bytes) -> Frame:
    if len(data) < HEADER_SIZE + CHECKSUM_SIZE:
        raise FrameError("frame too short")
    msg_id, length = _HEADER.unpack_from(data)
    if len(data) != HEADER_SIZE + length + CHECKSUM_SIZE:
        raise FrameError("length mismatch")
    if xor_checksum(data[:-1]) != data[-1]:
        raise FrameError("checksum mismatch")
    return Frame(msg_id, bytes(data[HEADER_SIZE:HEADER_SIZE + length]))


class StreamDecoder:
    """Parça parça gelen byte akışından tam frame'leri çıkarır."""

    def __init__(self, max_payload: int = 256):
        self._buf = bytearray()
        self._max = max_payload

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        frames: list[Frame] = []
        while len(self._buf) >= HEADER_SIZE:
            _, length = _HEADER.unpack_from(self._buf)
            if length > self._max:
                del self._buf[0]  # bozuk başlık: bir byte kaydır, yeniden senkronize ol
                continue
            total = HEADER_SIZE + length + CHECKSUM_SIZE
            if len(self._buf) < total:
                break
            raw = bytes(self._buf[:total])
            try:
                frames.append(decode(raw))
                del self._buf[:total]
            except FrameError:
                del self._buf[0]
        return frames