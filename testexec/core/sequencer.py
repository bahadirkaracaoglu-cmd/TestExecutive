from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

import yaml

from ..dut import Catalog
from ..instruments import create_instrument, refine_by_idn
from ..instruments.scpi import ScpiInstrument
from ..transports import (MockTransport, SerialTransport, TcpTransport, Transport,
                          UdpTransport, VisaTransport)
from .models import RunResult, Status, StepResult
from .steps import STEP_TYPES


class Cancelled(Exception):
    pass


def build_transport(name: str, spec: dict) -> Transport:
    kind = spec["type"]
    if kind == "tcp":
        return TcpTransport(spec["host"], spec["port"], name)
    if kind == "udp":
        return UdpTransport(spec["host"], spec["port"], spec.get("local_port", 0), name)
    if kind == "serial":
        return SerialTransport(spec["port"], spec.get("baudrate", 115200), name)
    if kind == "visa":
        return VisaTransport(spec["resource"], name)
    if kind == "mock":
        from ..simulators import make_responder
        return MockTransport(make_responder(spec.get("profile", "scpi")), name)
    raise ValueError(f"unknown transport type '{kind}'")


class Station:
    """Test istasyonu: kaynakları (kanallar + cihazlar) yönetir."""

    def __init__(self, config: dict):
        self.name = config.get("station", "station-1")
        self._transports: dict[str, Transport] = {}
        self._instruments: dict[str, ScpiInstrument] = {}
        self.catalog: Optional[Catalog] = None
        if config.get("dut_profile"):
            self.catalog = Catalog.load(config["dut_profile"])
        self._cfg = config
        self._cancel = threading.Event()
        self.on_sample: Optional[Callable[[str, float], None]] = None
        self.on_traffic: Optional[Callable[[str, str, bytes, float], None]] = None
        # Operatör etkileşimi: (mesaj, tür["text"|"confirm"]) -> str | bool | None(iptal)
        self.on_prompt: Optional[Callable[[str, str], object]] = None
        self.vars: dict[str, str] = {}  # sekans boyunca paylaşılan değişkenler

    def prompt(self, message: str, kind: str = "text"):
        if not self.on_prompt:
            raise RuntimeError("operatör girişi için arayüz tanımlı değil")
        return self.on_prompt(message, kind)

    @classmethod
    def from_file(cls, path: str | Path) -> "Station":
        return cls(yaml.safe_load(Path(path).read_text(encoding="utf-8")))

    def open(self) -> None:
        for name, spec in self._cfg.get("transports", {}).items():
            t = build_transport(name, spec)
            t.on_traffic = lambda d, data, ts, n=name: self.on_traffic and self.on_traffic(n, d, data, ts)
            t.open()
            self._transports[name] = t
        for name, spec in self._cfg.get("instruments", {}).items():
            inst = create_instrument(spec["type"], self._transports[spec["transport"]], name)
            if spec.get("auto_idn", True):
                try:
                    inst = refine_by_idn(inst)
                except Exception:
                    pass
            self._instruments[name] = inst

    def close(self) -> None:
        for t in self._transports.values():
            try:
                t.close()
            except Exception:
                pass
        self._transports.clear()
        self._instruments.clear()

    def transport_names(self) -> list[str]:
        return list(self._transports)

    @property
    def connected(self) -> bool:
        return bool(self._transports)

    def transport(self, name: str) -> Transport:
        return self._transports[name]

    def instrument(self, name: str) -> ScpiInstrument:
        return self._instruments[name]

    def emit_sample(self, step: str, value: float) -> None:
        if self.on_sample:
            self.on_sample(step, value)

    def cancel(self) -> None:
        self._cancel.set()

    def check_cancel(self) -> None:
        if self._cancel.is_set():
            raise Cancelled()

    def reset_cancel(self) -> None:
        self._cancel.clear()


class Sequencer:
    """YAML sekansını koşturur. UI veya CLI'dan, ayrı thread içinde çağrılabilir."""

    def __init__(self, station: Station):
        self.station = station
        self.on_step_start: Optional[Callable[[int, str], None]] = None
        self.on_step_done: Optional[Callable[[int, StepResult], None]] = None

    @staticmethod
    def load(path: str | Path) -> dict:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    def run(self, seq: dict, serial: str, operator: str = "") -> RunResult:
        st = self.station
        st.reset_cancel()
        st.vars.clear()
        if seq.get("dut_profile"):
            st.catalog = Catalog.load(seq["dut_profile"])
        run = RunResult(seq.get("sequence", "?"), serial, operator, st.name)
        st.on_traffic = lambda ch, d, data, ts: run.traffic.append((ts, ch, d, data))
        run.status = Status.RUNNING
        stop = False
        for idx, spec in enumerate(seq["steps"]):
            res = StepResult(spec["name"])
            run.steps.append(res)
            if stop:
                res.status = Status.SKIPPED
                if self.on_step_done:
                    self.on_step_done(idx, res)
                continue
            if self.on_step_start:
                self.on_step_start(idx, res.name)
            res.status = Status.RUNNING
            res.started = time.time()
            retries = int(spec.get("retries", 0))
            for attempt in range(retries + 1):
                res.series.clear()
                res.message = ""
                try:
                    STEP_TYPES[spec["type"]](spec, st, res)
                except Cancelled:
                    res.status, res.message = Status.ERROR, "iptal edildi"
                    stop = True
                    break
                except Exception as e:  # cihaz/iletişim hatası
                    res.status, res.message = Status.ERROR, f"{type(e).__name__}: {e}"
                if res.status == Status.PASS:
                    break
            res.duration = time.time() - res.started
            if res.status in (Status.FAIL, Status.ERROR) and spec.get("on_fail", "stop") == "stop":
                stop = True
            if self.on_step_done:
                self.on_step_done(idx, res)
        run.finished = time.time()
        if st.vars.get("serial"):
            run.serial = st.vars["serial"]
        statuses = [s.status for s in run.steps]
        if Status.ERROR in statuses:
            run.status = Status.ERROR
        elif Status.FAIL in statuses:
            run.status = Status.FAIL
        else:
            run.status = Status.PASS
        st.on_traffic = None
        return run