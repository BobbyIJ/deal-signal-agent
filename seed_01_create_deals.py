"""
Deal Signal Agent — Seed 1: Create deals.

Creates the 16-deal synthetic pipeline for Sans Pareil Analytics, a fictional
BI and data analytics company selling into Mid-Market and Enterprise segments.

Each deal is reverse-engineered from a target risk score: field values are set
so that the scoring rules in agent_02_scoring.py should produce a specific,
known result. That makes the dataset double as a validation suite, since the
expected answer for each deal is known before the agent ever runs.

Four "noise" deals (N1-N4) deliberately have no target score. They exist so
the scoring logic gets exercised against cases that weren't hand-tuned to
match its own rules, which a fully reverse-engineered dataset can't do.

Outputs two files, kept separate on purpose:
  deal_id_mapping.json  - operational data the later scripts read
  deal_answer_key.json  - target scores, for manual verification only

Nothing in the agent pipeline reads the answer key. Keeping it in a separate
file makes that boundary structural rather than a rule to remember.

Prerequisites: setup_01 and setup_02 completed.
"""

import json
import time
from datetime import timedelta

from config import OWNERS, REFERENCE_DATE
from hubspot_client import post

# HubSpot internal stage IDs for the default sales pipeline.
STAGES = {
    "Appointment Scheduled": "appointmentscheduled",
    "Qualified To Buy": "qualifiedtobuy",
    "Presentation Scheduled": "presentationscheduled",
    "Decision Maker Bought-In": "decisionmakerboughtin",
    "Contract Sent": "contractsent",
}


def days_ago(n):
    """ISO timestamp for n days before the frozen reference date."""
    return (REFERENCE_DATE - timedelta(days=n)).strftime("%Y-%m-%dT12:00:00.000Z")


def on(month, day):
    """ISO timestamp for a specific 2026 date."""
    return f"2026-{month:02d}-{day:02d}T12:00:00.000Z"


# =============================================================================
# THE PIPELINE
#
# Product tier drives segment, which drives the pace benchmark the agent scores
# against: Team Analytics is Mid-Market, Platform is Enterprise, Enterprise
# Suite is its own tier. The suffix in each deal name is what the agent reads
# to determine segment.
# =============================================================================

