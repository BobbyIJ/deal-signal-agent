"""
Deal Signal Agent — Seed 3: Create AE notes and set next steps.

Writes one CRM note per deal, in the register a rep actually uses: short,
written between calls, relative time references rather than exact dates. The
note's timestamp already carries the precise timing, so restating dates in the
prose would be both unrealistic and redundant.

Five notes carry deliberate signal:
  A1, H1  champion has gone quiet after the contract went out
  H2      three reschedules with no new time proposed
  H3      two of three stakeholders unresponsive
  H4      multi-threaded stall, AE already escalating internally

H2 is the important one. Its structural score is only 2.5, so nothing in the
timestamps marks it as high risk. The reschedule pattern exists only in this
note, which is what the conditional fetch in the agent pipeline is there to
find.

The remaining eleven notes are ordinary status logging with no signal. They
matter as controls: if only the risky deals had notes, the agent's judgment
would be trivially easy.

Also sets hs_next_step on every deal except C3, left blank on purpose so the
hygiene indicator has something to catch.

Prerequisite: seed_01 completed.
"""

import json
import time

from config import ASSOC_NOTE_TO_DEAL, REFERENCE_DATE
from hubspot_client import patch, post

NOTES = {
    "C1": "Contract sent, reviewing with their legal team. Elena confirmed they're on track for the original timeline.",
    "C2": "Good call with Jennifer. Walked through pricing tiers, she's bringing it to her team this week.",
    "C3": "Demo went well. Michael wants to loop in Sandra before scheduling next steps.",
    "C4": "Angela gave verbal go ahead. Drafting contract now.",
    "A1": "Sent updated contract terms to Rachel last week. Followed up a few days later with no response. Sending another check in today. Deal still feels warm based on our last call, just slower than expected on their end.",
    "A2": "Quick sync with Nicole. She's still interested, just juggling a few competing priorities this month.",
    "A3": "Second demo scheduled with Daniel's broader team next week.",
    "A4": "Melissa confirmed budget is approved. Waiting on her final sign off before moving to contract.",
    "H1": "Following up with Amanda for the third time this month, still no response since sending the signed contract. Starting to wonder if priorities shifted internally. Will try reaching Christine (CFO) directly if no word by end of week.",
    "H2": "Steven asked to push our review call again. Third reschedule now, no new time proposed yet. Says team is still aligning internally. Keeping this warm but flagging the pattern.",
    "H3": "Dr. Lindqvist remains engaged and responsive, but haven't heard from Dr. Osei or Linda in a few weeks despite two follow up attempts. Might just be bandwidth on their end given clinical schedules, but worth watching.",
    "H4": "Escalating internally. Legal review has been open far longer than usual and Katherine has gone quiet since our last call. Compliance and procurement contacts also unresponsive. Considering looping in our VP to help re engage at the exec level.",
    "N1": "Initial call went well. Brandon wants to see a demo before moving forward.",
    "N2": "Jonathan is comparing us against one other vendor. Sent additional case studies.",
    "N3": "Derek's team reviewing contract terms. No concerns raised so far.",
    "N4": "Ashley requested a few customization details before finalizing. Following up early next week.",
}

# C3 is absent by design: an empty next step is what trips its hygiene signal.
NEXT_STEPS = {
    "C1": "Follow up on legal review timeline",
    "C2": "Send follow-up after internal review",
    "C4": "Send contract for signature",
    "A1": "Send another follow-up to Rachel",
    "A2": "Check in with Nicole next week",
    "A3": "Confirm second demo logistics",
    "A4": "Confirm final sign-off from Melissa",
    "H1": "Attempt to reach Christine (CFO) directly",
    "H2": "Request firm date for rescheduled call",
    "H3": "Follow up with Dr. Osei and Linda",
    "H4": "Escalate to VP for executive engagement",
    "N1": "Schedule demo for Brandon's team",
    "N2": "Follow up on case study review",
    "N3": "Await contract feedback from Derek's team",
    "N4": "Follow up on customization requirements",
}


def main():
    with open("deal_id_mapping.json") as f:
        deal_lookup = {d["local_id"]: d["hubspot_id"] for d in json.load(f)}

    timestamp = REFERENCE_DATE.strftime("%Y-%m-%dT12:00:00.000Z")

    print("Creating notes...")
    notes = []

    for local_id, body in NOTES.items():
        result = post("/crm/v3/objects/notes", {
            "properties": {
                "hs_timestamp": timestamp,
                "hs_note_body": body,
            },
            "associations": [{
                "to": {"id": deal_lookup[local_id]},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOC_NOTE_TO_DEAL}],
            }],
        })

        if result:
            print(f"  [{local_id}] note created")
            notes.append({"local_id": local_id, "hubspot_note_id": result["id"]})
        else:
            print(f"  [{local_id}] FAILED")

        time.sleep(0.1)

    print("\nSetting next steps...")

    for local_id, next_step in NEXT_STEPS.items():
        result = patch(
            f"/crm/v3/objects/deals/{deal_lookup[local_id]}",
            {"properties": {"hs_next_step": next_step}},
        )
        print(f"  [{local_id}] {'set' if result else 'FAILED'}")
        time.sleep(0.1)

    print("  [C3] left blank on purpose (hygiene indicator)")

    with open("note_id_mapping.json", "w") as f:
        json.dump(notes, f, indent=2)

    print(f"\nNotes: {len(notes)}/{len(NOTES)}")
    print(f"Next steps: {len(NEXT_STEPS)}/15, C3 intentionally blank")


if __name__ == "__main__":
    main()
