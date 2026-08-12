"""
tests/test_mizan.py
~~~~~~~~~~~~~~~~~~~
Unit tests for core/mizan.py
"""

import pytest
from datetime import datetime, timezone, timedelta

from core.mizan import (
    KSA_TZ,
    EmployeeLedger,
    MizanEngine,
    calculate_tpc,
    is_prayer_pause,
    require_not_prayer_pause,
    update_ledger_tpc,
)


class TestCalculateTPC:
    def test_all_ones_gives_one(self):
        assert calculate_tpc(1.0, 1.0, 1.0) == 1.0

    def test_all_zeros_gives_zero(self):
        assert calculate_tpc(0.0, 0.0, 0.0) == 0.0

    def test_weighted_formula(self):
        # TPC = 0.8*0.5 + 0.6*0.3 + 0.4*0.2 = 0.4 + 0.18 + 0.08 = 0.66
        assert calculate_tpc(0.8, 0.6, 0.4) == pytest.approx(0.66, abs=1e-4)

    def test_out_of_range_tcr_raises(self):
        with pytest.raises(ValueError, match="TCR"):
            calculate_tpc(1.1, 0.5, 0.5)

    def test_out_of_range_aes_raises(self):
        with pytest.raises(ValueError, match="AES"):
            calculate_tpc(0.5, -0.1, 0.5)

    def test_out_of_range_oqi_raises(self):
        with pytest.raises(ValueError, match="OQI"):
            calculate_tpc(0.5, 0.5, 2.0)

    def test_boundary_values_accepted(self):
        assert calculate_tpc(0.0, 0.0, 0.0) == 0.0
        assert calculate_tpc(1.0, 1.0, 1.0) == 1.0


class TestEmployeeLedger:
    def test_initial_balances_zero(self):
        ledger = EmployeeLedger(employee_id="emp_001")
        assert ledger.positive_balance == 0.0
        assert ledger.negative_balance == 0.0
        assert ledger.net_balance == 0.0

    def test_add_credit(self):
        ledger = EmployeeLedger(employee_id="emp_001")
        ledger.add_credit(100.0, "Sprint completed")
        assert ledger.positive_balance == 100.0

    def test_add_debit(self):
        ledger = EmployeeLedger(employee_id="emp_001")
        ledger.add_debit(30.0, "Late delivery")
        assert ledger.negative_balance == 30.0

    def test_net_balance(self):
        ledger = EmployeeLedger(employee_id="emp_001")
        ledger.add_credit(100.0, "bonus")
        ledger.add_debit(20.0, "penalty")
        assert ledger.net_balance == 80.0

    def test_credit_zero_raises(self):
        ledger = EmployeeLedger(employee_id="emp_001")
        with pytest.raises(ValueError):
            ledger.add_credit(0.0, "bad")

    def test_debit_negative_raises(self):
        ledger = EmployeeLedger(employee_id="emp_001")
        with pytest.raises(ValueError):
            ledger.add_debit(-5.0, "bad")


class TestPrayerPause:
    def _ksa_dt(self, hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 8, 12, hour, minute, tzinfo=KSA_TZ)

    def test_during_fajr_is_paused(self):
        assert is_prayer_pause(self._ksa_dt(5, 10)) is True

    def test_before_fajr_not_paused(self):
        assert is_prayer_pause(self._ksa_dt(4, 59)) is False

    def test_after_fajr_window_not_paused(self):
        assert is_prayer_pause(self._ksa_dt(5, 31)) is False

    def test_during_dhuhr_is_paused(self):
        assert is_prayer_pause(self._ksa_dt(12, 45)) is True

    def test_during_asr_is_paused(self):
        assert is_prayer_pause(self._ksa_dt(15, 40)) is True

    def test_during_maghrib_is_paused(self):
        assert is_prayer_pause(self._ksa_dt(18, 15)) is True

    def test_during_isha_is_paused(self):
        assert is_prayer_pause(self._ksa_dt(19, 50)) is True

    def test_midday_not_paused(self):
        assert is_prayer_pause(self._ksa_dt(10, 0)) is False

    def test_require_raises_during_pause(self):
        with pytest.raises(RuntimeError, match="prayer pause"):
            require_not_prayer_pause(self._ksa_dt(5, 10))

    def test_require_passes_outside_pause(self):
        # Should not raise
        require_not_prayer_pause(self._ksa_dt(9, 0))


class TestMizanEngine:
    def _outside_prayer(self) -> datetime:
        return datetime(2026, 8, 12, 9, 0, tzinfo=KSA_TZ)

    def test_get_or_create_new_ledger(self):
        engine = MizanEngine(company_id=1)
        ledger = engine.get_or_create("emp_001")
        assert ledger.employee_id == "emp_001"

    def test_get_or_create_returns_same_instance(self):
        engine = MizanEngine(company_id=1)
        a = engine.get_or_create("emp_001")
        b = engine.get_or_create("emp_001")
        assert a is b

    def test_summary_includes_tpc(self):
        engine = MizanEngine(company_id=1)
        engine.set_scores("emp_001", tcr=0.8, aes=0.6, oqi=0.4)
        summary = engine.summary("emp_001")
        assert "tpc" in summary
        assert summary["tpc"] == pytest.approx(0.66, abs=1e-4)
