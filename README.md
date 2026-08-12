# A.R.SQLPro6 — Thabot Autonomous Enterprise · Core Backend Middleware

> **ثابوت للتقنيات المستقلة** | Thabot Autonomous Technologies  
> Kingdom of Saudi Arabia · PDPL / SDAIA Compliant · Odoo 19 Enterprise

---

## Overview

This repository serves as the **core backend middleware** for the **Thabot Group** multi-company ecosystem. It provides:

- Multi-company orchestration over **Odoo 19 Enterprise** via JSON-RPC / REST.
- A **Double-Ledger Productivity Engine** (Mizan) with TPC calculations.
- A **Data-Privacy Firewall** enforcing PDPL / SDAIA rules on Edge nodes.
- A **Sprint Manager** implementing the 3-Hour Sprint cadence.
- Hourly-rate payroll sync aligned with Saudi labour tiers.

---

## Thabot Group Ecosystem — 6-Entity Architecture

| # | Entity | Operational Domain | Max Headcount |
|---|--------|--------------------|---------------|
| 1 | **Thabot** | Parent — AI & Robotics R&D | 6 |
| 2 | **Aljazeerah River** (فلاح 1) | Commercial & Water Desalination | 6 |
| 3 | **GF Factory** (فلاح 2) | Industrial Food Production | 6 |
| 4 | **Khubzi Al-Khali** (فلاح 3) | Gluten-Free Bakeries | 6 |
| 5 | **Thabot Logistics** (فلاح 6) | Specialised Transportation Fleet | 6 |
| 6 | **Al-Hayathem Complex** | Business Park + 72-unit Smart Housing | 6 |

**Aggregate limit: 36 employees** across all entities.

---

## Al-Hayathem HQ Specifications

- Location: Al-Hayathem Complex, Kingdom of Saudi Arabia.
- Infrastructure: GCP Saudi region (primary) + Mac Mini Edge nodes (local biometrics processing).
- ERP: Odoo 19 Enterprise — Multi-Company, Payroll, Inventory, and Project modules.

---

## Repository Structure

```
A.R.SQLPro6/
├── config/
│   └── settings.py          # Environment & cloud configuration
├── core/
│   ├── firewall.py          # Data-privacy & jailbreak-prevention module
│   ├── mizan.py             # Double-ledger engine & TPC calculations
│   ├── odoo_client.py       # Odoo 19 JSON-RPC / REST client
│   └── sprint_manager.py   # 3-Hour Sprint state machine
├── tests/
│   ├── test_firewall.py
│   ├── test_mizan.py
│   ├── test_odoo_client.py
│   └── test_sprint_manager.py
└── README.md
```

---

## Payroll Rate Card

| Education Level | Base Rate | T-6 Control Room (−25 %) |
|-----------------|-----------|--------------------------|
| High School     | 55 SAR/hr | 41.25 SAR/hr             |
| BSc             | 77 SAR/hr | 57.75 SAR/hr             |
| MSc             | 111 SAR/hr| 83.25 SAR/hr             |

---

## Compliance

- **PDPL** (Personal Data Protection Law) — all biometric data processed locally on Edge nodes; never transmitted to cloud.
- **SDAIA** ethics guidelines — AI outputs auditable and explainable.
- **Islamic Prayer Schedule** — automated operations are paused 30 minutes per prayer window (5 daily pauses).
