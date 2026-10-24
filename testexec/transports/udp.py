from __future__ import annotations

import socket

from .base import Transport, TransportError


class UdpTransport(Transport):
    def __init__(self, host: str, port: int, local_port: int = 0, name: str = "udp"):
        super().__init__(name)
        self.host, self.port, self.local_port = host, port, local_port
        self._sock: socket.socket | None = None
        self._pending = bytearray()

    def open(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.local_port:
            self._sock.bind(("", self.local_port))

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def _write(self, data: bytes) -> None:
        if not self._sock:
            raise TransportError("not open")
        self._sock.sendto(data, (self.host, self.port))

    def _read(self, size: int, timeout: float) -> bytes:
        if not self._sock:
            raise TransportError("not open")
        if not self._pending:
            self._sock.settimeout(max(timeout, 0.001))
            try:
                data, _ = self._sock.recvfrom(65535)
            except socket.timeout:
                return b""
            self._pending += data
        out = bytes(self._pending[:size])
        del self._pending[:size]
        return out