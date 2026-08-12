"""
core/sprint_manager.py
~~~~~~~~~~~~~~~~~~~~~~
3-Hour Sprint State Machine.

Each working day is divided into up to ``daily_sprints`` sprint slots
(default 4 × 3-hour blocks = 12 productive hours).  Five 30-minute
prayer pauses are automatically excluded from productive time.

State diagram::

    IDLE ──start──► ACTIVE ──complete──► REVIEW ──close──► IDLE
                      │                                      ▲
                      └──pause──► PRAYER_PAUSE ──resume──────┘

"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from config.settings import settings
from core.mizan import KSA_TZ, is_prayer_pause

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sprint states
# ---------------------------------------------------------------------------


class SprintState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    PRAYER_PAUSE = "prayer_pause"
    REVIEW = "review"
    CLOSED = "closed"


# ---------------------------------------------------------------------------
# Sprint data class
# ---------------------------------------------------------------------------


@dataclass
class Sprint:
    """Represents a single 3-hour sprint slot."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: int = 0
    employee_id: str = ""
    state: SprintState = SprintState.IDLE

    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    duration_hours: int = field(default_factory=lambda: settings.sprint.sprint_duration_hours)

    goals: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    notes: str = ""

    # Accumulated prayer-pause time (excluded from productive time)
    prayer_pause_seconds: float = 0.0

    @property
    def deadline(self) -> Optional[datetime]:
        """Return the expected end time based on start time + duration."""
        if self.started_at is None:
            return None
        return self.started_at + timedelta(hours=self.duration_hours)

    @property
    def productive_seconds(self) -> float:
        """
        Elapsed productive (non-paused) seconds since sprint start.
        Returns 0 if the sprint has not started yet.
        """
        if self.started_at is None:
            return 0.0
        end = self.completed_at or self.closed_at or datetime.now(KSA_TZ)
        total = (end - self.started_at).total_seconds()
        return max(0.0, total - self.prayer_pause_seconds)

    def is_overdue(self, now: Optional[datetime] = None) -> bool:
        if self.deadline is None or self.state in (SprintState.CLOSED, SprintState.REVIEW):
            return False
        now = now or datetime.now(KSA_TZ)
        return now > self.deadline


# ---------------------------------------------------------------------------
# Sprint Manager
# ---------------------------------------------------------------------------


