"""
Deal Signal Agent — Seed 5: Create and apply the Champion association label.

Marks one contact per deal as that deal's champion, so the agent can tell the
difference between "this account has gone quiet" and "the person who was
driving this purchase has gone quiet". The second is a much stronger signal.

Why a custom association label rather than a contact property: HubSpot ships a
native hs_buying_role field with a Champion option, which looks like the right
answer until you notice it lives on the contact record. A procurement lead
evaluating two deals would be marked champion on both, or neither. Association
labels attach to the specific contact-deal pair, so the same person can be a
champion on one deal and a bystander on another. That matches how buying
committees actually work.

Creating a label requires Super Admin permissions on the portal.

Prerequisites: seed_01 and seed_02 completed.
"""

import json
import time

from config import ASSOC_CONTACT_TO_DEAL
from hubspot_client import get, post, put

LABEL_NAME = "champion"
LABEL_DISPLAY = "Champion"


def find_existing_label():
    """Return the contact-to-deal typeId for the Champion label, if present."""
    result = get("/crm/v4/associations/contacts/deals/labels")
    if not result:
        return None

    for entry in result.get("results", []):
        if entry.get("label") == LABEL_DISPLAY:
            return entry["typeId"]
    return None


def create_label():
    """
    Create the label and return its contact-to-deal typeId.

    HubSpot creates labels in pairs, one per direction, and returns both. The
    lower ID is the contact-to-deal direction used for writing here; the other
    is what the agent reads from the deal side.
    """
    result = post(
        "/crm/v4/associations/contacts/deals/labels",
        {"label": LABEL_DISPLAY, "name": LABEL_NAME},
    )
    if not result:
        return None

    type_ids = [e["typeId"] for e in result.get("results", []) if e.get("label") == LABEL_DISPLAY]
    return min(type_ids) if type_ids else None


def main():
    print("Checking for an existing Champion label...")
    type_id = find_existing_label()

    if type_id:
        print(f"  Already exists, typeId {type_id}")
    else:
        print("  Not found, creating it...")
        type_id = create_label()
        if not type_id:
            raise SystemExit(
                "Could not create the label. This endpoint requires Super Admin "
                "permissions on the portal."
            )
        print(f"  Created, typeId {type_id}")

    with open("contact_answer_key.json") as f:
        champions = [c for c in json.load(f) if c["is_intended_champion"]]

    with open("deal_id_mapping.json") as f:
        deal_lookup = {d["local_id"]: d["hubspot_id"] for d in json.load(f)}

    print(f"\nApplying the label to {len(champions)} contacts...")
    applied = 0

    for champion in champions:
        deal_id = deal_lookup.get(champion["local_deal_id"])
        if not deal_id:
            print(f"  [{champion['local_deal_id']}] SKIP — deal not found")
            continue

        # Send both the default association and the Champion label together.
        # A PUT replaces the full set of association types, so omitting the
        # default here would silently unlink the contact from the deal.
        result = put(
            f"/crm/v4/objects/contacts/{champion['hubspot_contact_id']}/associations/deals/{deal_id}",
            [
                {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOC_CONTACT_TO_DEAL},
                {"associationCategory": "USER_DEFINED", "associationTypeId": type_id},
            ],
        )

        if result is not None:
            print(f"  [{champion['local_deal_id']}] {champion['email']}")
            applied += 1
        else:
            print(f"  [{champion['local_deal_id']}] FAILED")

        time.sleep(0.1)

    print(f"\nApplied {applied}/{len(champions)} champion labels.")

    if type_id != 1:
        print(
            f"\nNote: this portal assigned typeId {type_id} rather than 1. Update "
            f"CHAMPION_LABEL_CONTACT_TO_DEAL in config.py, and set "
            f"CHAMPION_LABEL_DEAL_TO_CONTACT to the paired ID."
        )


if __name__ == "__main__":
    main()
