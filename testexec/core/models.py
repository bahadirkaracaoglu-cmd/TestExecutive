from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    RUNNING = "RUNNING"
    PENDING = "PENDING"


@dataclass
class StepResult:
    name: str
    status: Status = Status.PENDING
    value: Any = None
    unit: str = ""
    low: Optional[float] = None
    high: Optional[float] = None
    message: str = ""
    started: float = 0.0
    duration: float = 0.0
    series: list[float] = field(default_factory=list)  # grafik için ham örnekler
    fields: dict[str, Any] = field(default_factory=dict)  # çözülmüş DUT mesaj alanları


@dataclass
class RunResult:
    sequence: str
    serial: str
    operator: str
    station: str
    started: float = field(default_factory=time.time)
    finished: float = 0.0
    status: Status = Status.PENDING
    steps: list[StepResult] = field(default_factory=list)
    traffic: list[tuple[float, str, str, bytes]] = field(default_factory=list)  # (ts, kanal, yön, veri)


def check_limits(value: float, low: Optional[float], high: Optional[float]) -> bool:
    if low is not None and value < low:
        return False
    if high is not None and value > high:
        return False
    return True