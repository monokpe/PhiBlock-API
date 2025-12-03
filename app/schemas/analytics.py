"""
Pydantic schemas for analytics API.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AnalyticsStatsResponse(BaseModel):
    total_requests: int
    total_tokens: int
    estimated_cost: float
    injection_attacks_blocked: int
    pii_detected_count: int
    avg_latency_ms: float


class TimeSeriesPoint(BaseModel):
    date: date
    requests: int
    violations: int
    latency_ms: float


class TimeSeriesResponse(BaseModel):
    data: List[TimeSeriesPoint]


class ViolationType(BaseModel):
    type: str
    count: int


class ViolationsBreakdownResponse(BaseModel):
    pii_types: List[ViolationType]
    injection_types: List[ViolationType]  # e.g. "jailbreak", "system_override" if available
