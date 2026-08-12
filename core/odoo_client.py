"""
core/odoo_client.py
~~~~~~~~~~~~~~~~~~~
JSON-RPC / REST client for Odoo 19 Enterprise.

Supported operations:
  - Authenticate via API key (recommended) or username / password.
  - Fetch and manage employee contracts (multi-company).
  - Resolve the effective hourly rate from education level and role.
  - Sync daily wage totals back to Odoo Payroll.
  - Fetch inventory snapshots (multi-company).
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Optional
from urllib.error import URLError

from config.settings import PayrollRates, settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OdooError(Exception):
    """Raised when Odoo returns an error response."""


class OdooAuthError(OdooError):
    """Raised when authentication against Odoo fails."""


# ---------------------------------------------------------------------------
# Low-level JSON-RPC helpers
# ---------------------------------------------------------------------------


def _jsonrpc_call(
    url: str,
    service: str,
    method: str,
    args: list[Any],
    timeout: int = 30,
) -> Any:
    """
    Execute a single Odoo JSON-RPC call and return the ``result`` field.

    Raises ``OdooError`` on JSON-RPC errors.
    """
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": 1,
        }
    ).encode()

    req = urllib.request.Request(
        f"{url}/jsonrpc",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except URLError as exc:
        raise OdooError(f"Network error calling Odoo: {exc}") from exc

    if "error" in body:
        raise OdooError(f"Odoo JSON-RPC error: {body['error']}")

    return body.get("result")


# ---------------------------------------------------------------------------
# OdooClient
# ---------------------------------------------------------------------------


class OdooClient:
    """
    High-level client for Odoo 19 Enterprise.

    Instantiate with explicit credentials or let it fall back to
    ``config.settings``.

    Example::

        client = OdooClient()
        client.authenticate()
        contracts = client.get_contracts(company_id=2)
    """

    def __init__(
        self,
        host: Optional[str] = None,
        database: Optional[str] = None,
        username: Optional[str] = None,
        api_key: Optional[str] = None,
        payroll_rates: Optional[PayrollRates] = None,
    ) -> None:
        self.host = (host or settings.odoo.host).rstrip("/")
        self.database = database or settings.odoo.database
        self.username = username or settings.odoo.username
        self.api_key = api_key or settings.odoo.api_key
        self.rates = payroll_rates or settings.payroll

        self._uid: Optional[int] = None  # set after authentication

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> int:
        """
        Authenticate against Odoo and cache the UID.

        Returns the Odoo user ID (uid).
        Raises ``OdooAuthError`` on failure.
        """
        uid = _jsonrpc_call(
            self.host,
            "common",
            "authenticate",
            [self.database, self.username, self.api_key, {}],
        )
        if not uid:
            raise OdooAuthError(
                f"Authentication failed for user {self.username!r} "
                f"on database {self.database!r}."
            )
        self._uid = uid
        logger.info("Authenticated as Odoo uid=%d", uid)
        return uid

    @property
    def uid(self) -> int:
        if self._uid is None:
            raise OdooAuthError("Not authenticated. Call authenticate() first.")
        return self._uid

    # ------------------------------------------------------------------
    # Low-level execute wrapper
    # ------------------------------------------------------------------

    def _execute(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: Optional[dict[str, Any]] = None,
    ) -> Any:
        return _jsonrpc_call(
            self.host,
            "object",
            "execute_kw",
            [
                self.database,
                self.uid,
                self.api_key,
                model,
                method,
                args,
                kwargs or {},
            ],
        )

    # ------------------------------------------------------------------
    # Employee / Contract management
    # ------------------------------------------------------------------

    def get_contracts(
        self, company_id: int, active_only: bool = True
    ) -> list[dict[str, Any]]:
        """
        Fetch employee contracts for *company_id*.

        Returns a list of contract dicts with keys:
        ``id``, ``name``, ``employee_id``, ``education_level``,
        ``is_control_room``, ``hourly_rate``.
        """
        domain: list[Any] = [("company_id", "=", company_id)]
        if active_only:
            domain.append(("state", "=", "open"))

        records = self._execute(
            "hr.contract",
            "search_read",
            [domain],
            {
                "fields": [
                    "id",
                    "name",
                    "employee_id",
                    "x_education_level",   # custom field
                    "x_is_control_room",   # custom field
                    "wage",
                ],
                "context": {"allowed_company_ids": [company_id]},
            },
        )
        return self._enrich_contracts(records)

    def _enrich_contracts(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Attach computed hourly_rate to each contract record."""
        for rec in records:
            edu = rec.get("x_education_level", "high_school") or "high_school"
            is_cr = bool(rec.get("x_is_control_room", False))
            rec["effective_hourly_rate"] = self.rates.effective_rate(edu, is_cr)
        return records

    # ------------------------------------------------------------------
    # Payroll sync
    # ------------------------------------------------------------------

    def sync_daily_wages(
        self, company_id: int, wage_entries: list[dict[str, Any]]
    ) -> list[int]:
        """
        Write finalised daily wages back to Odoo Payroll.

        *wage_entries* should be a list of dicts::

            [
                {
                    "employee_id": 42,
                    "date": "2026-08-12",
                    "hours_worked": 8.0,
                    "hourly_rate": 77.0,
                    "total_wage": 616.0,
                },
                ...
            ]

        Returns a list of created ``hr.payslip.line`` IDs.
        """
        created_ids: list[int] = []
        for entry in wage_entries:
            vals = {
                "employee_id": entry["employee_id"],
                "date_from": entry["date"],
                "date_to": entry["date"],
                "company_id": company_id,
                "x_hours_worked": entry.get("hours_worked", 0),
                "x_hourly_rate": entry.get("hourly_rate", 0),
                "x_total_daily_wage": entry.get("total_wage", 0),
            }
            rec_id = self._execute(
                "hr.payslip",
                "create",
                [vals],
                {"context": {"allowed_company_ids": [company_id]}},
            )
            logger.info("Created payslip id=%s for employee [REDACTED]", rec_id)
            created_ids.append(rec_id)

        return created_ids

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def get_inventory_snapshot(self, company_id: int) -> list[dict[str, Any]]:
        """Return current stock quant records for *company_id*."""
        return self._execute(
            "stock.quant",
            "search_read",
            [[("company_id", "=", company_id)]],
            {
                "fields": ["product_id", "location_id", "quantity", "reserved_quantity"],
                "context": {"allowed_company_ids": [company_id]},
            },
        )
