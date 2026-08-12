"""
tests/test_odoo_client.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for core/odoo_client.py

Odoo JSON-RPC calls are fully mocked so no live server is needed.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from config.settings import PayrollRates
from core.odoo_client import OdooAuthError, OdooClient, OdooError, _jsonrpc_call


class TestPayrollRates:
    def setup_method(self):
        self.rates = PayrollRates()

    def test_high_school_rate(self):
        assert self.rates.effective_rate("high_school") == 55.0

    def test_bsc_rate(self):
        assert self.rates.effective_rate("bsc") == 77.0

    def test_msc_rate(self):
        assert self.rates.effective_rate("msc") == 111.0

    def test_control_room_high_school(self):
        # 55 * 0.75 = 41.25
        assert self.rates.effective_rate("high_school", is_control_room=True) == 41.25

    def test_control_room_bsc(self):
        # 77 * 0.75 = 57.75
        assert self.rates.effective_rate("bsc", is_control_room=True) == 57.75

    def test_control_room_msc(self):
        # 111 * 0.75 = 83.25
        assert self.rates.effective_rate("msc", is_control_room=True) == 83.25

    def test_unknown_education_raises(self):
        with pytest.raises(ValueError, match="Unknown education level"):
            self.rates.effective_rate("phd")


class TestOdooClientAuthentication:
    def _make_client(self):
        return OdooClient(
            host="http://fake-odoo.local",
            database="test_db",
            username="admin",
            api_key="secret_key",
        )

    def test_authenticate_sets_uid(self):
        client = self._make_client()
        with patch("core.odoo_client._jsonrpc_call", return_value=7) as mock_call:
            uid = client.authenticate()
            assert uid == 7
            assert client._uid == 7

    def test_authenticate_failure_raises(self):
        client = self._make_client()
        with patch("core.odoo_client._jsonrpc_call", return_value=False):
            with pytest.raises(OdooAuthError):
                client.authenticate()

    def test_uid_property_raises_when_not_authenticated(self):
        client = self._make_client()
        with pytest.raises(OdooAuthError):
            _ = client.uid


class TestOdooClientContracts:
    def _authenticated_client(self):
        client = OdooClient(
            host="http://fake-odoo.local",
            database="test_db",
            username="admin",
            api_key="secret_key",
        )
        client._uid = 1
        return client

    def test_get_contracts_enriched_with_rates(self):
        raw_records = [
            {
                "id": 10,
                "name": "Contract Ahmed",
                "employee_id": [42, "Ahmed"],
                "x_education_level": "bsc",
                "x_is_control_room": False,
                "wage": 10000,
            }
        ]
        client = self._authenticated_client()
        with patch.object(client, "_execute", return_value=raw_records):
            contracts = client.get_contracts(company_id=2)
        assert len(contracts) == 1
        assert contracts[0]["effective_hourly_rate"] == 77.0

    def test_control_room_employee_gets_discount(self):
        raw_records = [
            {
                "id": 11,
                "name": "Contract Fatima",
                "employee_id": [43, "Fatima"],
                "x_education_level": "msc",
                "x_is_control_room": True,
                "wage": 15000,
            }
        ]
        client = self._authenticated_client()
        with patch.object(client, "_execute", return_value=raw_records):
            contracts = client.get_contracts(company_id=1)
        assert contracts[0]["effective_hourly_rate"] == 83.25

    def test_missing_education_defaults_to_high_school(self):
        raw_records = [
            {
                "id": 12,
                "name": "Contract Unknown",
                "employee_id": [44, "Unknown"],
                "x_education_level": None,
                "x_is_control_room": False,
                "wage": 5000,
            }
        ]
        client = self._authenticated_client()
        with patch.object(client, "_execute", return_value=raw_records):
            contracts = client.get_contracts(company_id=3)
        assert contracts[0]["effective_hourly_rate"] == 55.0


class TestOdooClientPayrollSync:
    def _authenticated_client(self):
        client = OdooClient(
            host="http://fake-odoo.local",
            database="test_db",
            username="admin",
            api_key="secret_key",
        )
        client._uid = 1
        return client

    def test_sync_daily_wages_returns_ids(self):
        wage_entries = [
            {"employee_id": 42, "date": "2026-08-12", "hours_worked": 8.0,
             "hourly_rate": 77.0, "total_wage": 616.0},
        ]
        client = self._authenticated_client()
        with patch.object(client, "_execute", return_value=99):
            ids = client.sync_daily_wages(company_id=2, wage_entries=wage_entries)
        assert ids == [99]

    def test_sync_multiple_entries(self):
        wage_entries = [
            {"employee_id": 42, "date": "2026-08-12", "hours_worked": 8.0,
             "hourly_rate": 77.0, "total_wage": 616.0},
            {"employee_id": 43, "date": "2026-08-12", "hours_worked": 6.0,
             "hourly_rate": 55.0, "total_wage": 330.0},
        ]
        client = self._authenticated_client()
        call_returns = iter([101, 102])
        with patch.object(client, "_execute", side_effect=call_returns):
            ids = client.sync_daily_wages(company_id=1, wage_entries=wage_entries)
        assert ids == [101, 102]
