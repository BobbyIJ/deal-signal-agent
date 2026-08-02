"""
Deal Signal Agent — Step 1: Observe.

Pulls everything the scoring step needs from HubSpot: deal properties, the
contacts on each deal with the champion identified, and email history.

Two things worth knowing about how this reads from HubSpot.

Champion identification reads the association label from the deal side, which
uses a different type ID than the contact side used to write it. HubSpot
association types are directional and the pairing is not guessable, so both
IDs live in config.py with a note explaining why.

Email history comes from the legacy Engagements v1 API rather than the current
v3 CRM objects API. The v3 endpoint requires a granular email-read scope that
does not appear in the Service Key scope picker, a gap other developers have
reported and HubSpot has not resolved. The Engagements endpoint returns the
same metadata using only the contacts scope. It is a workaround, but a live
one: the data still comes from HubSpot at runtime.

Writes fetched_deal_data.json. The cache exists so the scoring rules can be
tested repeatedly without re-hitting the API, not because the agent depends on
it; agent_run.py holds the same data in memory and never touches disk.
"""

import json
import time
from datetime import datetime, timezone

from config import CHAMPION_LABEL_DEAL_TO_CONTACT
from hubspot_client import get

DEAL_PROPERTIES = "dealname,dealstage,amount,closedate,stage_entered_date,hs_next_step"

EMAIL_TYPES = ("EMAIL", "INCOMING_EMAIL", "FORWARDED_EMAIL")


def get_deal_properties(deal_id):
    result = get(f"/crm/v3/objects/deals/{deal_id}?properties={DEAL_PROPERTIES}")
    return result["properties"] if result else {}


def get_contacts_and_champion(deal_id):
    """Return every associated contact ID, plus whichever carries the Champion label."""
    result = get(f"/crm/v4/objects/deals/{deal_id}/associations/contacts")
    if not result:
        return [], None

    contact_ids = []
    champion_id = None

    for row in result.get("results", []):
        contact_id = row["toObjectId"]
        contact_ids.append(contact_id)

        for assoc in row.get("associationTypes", []):
            is_champion = (
                assoc.get("category") == "USER_DEFINED"
                and assoc.get("typeId") == CHAMPION_LABEL_DEAL_TO_CONTACT
            )
            if is_champion:
                champion_id = contact_id

    return contact_ids, champion_id


def get_emails(deal_id):
    """
    Fetch email metadata via the Engagements API. Timestamps come back as Unix
    epoch milliseconds and are converted to ISO here so the scoring step only
    ever deals with one date format.
    """
    result = get(f"/engagements/v1/engagements/associated/deal/{deal_id}/paged?limit=100")
    if not result:
        return []

    emails = []

    for row in result.get("results", []):
        engagement = row.get("engagement", {})
        if engagement.get("type") not in EMAIL_TYPES:
            continue  # notes and other engagement types are fetched separately

        ts_ms = engagement.get("timestamp")
        timestamp = (
            datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if ts_ms else None
        )

        contact_ids = row.get("associations", {}).get("contactIds", [])

        emails.append({
            "email_id": engagement.get("id"),
            "timestamp": timestamp,
            "direction": engagement.get("type"),
            "contact_id": contact_ids[0] if contact_ids else None,
        })

    return emails


def derive_segment(deal_name):
    """
    Segment drives which pace benchmark applies. It is read from the product
    tier in the deal name, since HubSpot has no native segment field and
    inferring it from deal value alone would misclassify edge cases.
    """
    if "Enterprise Suite" in deal_name:
        return "Enterprise Suite"
    if "Platform" in deal_name:
        return "Enterprise"
    if "Team Analytics" in deal_name:
        return "Mid-Market"
    return "Unknown"


def fetch_deal(local_id, deal_id):
    props = get_deal_properties(deal_id)
    contact_ids, champion_id = get_contacts_and_champion(deal_id)
    emails = get_emails(deal_id)
    deal_name = props.get("dealname", "")

    return {
        "local_id": local_id,
        "deal_id": deal_id,
        "name": deal_name,
        "segment": derive_segment(deal_name),
        "stage": props.get("dealstage"),
        "amount": props.get("amount"),
        "close_date": props.get("closedate"),
        "stage_entered_date": props.get("stage_entered_date"),
        "next_step": props.get("hs_next_step") or None,
        "contact_ids": contact_ids,
        "champion_contact_id": champion_id,
        "emails": emails,
    }


def fetch_all():
    """Fetch every deal in the mapping file. Returns a list of deal records."""
    with open("deal_id_mapping.json") as f:
        deals = json.load(f)

    results = []

    for deal in deals:
        record = fetch_deal(deal["local_id"], deal["hubspot_id"])
        results.append(record)

        champion = "yes" if record["champion_contact_id"] else "NONE"
        print(f"[{record['local_id']}] {record['segment']:16} "
              f"{len(record['contact_ids'])} contacts (champion: {champion}), "
              f"{len(record['emails'])} emails")

        time.sleep(0.1)

    return results


def main():
    print("Fetching deal data from HubSpot...\n")
    results = fetch_all()

    with open("fetched_deal_data.json", "w") as f:
        json.dump(results, f, indent=2)

    missing = [r["local_id"] for r in results if not r["champion_contact_id"]]
    if missing:
        print(f"\nWarning: no champion label found on {', '.join(missing)}.")
        print("Run seed_05_apply_champion_labels.py, or check that")
        print("CHAMPION_LABEL_DEAL_TO_CONTACT in config.py matches this portal.")

    print(f"\nSaved {len(results)} deals to fetched_deal_data.json")


if __name__ == "__main__":
    main()
