"""
tests/test_sprint_manager.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for core/sprint_manager.py
"""

import pytest
from datetime import datetime, timedelta

from core.mizan import KSA_TZ
from core.sprint_manager import Sprint, SprintManager, SprintState


def _outside_prayer(hour: int = 9, minute: int = 0) -> datetime:
    """Return a KSA datetime guaranteed to be outside any prayer window."""
    return datetime(2026, 8, 12, hour, minute, tzinfo=KSA_TZ)


def _during_prayer() -> datetime:
    """Return a KSA datetime that falls inside the Fajr prayer window."""
    return datetime(2026, 8, 12, 5, 10, tzinfo=KSA_TZ)


class TestSprintCreation:
    def test_new_sprint_is_idle(self):
        mgr = SprintManager(company_id=1, employee_id="emp_001")
        sprint = mgr.new_sprint()
        assert sprint.state == SprintState.IDLE

    def test_new_sprint_has_goals(self):
        mgr = SprintManager(company_id=1, employee_id="emp_001")
        sprint = mgr.new_sprint(goals=["Deploy module A"])
        assert "Deploy module A" in sprint.goals


class TestSprintTransitions:
    def _mgr(self):
        return SprintManager(company_id=1, employee_id="emp_001")

    def test_idle_to_active(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer())
        assert s.state == SprintState.ACTIVE

    def test_start_sets_started_at(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        t = _outside_prayer()
        mgr.start(s.id, now=t)
        assert s.started_at == t

    def test_start_during_prayer_raises(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        with pytest.raises(RuntimeError, match="prayer pause"):
            mgr.start(s.id, now=_during_prayer())

    def test_active_to_prayer_pause(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9))
        mgr.pause_for_prayer(s.id, now=_outside_prayer(9, 10))
        assert s.state == SprintState.PRAYER_PAUSE

    def test_prayer_pause_to_active(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9))
        mgr.pause_for_prayer(s.id, now=_outside_prayer(9, 10))
        mgr.resume(s.id, now=_outside_prayer(9, 40))
        assert s.state == SprintState.ACTIVE

    def test_resume_accumulates_pause_seconds(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9))
        mgr.pause_for_prayer(s.id, now=_outside_prayer(9, 10))
        # Resume 30 minutes later
        mgr.resume(s.id, now=_outside_prayer(9, 40))
        assert s.prayer_pause_seconds == pytest.approx(30 * 60, abs=1)

    def test_active_to_review(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9))
        mgr.complete(s.id, deliverables=["PR merged"], now=_outside_prayer(11, 59))
        assert s.state == SprintState.REVIEW

    def test_complete_during_prayer_raises(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9))
        # Force state change to active without the prayer check for setup
        s.state = SprintState.ACTIVE
        with pytest.raises(RuntimeError, match="prayer pause"):
            mgr.complete(s.id, now=_during_prayer())

    def test_review_to_closed(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9))
        mgr.complete(s.id, now=_outside_prayer(11, 59))
        mgr.close(s.id, notes="All good")
        assert s.state == SprintState.CLOSED
        assert s.notes == "All good"

    def test_invalid_transition_raises(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        # Can't complete an IDLE sprint
        with pytest.raises(RuntimeError, match="Invalid transition"):
            mgr.complete(s.id, now=_outside_prayer(11))


class TestSprintQueries:
    def _mgr(self):
        return SprintManager(company_id=1, employee_id="emp_001")

    def test_active_sprint_found(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9))
        assert mgr.active_sprint() is s

    def test_no_active_sprint_when_idle(self):
        mgr = self._mgr()
        mgr.new_sprint()
        assert mgr.active_sprint() is None

    def test_sprints_today_counts_correctly(self):
        mgr = self._mgr()
        s1 = mgr.new_sprint()
        s2 = mgr.new_sprint()
        mgr.start(s1.id, now=_outside_prayer(9))
        mgr.start(s2.id, now=_outside_prayer(13))
        today = _outside_prayer(15)
        assert len(mgr.sprints_today(now=today)) == 2

    def test_daily_productive_hours_excludes_prayer_pause(self):
        mgr = self._mgr()
        s = mgr.new_sprint()
        mgr.start(s.id, now=_outside_prayer(9, 0))
        mgr.pause_for_prayer(s.id, now=_outside_prayer(9, 30))
        mgr.resume(s.id, now=_outside_prayer(10, 0))  # 30-min pause
        mgr.complete(s.id, now=_outside_prayer(12, 0))  # 3 hrs total, 30 min paused
        mgr.close(s.id, now=_outside_prayer(12, 5))

        today = _outside_prayer(12, 10)
        hours = mgr.daily_productive_hours(now=today)
        # 3 hours wall-clock - 0.5 hour prayer = 2.5 productive hours
        assert hours == pytest.approx(2.5, abs=0.01)