class SprintManager:
    """
    Manages all sprint slots for one employee within one company.

    Transitions are validated against the state machine diagram.
    Prayer pauses are enforced: you cannot start or complete a sprint
    during a prayer window, and an active sprint is automatically
    suspended when a pause window opens.

    Usage::

        mgr = SprintManager(company_id=1, employee_id="emp_001")
        sprint = mgr.new_sprint(goals=["Finish API module"])
        mgr.start(sprint.id)
        # ... work happens ...
        mgr.complete(sprint.id, deliverables=["PR #42 merged"])
        mgr.close(sprint.id)
    """

    def __init__(self, company_id: int, employee_id: str) -> None:
        self.company_id = company_id
        self.employee_id = employee_id
        self._sprints: dict[str, Sprint] = {}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    def new_sprint(self, goals: Optional[list[str]] = None) -> Sprint:
        sprint = Sprint(
            company_id=self.company_id,
            employee_id=self.employee_id,
            goals=goals or [],
        )
        self._sprints[sprint.id] = sprint
        logger.info("Created sprint %s for employee [REDACTED]", sprint.id[:8])
        return sprint

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def start(self, sprint_id: str, now: Optional[datetime] = None) -> Sprint:
        """Transition sprint from IDLE → ACTIVE."""
        sprint = self._get(sprint_id)
        self._assert_state(sprint, SprintState.IDLE)
        self._block_if_prayer(now)

        now = now or datetime.now(KSA_TZ)
        sprint.state = SprintState.ACTIVE
        sprint.started_at = now
        logger.info("Sprint %s started at %s", sprint_id[:8], now.isoformat())
        return sprint

    def pause_for_prayer(self, sprint_id: str, now: Optional[datetime] = None) -> Sprint:
        """Transition sprint from ACTIVE → PRAYER_PAUSE."""
        sprint = self._get(sprint_id)
        self._assert_state(sprint, SprintState.ACTIVE)

        now = now or datetime.now(KSA_TZ)
        sprint.state = SprintState.PRAYER_PAUSE
        sprint.paused_at = now
        logger.info("Sprint %s paused for prayer at %s", sprint_id[:8], now.isoformat())
        return sprint

    def resume(self, sprint_id: str, now: Optional[datetime] = None) -> Sprint:
        """Transition sprint from PRAYER_PAUSE → ACTIVE."""
        sprint = self._get(sprint_id)
        self._assert_state(sprint, SprintState.PRAYER_PAUSE)

        now = now or datetime.now(KSA_TZ)
        if sprint.paused_at:
            pause_duration = (now - sprint.paused_at).total_seconds()
            sprint.prayer_pause_seconds += pause_duration
            logger.debug(
                "Sprint %s: accumulated %.0f s prayer pause",
                sprint_id[:8],
                sprint.prayer_pause_seconds,
            )
        sprint.state = SprintState.ACTIVE
        sprint.resumed_at = now
        return sprint

    def complete(
        self,
        sprint_id: str,
        deliverables: Optional[list[str]] = None,
        now: Optional[datetime] = None,
    ) -> Sprint:
        """Transition sprint from ACTIVE → REVIEW."""
        sprint = self._get(sprint_id)
        self._assert_state(sprint, SprintState.ACTIVE)
        self._block_if_prayer(now)

        now = now or datetime.now(KSA_TZ)
        sprint.state = SprintState.REVIEW
        sprint.completed_at = now
        if deliverables:
            sprint.deliverables.extend(deliverables)
        logger.info("Sprint %s completed — deliverables: %s", sprint_id[:8], sprint.deliverables)
        return sprint

    def close(self, sprint_id: str, notes: str = "", now: Optional[datetime] = None) -> Sprint:
        """Transition sprint from REVIEW → CLOSED."""
        sprint = self._get(sprint_id)
        self._assert_state(sprint, SprintState.REVIEW)

        now = now or datetime.now(KSA_TZ)
        sprint.state = SprintState.CLOSED
        sprint.closed_at = now
        sprint.notes = notes
        logger.info("Sprint %s closed", sprint_id[:8])
        return sprint

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def active_sprint(self) -> Optional[Sprint]:
        for s in self._sprints.values():
            if s.state == SprintState.ACTIVE:
                return s
        return None

    def sprints_today(self, now: Optional[datetime] = None) -> list[Sprint]:
        now = now or datetime.now(KSA_TZ)
        today = now.date()
        return [
            s for s in self._sprints.values()
            if s.started_at and s.started_at.date() == today
        ]

    def daily_productive_hours(self, now: Optional[datetime] = None) -> float:
        total_secs = sum(s.productive_seconds for s in self.sprints_today(now))
        return round(total_secs / 3600, 2)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get(self, sprint_id: str) -> Sprint:
        try:
            return self._sprints[sprint_id]
        except KeyError as exc:
            raise ValueError(f"Sprint {sprint_id!r} not found.") from exc

    @staticmethod
    def _assert_state(sprint: Sprint, expected: SprintState) -> None:
        if sprint.state != expected:
            raise RuntimeError(
                f"Invalid transition: sprint is in state {sprint.state!r}, "
                f"expected {expected!r}."
            )

    @staticmethod
    def _block_if_prayer(now: Optional[datetime] = None) -> None:
        if is_prayer_pause(now):
            raise RuntimeError(
                "Operation blocked: currently in a prayer pause window. "
                "Please wait until the window ends."
            )
