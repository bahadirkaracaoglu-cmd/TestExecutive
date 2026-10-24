"""İstatistik ve süreç yeterlilik hesapları."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass
class Summary:
    n: int
    mean: float
    std: float
    minimum: float
    maximum: float
    cp: Optional[float] = None
    cpk: Optional[float] = None


def summarize(values: Sequence[float], low: Optional[float] = None,
              high: Optional[float] = None) -> Optional[Summary]:
    n = len(values)
    if n == 0:
        return None
    mean = sum(values) / n
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    cp = cpk = None
    if std > 0:
        if low is not None and high is not None:
            cp = (high - low) / (6 * std)
        parts = []
        if high is not None:
            parts.append((high - mean) / (3 * std))
        if low is not None:
            parts.append((mean - low) / (3 * std))
        if parts:
            cpk = min(parts)
    return Summary(n, mean, std, min(values), max(values), cp, cpk)


def yield_percent(statuses: Sequence[str]) -> float:
    """PASS oranı (%)."""
    return 100.0 * sum(1 for s in statuses if s == "PASS") / len(statuses) if statuses else 0.0