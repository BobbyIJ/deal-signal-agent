"""
Deal Signal Agent — Setup 1: Create the stage_entered_date custom property.

Run this once against a fresh HubSpot sandbox, before any seed script.

Why a custom property is needed: HubSpot exposes a native
hs_v2_date_entered_current_stage field, which would be the obvious source for
the pace signal. It is read-only (HubSpot calculates it), so a synthetic
dataset can't backdate it to simulate deals that have been sitting in a stage
for weeks. This writable equivalent gives the seed scripts control over stage
duration; against a live CRM the agent would read the native field instead.

Requires the crm.schemas.deals.write scope on the Service Key, which is
separate from the crm.objects.deals.write scope used elsewhere.
"""

from hubspot_client import post

PROPERTY = {
    "name": "stage_entered_date",
    "label": "Stage Entered Date",
    "type": "datetime",
    "fieldType": "date",
    "groupName": "dealinformation",
    "description": "Deal Signal Agent: writable stand-in for stage entry date, used to score pace against benchmark.",
}


def main():
    print("Creating custom deal property 'stage_entered_date'...")

    result = post("/crm/v3/properties/deals", PROPERTY)

    if result:
        print(f"  Created: {result['name']} ({result['type']})")
        print("\nYou can now run seed_01_create_deals.py")
    else:
        print("\nFailed. Two common causes:")
        print("  - The Service Key is missing the crm.schemas.deals.write scope")
        print("  - The property already exists (safe to ignore, continue to the seed scripts)")


if __name__ == "__main__":
    main()
