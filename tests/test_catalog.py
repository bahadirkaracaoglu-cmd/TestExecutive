import pytest

from testexec import codec
from testexec.dut import Catalog, CatalogError

PROFILE = "dut_profiles/example_dut.yaml"


@pytest.fixture
def cat():
    return Catalog.load(PROFILE)


def test_encode_defaults_and_params(cat):
    f = cat.encode("INIT_REQ")
    assert f.message_id == 0x10
    assert f.payload == bytes([0, 0, 0, 0]) + (500).to_bytes(2, "little")
    f = cat.encode("INIT_REQ", {"mode": "TEST", "init_params": "01 02 03", "timeout_ms": 0x1234})
    assert f.payload == bytes([1, 1, 2, 3, 0x34, 0x12])


def test_length_field_is_payload_length(cat):
    raw = codec.encode(cat.encode("INIT_REQ", {"mode": "TEST"}))
    assert int.from_bytes(raw[4:8], "little") == 6  # sadece payload
    assert len(raw) == 8 + 6 + 1


def test_preset_and_override(cat):
    f = cat.encode("INIT_REQ", preset="fabrika_init", params={"timeout_ms": 5})
    assert f.payload[1:4] == bytes([0xA1, 0xB2, 0xC3])
    assert int.from_bytes(f.payload[4:6], "little") == 5
    with pytest.raises(CatalogError):
        cat.encode("INIT_REQ", preset="yok")


def test_decode_scale_enum_bits(cat):
    payload = bytes([0, 1, 2]) + (253).to_bytes(2, "little", signed=True) + bytes([0b101])
    d = cat.decode(codec.Frame(0x90, payload))
    assert d.name == "INIT_RSP"
    assert d["status"] == "OK" and d["fw_major"] == 1
    assert d["temp"] == pytest.approx(25.3)
    assert d.raw["temp"] == 253
    assert d["flags"] == {"ready": True, "fault": False, "low_batt": True}


def test_negative_temp_roundtrip(cat):
    m = cat.get("INIT_RSP")
    p = cat.build_payload(m, {"status": "ERR", "temp": -12.5, "flags": {"fault": True}})
    d = cat.decode(codec.Frame(0x90, p))
    assert d["temp"] == pytest.approx(-12.5) and d["status"] == "ERR" and d["flags"]["fault"]


def test_rest_ascii_and_extra_bytes(cat):
    d = cat.decode(codec.Frame(0x81, b"1.2.5"))
    assert d["version"] == "1.2.5"
    d = cat.decode(codec.Frame(0x90, bytes(6) + b"\xAA\xBB"))
    assert d.extra == b"\xAA\xBB"


def test_errors(cat):
    with pytest.raises(CatalogError):
        cat.encode("INIT_REQ", {"nope": 1})
    with pytest.raises(CatalogError):
        cat.encode("INIT_REQ", {"timeout_ms": 70000})
    with pytest.raises(CatalogError):
        cat.encode("INIT_REQ", {"init_params": "01 02"})
    with pytest.raises(CatalogError):
        cat.decode(codec.Frame(0x90, b"\x00"))  # kısa
    with pytest.raises(CatalogError):
        cat.decode(codec.Frame(0x7F, b""))  # tanımsız ID
    with pytest.raises(CatalogError):
        cat.get("YOK")


def test_validation_overlap_and_dup():
    bad = {"messages": {"A": {"id": 1, "fields": [
        {"name": "x", "offset": 0, "type": "uint16"}, {"name": "y", "offset": 1, "type": "uint8"}]}}}
    with pytest.raises(CatalogError):
        Catalog.from_dict(bad)
    bad = {"messages": {"A": {"id": 1, "response": "B"}}}
    with pytest.raises(CatalogError):
        Catalog.from_dict(bad).validate()


def test_big_endian_and_24bit():
    c = Catalog.from_dict({"byte_order": "big", "messages": {"M": {"id": 2, "fields": [
        {"name": "v", "offset": 0, "type": "uint24"}, {"name": "f", "offset": 3, "type": "float32", "scale": 1}]}}})
    p = c.build_payload(c.get("M"), {"v": 0x010203, "f": 1.5})
    assert p[:3] == b"\x01\x02\x03"
    d = c.decode(codec.Frame(2, p))
    assert d["v"] == 0x010203 and d["f"] == 1.5


def test_search_groups_and_directory(tmp_path, cat):
    assert {"init", "diag"} <= set(cat.groups)
    assert [m.name for m in cat.search("version")] == ["GET_VERSION", "VERSION_RSP"]
    assert cat.search(group="init")[0].name == "INIT_REQ"
    (tmp_path / "a.yaml").write_text("dut: X\nmessages:\n  A: {id: 1}\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("messages:\n  B: {id: 2, response: A}\n", encoding="utf-8")
    c = Catalog.load(tmp_path)
    assert c.get("A").group == "a" and c.get("B").group == "b"


def test_full_frame_roundtrip(cat):
    raw = codec.encode(cat.encode("INIT_REQ", preset="test_modu"))
    f = codec.decode(raw)
    assert f.message_id == 0x10 and f.payload[0] == 1