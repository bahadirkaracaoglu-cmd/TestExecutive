import argparse

from testexec.core import Sequencer, Station
from testexec.db import Repository


def main():
    ap = argparse.ArgumentParser(description="Test Executive (CLI)")
    ap.add_argument("--station", default="stations/demo_station.yaml")
    ap.add_argument("--sequence", default="sequences/demo_sequence.yaml")
    ap.add_argument("--serial", default="SN0001")
    ap.add_argument("--operator", default="op1")
    ap.add_argument("--db", default="sqlite:///testexec.db")
    a = ap.parse_args()

    station = Station.from_file(a.station)
    station.open()
    try:
        seq = Sequencer(station)
        seq.on_step_done = lambda i, r: print(
            f"[{r.status.value:7}] {r.name:32} {r.value if r.value is not None else '':<20} {r.message}")
        run = seq.run(Sequencer.load(a.sequence), a.serial, a.operator)
    finally:
        station.close()
    rid = Repository(a.db).save(run)
    print(f"\nSONUÇ: {run.status.value}  (run id={rid})")


if __name__ == "__main__":
    main()