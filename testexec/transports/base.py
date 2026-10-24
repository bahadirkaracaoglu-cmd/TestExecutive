from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Callable, Optional


class TransportError(Exception):
    pass


class Transport(ABC):
    """Tüm haberleşme kanalları için ortak arayüz.

    Her write/read çağrısı `on_traffic` ile (yön, veri, zaman) olarak bildirilir;
    böylece ham iletişim kaydı tek noktada tutulabilir.
    """

    def __init__(self, name: str = ""):
        self.name = name
        self.on_traffic: Optional[Callable[[str, bytes, float], None]] = None

    def _log(self, direction: str, data: bytes) -> None:
        if self.on_traffic and data:
            self.on_traffic(direction, data, time.time())

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def _write(self, data: bytes) -> None: ...

    @abstractmethod
    def _read(self, size: int, timeout: float) -> bytes:
        """En fazla `size` byte oku; timeout'ta boş bytes dön."""

    def write(self, data: bytes) -> None:
        self._write(data)
        self._log("TX", data)

    def read(self, size: int = 4096, timeout: float = 2.0) -> bytes:
        data = self._read(size, timeout)
        self._log("RX", data)
        return data

    def read_until(self, terminator: bytes = b"\n", timeout: float = 2.0) -> bytes:
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            chunk = self._read(1, max(0.0, deadline - time.monotonic()))
            if chunk:
                buf += chunk
                if buf.endswith(terminator):
                    break
        data = bytes(buf)
        self._log("RX", data)
        return data

    def query(self, data: bytes, terminator: bytes = b"\n", timeout: float = 2.0) -> bytes:
        self.write(data)
        return self.read_until(terminator, timeout)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()