import pytest

from testexec import reports
from testexec.analysis import summarize, yield_percent
from testexec.core import Sequencer, Station, Status
from testexec.db import Repository


def _run(seq_path="sequences/demo_sequence.yaml", prompt=None):
    st = Station.from_file("stations/demo_station.yaml")
    st.open()
    st.on_prompt = prompt
    try:
        return Sequencer(st).run(Sequencer.load(seq_path), "SN-T", "op")
    finally:
        st.close()


def test_summarize_cpk():
    s = summarize([9.9, 10.0, 10.1, 10.0, 10.0], 9.0, 11.0)
    assert s.n == 5 and s.cpk > 4 and abs(s.mean - 10.0) < 1e-9
    assert summarize([]) is None
    assert yield_percent(["PASS", "FAIL", "PASS", "PASS"]) == 75.0


def test_operator_sequence_with_answers():
    answers = iter(["SN-ABCD1", True])
    run = _run("sequences/operator_sequence.yaml", lambda msg, kind: next(answers))
    assert run.status == Status.PASS
    assert run.serial == "SN-ABCD1"  # operatörden alınan seri no koşuya yazılır


def test_operator_reject_fails():
    answers = iter(["SN-ABCD1", False])
    run = _run("sequences/operator_sequence.yaml", lambda msg, kind: next(answers))
    assert run.status == Status.FAIL


def test_reports(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path/'r.db'}")
    rid = repo.save(_run())
    run = repo.get_run(rid)
    html = reports.render_html(run, include_traffic=True)
    assert "Çekilen Akım" in html and "data:image/png;base64" in html and "PASS" in html
    x = reports.save_excel([run], tmp_path / "r.xlsx")
    assert x.exists() and x.stat().st_size > 1000
    assert "Çekilen Akım" in repo.numeric_step_names()
    assert repo.status_counts()["PASS"] == 1
    lo, hi, unit = repo.step_limits("Çekilen Akım")
    assert (lo, hi, unit) == (0.10, 0.25, "A")