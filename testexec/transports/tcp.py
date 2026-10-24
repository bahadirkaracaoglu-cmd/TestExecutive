from __future__ import annotations

import socket

from .base import Transport, TransportError


class TcpTransport(Transport):
    def __init__(self, host: str, port: int, name: str = "tcp", connect_timeout: float = 3.0):
        super().__init__(name)
        self.host, self.port, self.connect_timeout = host, port, connect_timeout
        self._sock: socket.socket | None = None

    def open(self) -> None:
        try:
            self._sock = socket.create_connection((self.host, self.port), self.connect_timeout)
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as e:
            raise TransportError(f"TCP connect failed {self.host}:{self.port}: {e}") from e

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def _write(self, data: bytes) -> None:
        if not self._sock:
            raise TransportError("not open")
        self._sock.sendall(data)

    def _read(self, size: int, timeout: float) -> bytes:
        if not self._sock:
            raise TransportError("not open")
        self._sock.settimeout(max(timeout, 0.001))
        try:
            return self._sock.recv(size)
        except socket.timeout:
            return b""