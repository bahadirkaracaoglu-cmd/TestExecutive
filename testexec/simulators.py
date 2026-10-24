"""Donanımsız demo/test için sahte DUT ve SCPI cihaz yanıtlayıcıları."""
from __future__ import annotations

import random
from typing import Callable

from . import codec


def _scpi_responder() -> Callable[[bytes], bytes]:
    state = {"v": 0.0, "i_lim": 1.0, "out": False}

    def respond(data: bytes) -> bytes:
        cmd = data.decode().strip().upper().lstrip(":")
        if cmd == "*IDN?":
            return b"SIM,PowerSupply-1000,SN0001,1.0\n"
        if cmd.startswith("VOLT "):
            state["v"] = float(cmd.split()[1])
            return b""
        if cmd.startswith("OUTP"):
            state["out"] = cmd.endswith(("ON", "1"))
            return b""
        if cmd == "MEAS:VOLT?":
            return f"{state['v'] if state['out'] else 0.0:.4f}\n".encode()
        if cmd in ("MEAS:CURR?", "MEAS:CURR:DC?"):
            i = (0.18 + random.uniform(-0.01, 0.01)) if state["out"] else 0.0
            return f"{i:.5f}\n".encode()
        if cmd == "SYST:ERR?":
            return b'0,"No error"\n'
        return b""

    return respond


def _dut_responder() -> Callable[[bytes], bytes]:
    dec = codec.StreamDecoder()

    def respond(data: bytes) -> bytes:
        out = b""
        for f in dec.feed(data):
            if f.message_id == 0x01:  # GET_VERSION -> 0x81, payload "1.2.5"
                out += codec.encode(codec.Frame(0x81, b"1.2.5"))
            elif f.message_id == 0x02:  # GET_TEMP -> 0x82, uint32 (°C*10)
                out += codec.encode(codec.Frame(0x82, (253).to_bytes(4, "little")))
            elif f.message_id == 0x10:  # INIT_REQ -> 0x90 (status=OK(0), fw=1.2, temp=25.3°C, flags=ready(1))
                payload = bytes([0, 1, 2]) + (253).to_bytes(2, "little", signed=True) + bytes([0x01])
                out += codec.encode(codec.Frame(0x90, payload))
        return out

    return respond


def _text_dut_responder() -> Callable[[bytes], bytes]:
    def respond(data: bytes) -> bytes:
        if data.strip() == b"GET VERSION":
            return b"v1.2.5\r\n"
        return b"ERR\r\n"
    return respond


PROFILES = {"scpi": _scpi_responder, "dut": _dut_responder, "text_dut": _text_dut_responder}


def make_responder(profile: str) -> Callable[[bytes], bytes]:
    return PROFILES[profile]()