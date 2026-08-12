"""
core/mizan.py
~~~~~~~~~~~~~
The Double-Ledger Engine (ميزان — Mizan).

Responsibilities:
  1. Maintain a positive / negative ledger for each employee.
  2. Calculate the Thabot Productivity Coefficient (TPC).
  3. Enforce the 5 Daily Prayer Pause — block automated operations for
     30 minutes during each of the five Islamic prayer windows.

TPC Formula
-----------
    TPC = (TCR × 0.50) + (AES × 0.30) + (OQI × 0.20)

Where:
    TCR — Task Completion Rate   (0.0 – 1.0)
    AES — Active Engagement Score (0.0 – 1.0)
    OQI — Output Quality Index   (0.0 – 1.0)

The TPC is normalised to [0.0, 1.0].
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prayer windows (local Saudi time — UTC+3)
# Each window is (start_time, duration_minutes).  The 30-minute pause begins
# at the window start time; this is configurable via the duration field.
# ---------------------------------------------------------------------------
PRAYER_WINDOWS: list[tuple[time, int]] = [
    (time(5, 0), 30),   # Fajr   — 05:00
    (time(12, 30), 30), # Dhuhr  — 12:30
    (time(15, 30), 30), # Asr    — 15:30
    (time(18, 0), 30),  # Maghrib — 18:00
    (time(19, 30), 30), # Isha   — 19:30
]

KSA_UTC_OFFSET = timedelta(hours=3)
KSA_TZ = timezone(KSA_UTC_OFFSET)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    """A single positive or negative entry in the employee ledger."""

    timestamp: datetime
    description: str
    amount: float  # positive = credit, negative = debit
    category: str  # e.g. "task_completed", "late_delivery", "bonus"


@dataclass
class EmployeeLedger:
    """Double-ledger for one employee."""

    employee_id: str
    positive_entries: list[LedgerEntry] = field(default_factory=list)
    negative_entries: list[LedgerEntry] = field(default_factory=list)

    # --- TPC components ---
    tcr: float = 0.0  # Task Completion Rate
    aes: float = 0.0  # Active Engagement Score
    oqi: float = 0.0  # Output Quality Index

    @property
    def positive_balance(self) -> float:
        return sum(e.amount for e in self.positive_entries)

    @property
    def negative_balance(self) -> float:
        return sum(abs(e.amount) for e in self.negative_entries)

    @property
    def net_balance(self) -> float:
        return self.positive_balance - self.negative_balance

    def add_credit(
        self, amount: float, description: str, category: str = "general"
    ) -> None:
        if amount <= 0:
            raise ValueError("Credit amount must be positive.")
        self.positive_entries.append(
            LedgerEntry(
                timestamp=datetime.now(KSA_TZ),
                description=description,
                amount=amount,
                category=category,
            )
        )

    def add_debit(
        self, amount: float, description: str, category: str = "general"
    ) -> None:
        if amount <= 0:
            raise ValueError("Debit amount must be positive.")
        self.negative_entries.append(
            LedgerEntry(
                timestamp=datetime.now(KSA_TZ),
                description=description,
                amount=-abs(amount),
                category=category,
            )
        )


# ---------------------------------------------------------------------------
# TPC Calculator
# ---------------------------------------------------------------------------


def calculate_tpc(tcr: float, aes: float, oqi: float) -> float:
    """
    Calculate the Thabot Productivity Coefficient.

        TPC = (TCR × 0.50) + (AES × 0.30) + (OQI × 0.20)

    All inputs must be in [0.0, 1.0]; raises ValueError otherwise.
    Returns a float in [0.0, 1.0] rounded to 4 decimal places.
    """
    for name, value in (("TCR", tcr), ("AES", aes), ("OQI", oqi)):
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{name} must be between 0.0 and 1.0, got {value}.")

    tpc = (tcr * 0.50) + (aes * 0.30) + (oqi * 0.20)
    return round(tpc, 4)


def update_ledger_tpc(ledger: EmployeeLedger) -> float:
    """Recalculate TPC from the ledger's stored component scores and return it."""
    tpc = calculate_tpc(ledger.tcr, ledger.aes, ledger.oqi)
    logger.debug(
        "TPC for employee %s: %.4f (TCR=%.2f, AES=%.2f, OQI=%.2f)",
        ledger.employee_id,
        tpc,
        ledger.tcr,
        ledger.aes,
        ledger.oqi,
    )
    return tpc


# ---------------------------------------------------------------------------
# Prayer Pause Enforcement
# ---------------------------------------------------------------------------


def current_ksa_time(now: Optional[datetime] = None) -> time:
    """Return the current time in KSA (UTC+3)."""
    if now is None:
        now = datetime.now(timezone.utc)
    ksa_dt = now.astimezone(KSA_TZ)
    return ksa_dt.time()


def is_prayer_pause(now: Optional[datetime] = None) -> bool:
    """
    Return True if the current KSA time falls within any of the five
    daily prayer pause windows (each 30 minutes long).
    """
    current = current_ksa_time(now)
    for window_start, duration_minutes in PRAYER_WINDOWS:
        window_end_dt = (
            datetime.combine(datetime.today(), window_start)
            + timedelta(minutes=duration_minutes)
        )
        window_end = window_end_dt.time()
        if window_start <= current < window_end:
            logger.info(
                "Prayer pause active — window starts at %s, ends at %s.",
                window_start,
                window_end,
            )
            return True
    return False


def require_not_prayer_pause(now: Optional[datetime] = None) -> None:
    """
    Raise ``RuntimeError`` if called during a prayer pause window.

    Call this at the start of any automated operation that must be blocked
    during prayer times.
    """
    if is_prayer_pause(now):
        raise RuntimeError(
            "Automated operation blocked: system is in prayer pause mode. "
            "Please resume after the prayer window ends."
        )


# ---------------------------------------------------------------------------
# Ledger Registry
# ---------------------------------------------------------------------------


class MizanEngine:
    """
    Central registry for all employee ledgers within one Odoo company.

    Usage::

        engine = MizanEngine(company_id=1)
        engine.get_or_create("emp_001")
        engine.credit("emp_001", 100.0, "Sprint completed on time")
        print(engine.tpc("emp_001"))
    """

    def __init__(self, company_id: int) -> None:
        self.company_id = company_id
        self._ledgers: dict[str, EmployeeLedger] = {}

    def get_or_create(self, employee_id: str) -> EmployeeLedger:
        if employee_id not in self._ledgers:
            self._ledgers[employee_id] = EmployeeLedger(employee_id=employee_id)
        return self._ledgers[employee_id]

    def credit(self, employee_id: str, amount: float, description: str, category: str = "general") -> None:
        require_not_prayer_pause()
        self.get_or_create(employee_id).add_credit(amount, description, category)

    def debit(self, employee_id: str, amount: float, description: str, category: str = "general") -> None:
        require_not_prayer_pause()
        self.get_or_create(employee_id).add_debit(amount, description, category)

    def set_scores(self, employee_id: str, tcr: float, aes: float, oqi: float) -> None:
        ledger = self.get_or_create(employee_id)
        ledger.tcr, ledger.aes, ledger.oqi = tcr, aes, oqi

    def tpc(self, employee_id: str) -> float:
        return update_ledger_tpc(self.get_or_create(employee_id))

    def summary(self, employee_id: str) -> dict:
        ledger = self.get_or_create(employee_id)
        return {
            "employee_id": employee_id,
            "company_id": self.company_id,
            "positive_balance": ledger.positive_balance,
            "negative_balance": ledger.negative_balance,
            "net_balance": ledger.net_balance,
            "tpc": self.tpc(employee_id),
        }