DEALS = [
    # -------------------------------------------------------------------------
    # Expected Clear (0 - 1.5)
    # -------------------------------------------------------------------------
    {
        "id": "C1", "name": "Ridgeline Health Systems — Platform",
        "ae": "Sarah Chen", "amount": 180000,
        "stage": "Contract Sent", "close_date": on(8, 2), "stage_entered": days_ago(5),
        "target_score": 0, "expected_triggers": "None",
    },
    {
        "id": "C2", "name": "Foxwood Credit Union — Team Analytics",
        "ae": "James Rodriguez", "amount": 45000,
        "stage": "Qualified To Buy", "close_date": on(8, 14), "stage_entered": days_ago(8),
        "target_score": 0, "expected_triggers": "None",
    },
    {
        "id": "C3", "name": "Atlas Logistics — Team Analytics",
        "ae": "James Rodriguez", "amount": 95000,
        "stage": "Presentation Scheduled", "close_date": on(8, 8), "stage_entered": days_ago(6),
        "target_score": 0.5, "expected_triggers": "Hygiene: no next step logged",
    },
    {
        "id": "C4", "name": "Halcyon Manufacturing — Team Analytics",
        "ae": "James Rodriguez", "amount": 120000,
        "stage": "Decision Maker Bought-In", "close_date": on(8, 6), "stage_entered": days_ago(10),
        "target_score": 1, "expected_triggers": "Activity: AE outbound gap",
    },

    # -------------------------------------------------------------------------
    # Expected Ambiguous (2 - 4)
    # -------------------------------------------------------------------------
    {
        # Matched pair with H1: same behavioral trigger, same stage, similar
        # value, same AE. H1 additionally trips the pace signal, which is what
        # pushes it over the corroboration threshold while A1 stays Ambiguous.
        "id": "A1", "name": "Palisade Media Group — Platform",
        "ae": "Sarah Chen", "amount": 150000,
        "stage": "Contract Sent", "close_date": on(7, 27), "stage_entered": days_ago(8),
        "target_score": 3, "expected_triggers": "Behavioral: champion silence",
    },
    {
        "id": "A2", "name": "Crestline SaaS — Team Analytics",
        "ae": "James Rodriguez", "amount": 85000,
        "stage": "Decision Maker Bought-In", "close_date": on(8, 4), "stage_entered": days_ago(7),
        "target_score": 3, "expected_triggers": "Behavioral: reply latency increasing",
    },
    {
        "id": "A3", "name": "Stratos Insurance — Platform",
        "ae": "Marcus Thompson", "amount": 175000,
        "stage": "Presentation Scheduled", "close_date": on(6, 28), "stage_entered": days_ago(35),
        "target_score": 2.5, "expected_triggers": "Pace + Hygiene: close date lapsed",
    },
    {
        "id": "A4", "name": "Driftwood Brands — Team Analytics",
        "ae": "James Rodriguez", "amount": 70000,
        "stage": "Qualified To Buy", "close_date": on(7, 14), "stage_entered": days_ago(14),
        "target_score": 3.5, "expected_triggers": "Pace + Activity + Hygiene: close date lapsed",
    },

    # -------------------------------------------------------------------------
    # Expected High-Confidence-Risk (4.5+)
    # -------------------------------------------------------------------------
    {
        "id": "H1", "name": "Ironshore Capital — Platform",
        "ae": "Sarah Chen", "amount": 160000,
        "stage": "Contract Sent", "close_date": on(6, 18), "stage_entered": days_ago(48),
        "target_score": 5.5, "expected_triggers": "Behavioral: champion silence + Pace + Hygiene",
    },
    {
        # Scores 2.5 structurally. The reschedule pattern that makes this a real
        # risk exists only in the AE's note, so this deal is the clearest test
        # of whether the Phase 3 fetch is doing useful work.
        "id": "H2", "name": "Keystone Freight — Platform",
        "ae": "Marcus Thompson", "amount": 275000,
        "stage": "Decision Maker Bought-In", "close_date": on(6, 30), "stage_entered": days_ago(34),
        "target_score": 2.5, "expected_triggers": "Pace + Hygiene structurally; reschedule pattern via note",
    },
    {
        # Lands exactly on the 4.5 boundary, which catches off-by-one errors in
        # the tier comparison.
        "id": "H3", "name": "Orion Therapeutics — Platform",
        "ae": "Marcus Thompson", "amount": 190000,
        "stage": "Presentation Scheduled", "close_date": on(7, 12), "stage_entered": days_ago(9),
        "target_score": 4.5, "expected_triggers": "Behavioral: contact drop + Activity + Hygiene",
    },
    {
        "id": "H4", "name": "Blackwater Industrial — Enterprise Suite",
        "ae": "Marcus Thompson", "amount": 450000,
        "stage": "Contract Sent", "close_date": on(5, 10), "stage_entered": days_ago(90),
        "target_score": 6.5, "expected_triggers": "All four categories",
    },

    # -------------------------------------------------------------------------
    # Noise: no target score, outcome not predetermined
    # -------------------------------------------------------------------------
    {
        "id": "N1", "name": "Timber Ridge Co-op — Team Analytics",
        "ae": "James Rodriguez", "amount": 65000,
        "stage": "Appointment Scheduled", "close_date": on(8, 19), "stage_entered": days_ago(7),
        "target_score": None, "expected_triggers": None,
    },
    {
        "id": "N2", "name": "Vanguard Property Group — Platform",
        "ae": "Sarah Chen", "amount": 200000,
        "stage": "Qualified To Buy", "close_date": on(8, 9), "stage_entered": days_ago(9),
        "target_score": None, "expected_triggers": None,
    },
    {
        "id": "N3", "name": "Apex Distribution — Platform",
        "ae": "Marcus Thompson", "amount": 250000,
        "stage": "Contract Sent", "close_date": on(8, 12), "stage_entered": days_ago(11),
        "target_score": None, "expected_triggers": None,
    },
    {
        "id": "N4", "name": "Pinehurst Digital — Team Analytics",
        "ae": "James Rodriguez", "amount": 55000,
        "stage": "Presentation Scheduled", "close_date": on(8, 4), "stage_entered": days_ago(12),
        "target_score": None, "expected_triggers": None,
    },
]


def main():
    print(f"Reference date: {REFERENCE_DATE:%Y-%m-%d}")
    print(f"Creating {len(DEALS)} deals...\n")

    created = []

    for deal in DEALS:
        payload = {
            "properties": {
                "dealname": deal["name"],
                "dealstage": STAGES[deal["stage"]],
                "amount": str(deal["amount"]),
                "closedate": deal["close_date"],
                "hubspot_owner_id": OWNERS[deal["ae"]],
                "stage_entered_date": deal["stage_entered"],
                "pipeline": "default",
            }
        }

        result = post("/crm/v3/objects/deals", payload)

        if result:
            print(f"  [{deal['id']}] {deal['name']}")
            print(f"       {deal['ae']} | {deal['stage']} | ${deal['amount']:,} | id {result['id']}")
            created.append({**deal, "hubspot_id": result["id"]})
        else:
            print(f"  [{deal['id']}] FAILED")

        time.sleep(0.1)

    # Operational mapping: what the rest of the pipeline is allowed to read.
    with open("deal_id_mapping.json", "w") as f:
        json.dump([
            {
                "local_id": d["id"],
                "hubspot_id": d["hubspot_id"],
                "name": d["name"],
                "ae": d["ae"],
            }
            for d in created
        ], f, indent=2)

    # Answer key: design intent, for eyeballing the agent's output afterwards.
    with open("deal_answer_key.json", "w") as f:
        json.dump([
            {
                "local_id": d["id"],
                "hubspot_id": d["hubspot_id"],
                "target_score": d["target_score"],
                "expected_triggers": d["expected_triggers"],
            }
            for d in created
        ], f, indent=2)

    print(f"\nCreated {len(created)}/{len(DEALS)} deals.")
    print("  deal_id_mapping.json  (used by the pipeline)")
    print("  deal_answer_key.json  (manual verification only)")


if __name__ == "__main__":
    main()
