"""Test adım tipleri. Yeni tip eklemek için @register_step("ad") kullanın."""
from __future__ import annotations

import re
import time
from typing import Callable

from .. import codec
from .models import Status, StepResult, check_limits

# fn(spec: dict, station: Station, result: StepResult) -> None  (result'ı doldurur)
STEP_TYPES: dict[str, Callable] = {}


def register_step(name: str):
    def deco(fn):
        STEP_TYPES[name] = fn
        return fn
    return deco


def _limits(spec, result: StepResult) -> None:
    lim = spec.get("limits", {})
    result.low, result.high = lim.get("min"), lim.get("max")
    result.unit = lim.get("unit", spec.get("unit", ""))


def _judge_numeric(result: StepResult, value: float) -> None:
    result.value = value
    ok = check_limits(value, result.low, result.high)
    result.status = Status.PASS if ok else Status.FAIL
    if not ok:
        result.message = f"{value:g}{result.unit} limit dışı [{result.low}, {result.high}]"


@register_step("delay")
def delay(spec, station, result):
    end = time.monotonic() + float(spec["seconds"])
    while time.monotonic() < end:
        station.check_cancel()
        time.sleep(0.05)
    result.status = Status.PASS


@register_step("operator_input")
def operator_input(spec, station, result):
    """Operatörden giriş al.

    spec: message, kind: text|confirm (varsayılan confirm),
          store_as (text için değişken adı), expect_regex (text için)
    """
    kind = spec.get("kind", "confirm")
    ans = station.prompt(spec["message"], kind)
    if ans is None:
        result.status, result.message = Status.FAIL, "operatör iptal etti"
        return
    if kind == "confirm":
        result.value = "ONAY" if ans else "RED"
        result.status = Status.PASS if ans else Status.FAIL
        return
    text = str(ans).strip()
    result.value = text
    if "store_as" in spec:
        station.vars[spec["store_as"]] = text
    rx = spec.get("expect_regex")
    ok = bool(text) and (rx is None or re.search(rx, text) is not None)
    result.status = Status.PASS if ok else Status.FAIL
    if not ok:
        result.message = "geçersiz giriş"


@register_step("scpi_write")
def scpi_write(spec, station, result):
    inst = station.instrument(spec["instrument"])
    for cmd in ([spec["command"]] if isinstance(spec["command"], str) else spec["command"]):
        inst.write(cmd)
    result.status = Status.PASS


@register_step("measure")
def measure(spec, station, result):
    """SCPI sorgusu veya cihaz metodu ile ölçüm; limit kontrolü.

    spec: instrument, (command | method), limits{min,max,unit},
          samples (varsayılan 1, ortalaması alınır), interval (s)
    """
    inst = station.instrument(spec["instrument"])
    _limits(spec, result)
    n, interval = int(spec.get("samples", 1)), float(spec.get("interval", 0.0))
    for _ in range(n):
        station.check_cancel()
        if "method" in spec:
            v = float(getattr(inst, spec["method"])())
        else:
            v = inst.query_float(spec["command"])
        result.series.append(v)
        station.emit_sample(result.name, v)
        if interval:
            time.sleep(interval)
    _judge_numeric(result, sum(result.series) / len(result.series))


@register_step("send_receive")
def send_receive(spec, station, result):
    """Metin tabanlı gönder/al; regex ile doğrula."""
    t = station.transport(spec["transport"])
    term = spec.get("terminator", "\\r\\n").encode().decode("unicode_escape").encode()
    resp = t.query(spec["send"].encode().decode("unicode_escape").encode(),
                   terminator=term, timeout=float(spec.get("timeout", 2.0)))
    text = resp.decode(errors="replace").strip()
    result.value = text
    pattern = spec.get("expect_regex")
    if pattern is None or re.search(pattern, text):
        result.status = Status.PASS
    else:
        result.status = Status.FAIL
        result.message = f"yanıt '{text}' beklenen '{pattern}' ile eşleşmiyor"


