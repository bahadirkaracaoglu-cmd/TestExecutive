"""SCPI cihaz sürücüleri.

Genel SCPI sınıfları (PowerSupply, Dmm, ElectronicLoad) standart komutları kullanır.
Üreticiye özel farklar alt sınıflarda ezilir ve `*IDN?` yanıtına göre otomatik seçilir.
"""
from __future__ import annotations

import re
from typing import Optional, Type

from ..transports.base import Transport


class ScpiError(Exception):
    pass


class ScpiInstrument:
    def __init__(self, transport: Transport, name: str = "", term: bytes = b"\n"):
        self.t = transport
        self.name = name
        self.term = term

    # --- düşük seviye ---
    def write(self, cmd: str) -> None:
        self.t.write(cmd.encode() + self.term)

    def query(self, cmd: str, timeout: float = 2.0) -> str:
        raw = self.t.query(cmd.encode() + self.term, terminator=self.term, timeout=timeout)
        if not raw:
            raise ScpiError(f"{self.name}: no response to '{cmd}'")
        return raw.decode(errors="replace").strip()

    def query_float(self, cmd: str, timeout: float = 2.0) -> float:
        return float(self.query(cmd, timeout))

    # --- IEEE 488.2 ortak komutlar ---
    def idn(self) -> str:
        return self.query("*IDN?")

    def reset(self) -> None:
        self.write("*RST")
        self.write("*CLS")

    def opc(self, timeout: float = 5.0) -> None:
        self.query("*OPC?", timeout)

    def error(self) -> str:
        return self.query("SYST:ERR?")

    def check_errors(self) -> None:
        err = self.error()
        if not err.startswith(("0", "+0")):
            raise ScpiError(f"{self.name}: {err}")


class PowerSupply(ScpiInstrument):
    def set_voltage(self, v: float) -> None:
        self.write(f"VOLT {v}")

    def set_current_limit(self, a: float) -> None:
        self.write(f"CURR {a}")

    def output(self, on: bool) -> None:
        self.write(f"OUTP {'ON' if on else 'OFF'}")

    def measure_voltage(self) -> float:
        return self.query_float("MEAS:VOLT?")

    def measure_current(self) -> float:
        return self.query_float("MEAS:CURR?")


class TdkLambdaPsu(PowerSupply):
    """TDK-Lambda Genesys/Z+ (SCPI uyumlu); kısa komut takma adları kullanır."""

    def set_voltage(self, v: float) -> None:
        self.write(f":VOLT {v}")

    def set_current_limit(self, a: float) -> None:
        self.write(f":CURR {a}")

    def output(self, on: bool) -> None:
        self.write(f":OUTP:STAT {1 if on else 0}")

    def measure_voltage(self) -> float:
        return self.query_float(":MEAS:VOLT?")

    def measure_current(self) -> float:
        return self.query_float(":MEAS:CURR?")


class Dmm(ScpiInstrument):
    def measure_dc_voltage(self) -> float:
        return self.query_float("MEAS:VOLT:DC?")

    def measure_dc_current(self) -> float:
        return self.query_float("MEAS:CURR:DC?")

    def measure_resistance(self) -> float:
        return self.query_float("MEAS:RES?")


class ElectronicLoad(ScpiInstrument):
    def set_current(self, a: float) -> None:
        self.write("FUNC CURR")
        self.write(f"CURR {a}")

    def input(self, on: bool) -> None:
        self.write(f"INP {'ON' if on else 'OFF'}")


# --- Sürücü kayıt defteri ---
_REGISTRY: dict[str, Type[ScpiInstrument]] = {
    "psu": PowerSupply,
    "dmm": Dmm,
    "load": ElectronicLoad,
    "tdk_lambda_psu": TdkLambdaPsu,
    "scpi": ScpiInstrument,
}


def register_driver(kind: str, cls: Type[ScpiInstrument]) -> None:
    _REGISTRY[kind] = cls


def create_instrument(kind: str, transport: Transport, name: str = "") -> ScpiInstrument:
    try:
        return _REGISTRY[kind](transport, name)
    except KeyError:
        raise ScpiError(f"unknown instrument type '{kind}'; known: {sorted(_REGISTRY)}")


# *IDN? üretici → sürücü eşlemesi (genel tür verildiğinde otomatik iyileştirme için)
_IDN_OVERRIDES = [(re.compile(r"TDK|LAMBDA", re.I), {"psu": TdkLambdaPsu})]


def refine_by_idn(inst: ScpiInstrument) -> ScpiInstrument:
    idn = inst.idn()
    for pat, mapping in _IDN_OVERRIDES:
        if pat.search(idn):
            for base, special in mapping.items():
                if isinstance(inst, _REGISTRY[base]) and not isinstance(inst, special):
                    return special(inst.t, inst.name, inst.term)
    return inst