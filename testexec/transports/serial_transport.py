from __future__ import annotations

from .base import Transport, TransportError


class SerialTransport(Transport):
    def __init__(self, port: str, baudrate: int = 115200, name: str = "serial", **kwargs):
        super().__init__(name)
        self.port, self.baudrate, self.kwargs = port, baudrate, kwargs
        self._ser = None

    def open(self) -> None:
        import serial  # geç import: kurulu değilse diğer kanallar etkilenmesin
        try:
            self._ser = serial.Serial(self.port, self.baudrate, timeout=0.1, **self.kwargs)
        except serial.SerialException as e:
            raise TransportError(f"serial open failed {self.port}: {e}") from e

    def close(self) -> None:
        if self._ser:
            self._ser.close()
            self._ser = None

    def _write(self, data: bytes) -> None:
        if not self._ser:
            raise TransportError("not open")
        self._ser.write(data)
        self._ser.flush()

    def _read(self, size: int, timeout: float) -> bytes:
        if not self._ser:
            raise TransportError("not open")
        self._ser.timeout = max(timeout, 0.001)
        return self._ser.read(size)