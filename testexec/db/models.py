"""SQLAlchemy modelleri ve depo (repository)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (Float, ForeignKey, Integer, LargeBinary, String, Text,
                        create_engine, inspect, select, text)
from sqlalchemy.orm import (DeclarativeBase, Mapped, Session, mapped_column,
                            relationship)

from ..core.models import RunResult


class Base(DeclarativeBase):
    pass


class TestRun(Base):
    __tablename__ = "test_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    sequence: Mapped[str] = mapped_column(String(100), index=True)
    serial: Mapped[str] = mapped_column(String(100), index=True)
    operator: Mapped[str] = mapped_column(String(100))
    station: Mapped[str] = mapped_column(String(100))
    started: Mapped[datetime]
    finished: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(10), index=True)
    steps: Mapped[list["StepRow"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    traffic: Mapped[list["TrafficRow"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class StepRow(Base):
    __tablename__ = "step_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_run.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(10))
    value_num: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="")
    low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    series: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # float64 dizi
    fields_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # çözülmüş DUT alanları JSON
    run: Mapped[TestRun] = relationship(back_populates="steps")

    @property
    def fields(self) -> dict[str, Any]:
        return json.loads(self.fields_json) if self.fields_json else {}


class TrafficRow(Base):
    __tablename__ = "traffic"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_run.id"), index=True)
    ts: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String(50))
    direction: Mapped[str] = mapped_column(String(2))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    run: Mapped[TestRun] = relationship(back_populates="traffic")


class Repository:
    def __init__(self, url: str = "sqlite:///testexec.db"):
        self.engine = create_engine(url)
        Base.metadata.create_all(self.engine)
        cols = {c["name"] for c in inspect(self.engine).get_columns("step_result")}
        if "fields_json" not in cols:
            with self.engine.begin() as conn:
                conn.execute(text("ALTER TABLE step_result ADD COLUMN fields_json TEXT"))

    def save(self, r: RunResult) -> int:
        import numpy as np
        with Session(self.engine) as s:
            run = TestRun(sequence=r.sequence, serial=r.serial, operator=r.operator,
                          station=r.station, started=datetime.fromtimestamp(r.started),
                          finished=datetime.fromtimestamp(r.finished or r.started),
                          status=r.status.value)
            for i, st in enumerate(r.steps):
                num = st.value if isinstance(st.value, (int, float)) else None
                fjson = None
                if st.fields:
                    clean = {k: (v.hex(" ") if isinstance(v, (bytes, bytearray)) else v)
                             for k, v in st.fields.items()}
                    fjson = json.dumps(clean, ensure_ascii=False)
                run.steps.append(StepRow(
                    idx=i, name=st.name, status=st.status.value, value_num=num,
                    value_text=None if num is not None or st.value is None else str(st.value),
                    unit=st.unit, low=st.low, high=st.high, message=st.message,
                    duration=st.duration,
                    series=np.asarray(st.series, dtype="<f8").tobytes() if st.series else None,
                    fields_json=fjson))
            for ts, ch, d, data in r.traffic:
                run.traffic.append(TrafficRow(ts=ts, channel=ch, direction=d, data=data))
            s.add(run)
            s.commit()
            return run.id

    def list_runs(self, limit: int = 200, serial: str | None = None) -> list[TestRun]:
        with Session(self.engine, expire_on_commit=False) as s:
            q = select(TestRun).order_by(TestRun.started.desc()).limit(limit)
            if serial:
                q = q.where(TestRun.serial.contains(serial))
            return list(s.scalars(q))

    def get_run(self, run_id: int) -> Optional[TestRun]:
        with Session(self.engine, expire_on_commit=False) as s:
            run = s.get(TestRun, run_id)
            if run:
                _ = run.steps, run.traffic  # yükle
            return run

    def numeric_step_names(self) -> list[str]:
        with Session(self.engine) as s:
            q = select(StepRow.name).where(StepRow.value_num.is_not(None)).distinct().order_by(StepRow.name)
            return list(s.scalars(q))

    def step_limits(self, step_name: str) -> tuple[Optional[float], Optional[float], str]:
        """Adımın en son kaydedilen (min, max, birim) değerleri."""
        with Session(self.engine) as s:
            row = s.execute(select(StepRow.low, StepRow.high, StepRow.unit).join(TestRun)
                            .where(StepRow.name == step_name).order_by(TestRun.started.desc()).limit(1)).first()
            return (row[0], row[1], row[2]) if row else (None, None, "")

    def status_counts(self) -> dict[str, int]:
        from sqlalchemy import func
        with Session(self.engine) as s:
            rows = s.execute(select(TestRun.status, func.count()).group_by(TestRun.status)).all()
            return {k: v for k, v in rows}

    def step_history(self, step_name: str, limit: int = 500) -> list[float]:
        """Bir adımın geçmiş ölçümleri (trend/Cpk için)."""
        with Session(self.engine) as s:
            q = (select(StepRow.value_num).join(TestRun).where(StepRow.name == step_name,
                 StepRow.value_num.is_not(None)).order_by(TestRun.started.desc()).limit(limit))
            return [v for v in s.scalars(q)][::-1]