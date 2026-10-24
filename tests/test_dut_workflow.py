import pytest

from testexec.core import Sequencer, Station, Status
from testexec.db import Repository
from testexec.dut import (Catalog, export_template_excel,
                          generate_sequence_from_catalog, import_catalog,
                          save_catalog_yaml)


def test_excel_template_and_import_roundtrip(tmp_path):
    cat = Catalog.load("dut_profiles/example_dut.yaml")
    xlsx_path = tmp_path / "messages.xlsx"
    export_template_excel(xlsx_path, cat)
    assert xlsx_path.exists()

    imported = import_catalog(xlsx_path, dut_name="RoundtripDUT")
    assert set(imported.messages.keys()) == set(cat.messages.keys())

    f = imported.encode("INIT_REQ", {"mode": "TEST", "init_params": "AA BB CC", "timeout_ms": 250})
    assert f.payload == bytes([1, 0xAA, 0xBB, 0xCC]) + (250).to_bytes(2, "little")

    yaml_out = tmp_path / "out.yaml"
    save_catalog_yaml(imported, yaml_out)
    reloaded = Catalog.load(yaml_out)
    assert reloaded.name == "RoundtripDUT"
    assert reloaded.get("INIT_REQ").id == 0x10


def test_dut_message_step_and_db_fields(tmp_path):
    st = Station.from_file("stations/demo_station.yaml")
    st.open()
    try:
        seq = {
            "sequence": "DUT Katalog Testi",
            "steps": [
                {
                    "name": "Init Komutu",
                    "type": "dut_message",
                    "transport": "dut",
                    "message": "INIT_REQ",
                    "preset": "fabrika_init",
                    "params": {"init_params": "11 22 33"},
                    "expect": {
                        "status": "OK",
                        "temp": {"min": 20.0, "max": 30.0},
                        "flags": {"ready": True, "fault": False},
                    },
                },
                {
                    "name": "Versiyon Komutu",
                    "type": "dut_message",
                    "transport": "dut",
                    "message": "GET_VERSION",
                    "expect": {"version": {"regex": r"^1\.2\.\d+$"}},
                },
            ],
        }
        run = Sequencer(st).run(seq, "SN-CAT1", "op")
    finally:
        st.close()

    assert run.status == Status.PASS, [(s.name, s.status, s.message) for s in run.steps]
    assert run.steps[0].fields["status"] == "OK"
    assert run.steps[0].fields["temp"] == pytest.approx(25.3)
    assert run.steps[1].fields["version"] == "1.2.5"

    repo = Repository(f"sqlite:///{tmp_path / 'cat.db'}")
    rid = repo.save(run)
    loaded = repo.get_run(rid)
    assert loaded.steps[0].fields["status"] == "OK"
    assert loaded.steps[1].fields["version"] == "1.2.5"


def test_dut_message_expect_failure():
    st = Station.from_file("stations/demo_station.yaml")
    st.open()
    try:
        seq = {
            "sequence": "Fail Test",
            "steps": [
                {
                    "name": "Wrong Status",
                    "type": "dut_message",
                    "transport": "dut",
                    "message": "INIT_REQ",
                    "expect": {"status": "ERR"},
                }
            ],
        }
        run = Sequencer(st).run(seq, "SN-FAIL")
    finally:
        st.close()
    assert run.status == Status.FAIL
    assert "status='OK'" in run.steps[0].message


def test_auto_sequence_generation():
    cat = Catalog.load("dut_profiles/example_dut.yaml")
    seq = generate_sequence_from_catalog(cat, transport="dut", preset="fabrika_init",
                                         dut_profile_path="dut_profiles/example_dut.yaml")
    assert len(seq["steps"]) == 2
    assert seq["steps"][0]["message"] == "INIT_REQ"
    assert seq["steps"][0]["preset"] == "fabrika_init"
    assert seq["steps"][0]["expect"] == {"status": "OK"}

    st = Station.from_file("stations/demo_station.yaml")
    st.open()
    try:
        run = Sequencer(st).run(seq, "SN-AUTO")
    finally:
        st.close()
    assert run.status == Status.PASS