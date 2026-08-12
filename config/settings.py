"""
config/settings.py
~~~~~~~~~~~~~~~~~~
Environment and cloud configuration for the Thabot Autonomous Enterprise
middleware.  Supports three deployment tiers:

  - local   : Mac Mini Edge nodes (biometric processing, PDPL compliance)
  - staging : GCP Saudi region — pre-production
  - cloud   : GCP Saudi region — production (Odoo 19 Enterprise)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Environment(str, Enum):
    LOCAL = "local"
    STAGING = "staging"
    CLOUD = "cloud"


@dataclass
class OdooConfig:
    """Connection parameters for Odoo 19 Enterprise."""

    host: str = os.getenv("ODOO_HOST", "https://thabot.odoo.com")
    port: int = int(os.getenv("ODOO_PORT", "443"))
    database: str = os.getenv("ODOO_DB", "thabot_prod")
    username: str = os.getenv("ODOO_USER", "")
    api_key: str = os.getenv("ODOO_API_KEY", "")
    # Multi-company IDs (resolved at runtime from Odoo)
    company_ids: dict[str, int] = field(
        default_factory=lambda: {
            "thabot": 1,
            "aljazeerah_river": 2,
            "gf_factory": 3,
            "khubzi_al_khali": 4,
            "thabot_logistics": 5,
            "al_hayathem_complex": 6,
        }
    )


@dataclass
class GCPConfig:
    """Google Cloud Platform — Saudi region settings."""

    project_id: str = os.getenv("GCP_PROJECT_ID", "thabot-ksa")
    region: str = os.getenv("GCP_REGION", "me-central2")  # GCP Saudi
    bucket_name: str = os.getenv("GCP_BUCKET", "thabot-payroll-exports")
    service_account_json: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


@dataclass
class EdgeNodeConfig:
    """Mac Mini Edge node — local biometric processing (PDPL compliant)."""

    node_id: str = os.getenv("EDGE_NODE_ID", "edge-alhayathem-01")
    # Biometric data MUST remain on this node; never forwarded to cloud.
    biometric_storage_path: str = os.getenv(
        "BIOMETRIC_STORAGE_PATH", "/var/thabot/biometrics"
    )
    # Encryption key reference (key stored in local macOS Keychain)
    keychain_service: str = "thabot.biometrics"


@dataclass
class SprintConfig:
    """3-Hour Sprint cadence settings."""

    sprint_duration_hours: int = 3
    daily_sprints: int = 4  # 12 productive hours / 3-hour blocks
    # Prayer pause duration in minutes (applied 5 times per day)
    prayer_pause_minutes: int = 30


@dataclass
class PayrollRates:
    """Hourly base rates in SAR by education level."""

    high_school: float = 55.0
    bsc: float = 77.0
    msc: float = 111.0
    # T-6 Control Room static staff discount
    control_room_discount: float = 0.25

    def effective_rate(self, education: str, is_control_room: bool = False) -> float:
        """Return the effective hourly rate (SAR) for a given education level."""
        base_map = {
            "high_school": self.high_school,
            "bsc": self.bsc,
            "msc": self.msc,
        }
        base = base_map.get(education.lower())
        if base is None:
            raise ValueError(f"Unknown education level: {education!r}")
        if is_control_room:
            base *= 1 - self.control_room_discount
        return round(base, 2)


@dataclass
class Settings:
    """Top-level settings object — instantiate once and pass around."""

    env: Environment = Environment(os.getenv("APP_ENV", "local"))
    odoo: OdooConfig = field(default_factory=OdooConfig)
    gcp: GCPConfig = field(default_factory=GCPConfig)
    edge: EdgeNodeConfig = field(default_factory=EdgeNodeConfig)
    sprint: SprintConfig = field(default_factory=SprintConfig)
    payroll: PayrollRates = field(default_factory=PayrollRates)
    max_employees_per_entity: int = 6
    total_employee_cap: int = 36


# Module-level singleton — import this in other modules.
settings = Settings()
