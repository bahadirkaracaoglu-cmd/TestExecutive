import pytest

from testexec import codec
from testexec.core import Sequencer, Station, Status
from testexec.db import Repository


def test_codec_roundtrip_little_endian_xor():
    raw = codec.encode(codec.Frame(0x01020304, b"\xAA\xBB"))
    assert raw[:4] == b"\x04\x03\x02\x01"          # little endian ID
    assert raw[4:8] == b"\x02\x00\x00\x00"         # sadece payload uzunluğu
    x = 0
    for b in raw[:-1]:
        x ^= b
    assert raw[-1] == x
    assert codec.decode(raw) == codec.Frame(0x01020304, b"\xAA\xBB")


def test_codec_bad_checksum():
    raw = bytearray(codec.encode(codec.Frame(1, b"abc")))
    raw[-1] ^= 0xFF
    with pytest.raises(codec.FrameError):
        codec.decode(bytes(raw))


def test_stream_decoder_resync_and_chunks():
    f1 = codec.encode(codec.Frame(1, b"hello"))
    f2 = codec.encode(codec.Frame(2, b""))
    d = codec.StreamDecoder()
    data = b"\xFF\xFF" + f1 + f2
    out = []
    for i in range(0, len(data), 3):
        out += d.feed(data[i:i + 3])
    assert [f.message_id for f in out] == [1, 2]


def test_demo_sequence_passes(tmp_path):
    st = Station.from_file("stations/demo_station.yaml")
    st.open()
    try:
        run = Sequencer(st).run(Sequencer.load("sequences/demo_sequence.yaml"), "SN1", "op")
    finally:
        st.close()
    assert run.status == Status.PASS, [(s.name, s.status, s.message) for s in run.steps]
    assert run.traffic
    repo = Repository(f"sqlite:///{tmp_path/'t.db'}")
    rid = repo.save(run)
    loaded = repo.get_run(rid)
    assert loaded.status == "PASS" and len(loaded.steps) == len(run.steps)
    assert len(repo.step_history("Çekilen Akım")) == 1


def test_limit_fail_stops_sequence():
    st = Station.from_file("stations/demo_station.yaml")
    st.open()
    seq = Sequencer.load("sequences/demo_sequence.yaml")
    for s in seq["steps"]:
        if s["name"] == "Çekilen Akım":
            s["limits"] = {"min": 1.0, "max": 2.0, "unit": "A"}
    try:
        run = Sequencer(st).run(seq, "SN2")
    finally:
        st.close()
    assert run.status == Status.FAIL
    names = {s.name: s.status for s in run.steps}
    assert names["Besleme Gerilimi"] == Status.SKIPPED
    assert names["Çekilen Akım"] == Status.FAIL