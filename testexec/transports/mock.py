from __future__ import annotations

from typing import Callable, Optional

from .base import Transport


class MockTransport(Transport):
    """Donanımsız geliştirme/test için sahte kanal.

    `responder(bytes) -> bytes` yazılan her veriye verilecek yanıtı üretir.
    """

    def __init__(self, responder: Optional[Callable[[bytes], bytes]] = None, name: str = "mock"):
        super().__init__(name)
        self.responder = responder or (lambda d: b"")
        self._rx = bytearray()
        self.sent: list[bytes] = []
        self.is_open = False

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def _write(self, data: bytes) -> None:
        self.sent.append(data)
        self._rx += self.responder(data)

    def _read(self, size: int, timeout: float) -> bytes:
        out = bytes(self._rx[:size])
        del self._rx[:size]
        return out