from __future__ import annotations

from .base import Transport, TransportError


class VisaTransport(Transport):
    """PyVISA üzerinden USB/LAN(VXI-11, HiSLIP, SOCKET)/GPIB/Serial cihazlar.

    resource örnekleri: "TCPIP0::192.168.1.10::INSTR", "USB0::0x2A8D::0x0101::MY123::INSTR"
    """

    def __init__(self, resource: str, name: str = "visa", timeout_ms: int = 5000,
                 backend: str = "", read_termination: str = "\n", write_termination: str = "\n"):
        super().__init__(name)
        self.resource, self.timeout_ms, self.backend = resource, timeout_ms, backend
        self.read_termination, self.write_termination = read_termination, write_termination
        self._rm = None
        self._inst = None

    def open(self) -> None:
        import pyvisa
        try:
            self._rm = pyvisa.ResourceManager(self.backend) if self.backend else pyvisa.ResourceManager()
            self._inst = self._rm.open_resource(self.resource)
            self._inst.timeout = self.timeout_ms
            self._inst.read_termination = self.read_termination
            self._inst.write_termination = self.write_termination
        except Exception as e:
            raise TransportError(f"VISA open failed {self.resource}: {e}") from e

    def close(self) -> None:
        if self._inst:
            self._inst.close()
            self._inst = None
        if self._rm:
            self._rm.close()
            self._rm = None

    def _write(self, data: bytes) -> None:
        if not self._inst:
            raise TransportError("not open")
        self._inst.write_raw(data)

    def _read(self, size: int, timeout: float) -> bytes:
        if not self._inst:
            raise TransportError("not open")
        import pyvisa
        self._inst.timeout = max(int(timeout * 1000), 1)
        try:
            return bytes(self._inst.read_bytes(size, break_on_termchar=True))
        except pyvisa.VisaIOError:
            return b""

    def query(self, data: bytes, terminator: bytes = b"\n", timeout: float = 2.0) -> bytes:
        # VISA kendi sonlandırıcısını yönetir; SCPI için doğrudan query kullan.
        if not self._inst:
            raise TransportError("not open")
        text = data.decode().rstrip("\r\n")
        self._log("TX", data)
        self._inst.timeout = max(int(timeout * 1000), 1)
        resp = self._inst.query(text).encode()
        self._log("RX", resp)
        return resp