@register_step("frame")
def frame_exchange(spec, station, result):
    """DUT çerçeve (ID|Len|Payload|XOR) gönder, yanıt çerçevesini doğrula.

    spec: transport, message_id, payload_hex, expect_id, expect_payload_regex_hex, timeout
    """
    t = station.transport(spec["transport"])
    out = codec.Frame(int(spec["message_id"], 0) if isinstance(spec["message_id"], str)
                      else spec["message_id"], bytes.fromhex(spec.get("payload_hex", "")))
    t.write(codec.encode(out))
    dec = codec.StreamDecoder()
    deadline = time.monotonic() + float(spec.get("timeout", 2.0))
    frames = []
    while not frames and time.monotonic() < deadline:
        station.check_cancel()
        frames = dec.feed(t.read(256, 0.1))
    if not frames:
        result.status = Status.FAIL
        result.message = "yanıt çerçevesi yok (timeout)"
        return
    f = frames[0]
    result.value = f"id=0x{f.message_id:X} payload={f.payload.hex()}"
    exp_id = spec.get("expect_id")
    exp_id = int(exp_id, 0) if isinstance(exp_id, str) else exp_id
    ok = exp_id is None or f.message_id == exp_id
    rx = spec.get("expect_payload_regex_hex")
    if ok and rx is not None:
        ok = re.fullmatch(rx, f.payload.hex()) is not None
    result.status = Status.PASS if ok else Status.FAIL
    if not ok:
        result.message = f"beklenmeyen yanıt: {result.value}"
    # sayısal çıkarım gerekirse: payload_uint -> limits
    if ok and spec.get("payload_uint"):
        _limits(spec, result)
        _judge_numeric(result, int.from_bytes(f.payload[:4], "little"))


@register_step("dut_message")
def dut_message(spec, station, result):
    """Katalog üzerinden tanımlı DUT mesajı gönderir ve cevabını alan alan doğrular.

    spec:
      transport: kanal adı (varsayılan 'dut')
      message: katalogdaki mesaj adı (örn. INIT_REQ)
      preset: isteğe bağlı preset adı
      params: {alan: değer} geçersiz kılmalar
      response: beklenen cevap mesajı adı (belirtilmezse mesajın kendi response alanı)
      expect: {alan: beklenen_değer | {min, max, equals, regex}}
      timeout: saniye (varsayılan 2.0)
    """
    cat = station.catalog
    if not cat:
        raise RuntimeError("İstasyonda veya sekansta 'dut_profile' tanımlı değil")
    t = station.transport(spec.get("transport", "dut"))
    msg_name = spec["message"]
    msg_def = cat.get(msg_name)
    out_frame = cat.encode(msg_name, params=spec.get("params"), preset=spec.get("preset"))
    t.write(codec.encode(out_frame))

    resp_name = spec.get("response", msg_def.response)
    if not resp_name:
        result.value = f"TX {msg_name} (0x{out_frame.message_id:X})"
        result.status = Status.PASS
        return

    dec = codec.StreamDecoder()
    deadline = time.monotonic() + float(spec.get("timeout", 2.0))
    frames = []
    while not frames and time.monotonic() < deadline:
        station.check_cancel()
        frames = dec.feed(t.read(256, 0.1))
    if not frames:
        result.status = Status.FAIL
        result.message = f"{resp_name} yanıtı gelmedi (timeout)"
        return

    decoded = cat.decode(frames[0], name=resp_name)
    result.fields = dict(decoded.values)

    # Özet metin ve varsa tekil sayısal ölçüm çıkarımı
    parts = []
    for k, v in decoded.values.items():
        if isinstance(v, bytes):
            parts.append(f"{k}={v.hex(' ')}")
        elif isinstance(v, float):
            parts.append(f"{k}={v:.4g}")
        else:
            parts.append(f"{k}={v}")
    summary = ", ".join(parts) if parts else f"0x{decoded.id:X}"
    result.value = summary

    expect = spec.get("expect") or {}
    errors = []
    first_numeric_checked = False
    for fname, rule in expect.items():
        if fname not in decoded.values:
            errors.append(f"'{fname}' alanı yanıtta yok")
            continue
        actual = decoded.values[fname]
        fdef = cat.get(resp_name).field(fname)
        if isinstance(rule, dict) and any(k in rule for k in ("min", "max", "equals", "regex")):
            lo, hi = rule.get("min"), rule.get("max")
            if (lo is not None or hi is not None) and isinstance(actual, (int, float)):
                if not first_numeric_checked:
                    result.low, result.high, result.unit = lo, hi, fdef.unit
                    result.value = float(actual)
                    first_numeric_checked = True
                if not check_limits(float(actual), lo, hi):
                    errors.append(f"{fname}={actual:g}{fdef.unit} limit dışı [{lo}, {hi}]")
            if "equals" in rule and actual != rule["equals"]:
                errors.append(f"{fname}={actual!r} != {rule['equals']!r}")
            if "regex" in rule and not re.search(str(rule["regex"]), str(actual)):
                errors.append(f"{fname}='{actual}' ~! /{rule['regex']}/")
        elif isinstance(actual, dict) and isinstance(rule, dict):
            for bit_k, bit_v in rule.items():
                if actual.get(bit_k) != bool(bit_v):
                    errors.append(f"{fname}.{bit_k}={actual.get(bit_k)} != {bool(bit_v)}")
        else:
            if actual != rule:
                errors.append(f"{fname}={actual!r} (beklenen {rule!r})")

    if errors:
        result.status = Status.FAIL
        result.message = "; ".join(errors)
    else:
        result.status = Status.PASS
