"""
Deal Signal Agent — Seed 4: Create email history.

Writes 58 emails across the 16 deals. This is where most of the detectable
signal lives, since the agent reads email metadata (who, which direction,
when) rather than message content for its structural pass.

Each email is associated to both the deal and the specific contact, so the
agent can tell a champion's silence apart from general quiet on the account.

Direction values, confirmed by testing against the API:
  EMAIL           AE sent it
  INCOMING_EMAIL  the prospect sent it
Both use hs_email_status SENT regardless of direction.

Signal by deal:
  A1, H1  AE sends repeatedly, champion never replies
  A2      reply gaps widen 0 -> 3 -> 5 days
  H4      reply gaps widen 2 -> 10 days, then silence from both sides
  A4      prospect engaged early then went quiet
  C4      AE quiet for over a week; prospect reaches out unprompted
  H3      champion still replies, two other stakeholders never do

Everything else is healthy back-and-forth, ending recently enough that no
activity gap trips by accident.

A note on the recent messages dated 12-17 July: earlier versions of this
dataset had every conversation ending weeks before the reference date, which
made almost every deal trip the inactivity threshold regardless of design
intent. Deals meant to look healthy needed a recent touch to actually look
healthy. The fix belongs in the data, not in the scoring rules.

Prerequisites: seed_01 and seed_02 completed.
"""

import json
import time

from config import ASSOC_EMAIL_TO_CONTACT, ASSOC_EMAIL_TO_DEAL
from hubspot_client import post

# (first, last, direction, date, subject, body), chronological within each deal
EMAILS = {
    "C1": [
        ("Elena", "Vasquez", "EMAIL", "2026-07-10", "Contract for review",
         "Sending over the contract for review."),
        ("Elena", "Vasquez", "INCOMING_EMAIL", "2026-07-11", "Re: Contract for review",
         "Thanks, our legal team will take a look this week."),
        ("Elena", "Vasquez", "EMAIL", "2026-07-15", "Checking in on the review",
         "Just wanted to check in as your legal team reviews, happy to hop on a call if useful."),
    ],
    "C2": [
        ("Jennifer", "Ortiz", "EMAIL", "2026-07-06", "Pricing tiers",
         "Wanted to share our team pricing tiers ahead of our call."),
        ("Jennifer", "Ortiz", "INCOMING_EMAIL", "2026-07-08", "Re: Pricing tiers",
         "This is helpful, bringing it to my team this week."),
        ("Jennifer", "Ortiz", "EMAIL", "2026-07-14", "Following up",
         "Wanted to see if you had a chance to discuss with your team yet."),
        ("Jennifer", "Ortiz", "INCOMING_EMAIL", "2026-07-16", "Re: Following up",
         "Just circling back, still discussing internally, will have an update soon."),
    ],
    "C3": [
        ("Michael", "Torres", "EMAIL", "2026-07-09", "Ahead of the demo",
         "Looking forward to the demo, let me know if you'd like anyone else included."),
        ("Michael", "Torres", "INCOMING_EMAIL", "2026-07-10", "Re: Ahead of the demo",
         "Sounds good, I'll loop in Sandra as well."),
        ("Michael", "Torres", "EMAIL", "2026-07-13", "Ahead of next steps",
         "Following up ahead of scheduling next steps with Sandra."),
    ],
    # AE has not reached out since 7 July. The prospect is the one keeping it
    # alive, which is what the AE-side activity gap is meant to surface.
    "C4": [
        ("Angela", "Ferreira", "EMAIL", "2026-07-07", "Implementation timeline",
         "Here's the answer to your question about implementation timeline."),
        ("Angela", "Ferreira", "INCOMING_EMAIL", "2026-07-16", "Checking in",
         "Just checking in, still keen to move forward on our end."),
    ],
    # Contract out, one follow up, no reply at any point.
    "A1": [
        ("Rachel", "Kim", "EMAIL", "2026-07-11", "Updated contract terms",
         "Sending over the updated contract terms as discussed."),
        ("Rachel", "Kim", "EMAIL", "2026-07-15", "Re: Updated contract terms",
         "Just following up on the contract, let me know if you have questions."),
    ],
    # Still replying, but taking steadily longer each time: 0, then 3, then 5 days.
    "A2": [
        ("Nicole", "Andrews", "EMAIL", "2026-06-20", "Recap from today",
         "Great speaking today, sending the recap we discussed."),
        ("Nicole", "Andrews", "INCOMING_EMAIL", "2026-06-20", "Re: Recap from today",
         "Thanks, this looks right!"),
        ("Nicole", "Andrews", "EMAIL", "2026-06-28", "Checking in on next steps",
         "Wanted to check in on timeline for next steps."),
        ("Nicole", "Andrews", "INCOMING_EMAIL", "2026-07-01", "Re: Checking in on next steps",
         "Sorry for the delay, still interested, just juggling priorities."),
        ("Nicole", "Andrews", "EMAIL", "2026-07-10", "Following up again",
         "Following up again, happy to answer any questions."),
        ("Nicole", "Andrews", "INCOMING_EMAIL", "2026-07-15", "Re: Following up again",
         "Apologies for slow reply, this is still on my radar."),
    ],
    # Correspondence is healthy. The only problem here is how long the deal has
    # sat in stage, which keeps this a clean single-signal test case.
    "A3": [
        ("Daniel", "Cho", "EMAIL", "2026-06-20", "Deck from today",
         "Sending over the deck from today's presentation."),
        ("Daniel", "Cho", "INCOMING_EMAIL", "2026-06-23", "Re: Deck from today",
         "Thanks, will review with the team."),
        ("Daniel", "Cho", "EMAIL", "2026-07-14", "Checking in on timing",
         "Wanted to check in on timing for the broader team demo."),
        ("Daniel", "Cho", "INCOMING_EMAIL", "2026-07-17", "Re: Checking in on timing",
         "Thanks for checking in, we are finalizing the demo schedule now."),
    ],
    "A4": [
        ("Melissa", "Grant", "EMAIL", "2026-07-05", "Following up after our call",
         "Wanted to follow up after our call, happy to answer any questions on pricing."),
        ("Melissa", "Grant", "INCOMING_EMAIL", "2026-07-06", "Re: Following up after our call",
         "Thanks, reviewing budget approval now."),
        ("Melissa", "Grant", "EMAIL", "2026-07-08", "Checking in on budget approval",
         "Just checking in on where things stand with budget approval."),
    ],
    # Same shape as A1 but far worse: seven weeks, four attempts, no reply.
    "H1": [
        ("Amanda", "Ross", "EMAIL", "2026-06-01", "Signed contract for review",
         "Sending over the signed contract for your review."),
        ("Amanda", "Ross", "EMAIL", "2026-07-03", "Following up on the contract",
         "Just following up on the contract, wanted to check in."),
        ("Amanda", "Ross", "EMAIL", "2026-07-10", "Re: Following up on the contract",
         "Following up again, please let me know if there are any concerns."),
        ("Amanda", "Ross", "EMAIL", "2026-07-17", "One more follow up",
         "Reaching out once more, happy to jump on a call if useful."),
    ],
    # Reads as perfectly healthy. The repeated reschedules only appear in the
    # AE's note, not anywhere in this correspondence.
    "H2": [
        ("Steven", "Kowalski", "EMAIL", "2026-06-15", "Materials for our review call",
         "Sending over materials ahead of our review call."),
        ("Steven", "Kowalski", "INCOMING_EMAIL", "2026-06-17", "Re: Materials for our review call",
         "Thanks, looking forward to the discussion."),
        ("Steven", "Kowalski", "EMAIL", "2026-06-30", "Confirming our call time",
         "Confirming our upcoming review call time."),
        ("Steven", "Kowalski", "INCOMING_EMAIL", "2026-07-02", "Re: Confirming our call time",
         "Confirmed on our end, talk soon."),
        ("Steven", "Kowalski", "EMAIL", "2026-07-16", "Confirming alignment",
         "Just confirming we're still aligned on rescheduling our review call soon."),
        ("Steven", "Kowalski", "INCOMING_EMAIL", "2026-07-17", "Re: Confirming alignment",
         "Yes, still aligned, will send a new time shortly."),
    ],
    # The champion is still responsive. Two other stakeholders were contacted
    # weeks ago and never replied, narrowing the deal to a single thread.
    "H3": [
        ("Sarah", "Lindqvist", "EMAIL", "2026-07-05", "Technical specs",
         "Sending over the technical specs you requested."),
        ("Sarah", "Lindqvist", "INCOMING_EMAIL", "2026-07-06", "Re: Technical specs",
         "Thanks, this is helpful, reviewing now."),
        ("Michael", "Osei", "EMAIL", "2026-06-20", "Clinical workflow examples",
         "Wanted to share some clinical workflow examples."),
        ("Linda", "Park", "EMAIL", "2026-06-22", "Budget questions follow up",
         "Following up on budget questions from our last call."),
    ],
    # Replies stretch from 2 days to 10, then stop entirely. The AE gave up in
    # early June, so both sides have been silent for weeks.
    "H4": [
        ("Katherine", "Reyes", "EMAIL", "2026-04-20", "Enterprise contract for legal review",
         "Sending over the enterprise contract for legal review."),
        ("Katherine", "Reyes", "INCOMING_EMAIL", "2026-04-22", "Re: Enterprise contract for legal review",
         "Received, forwarding to our legal team."),
        ("Katherine", "Reyes", "EMAIL", "2026-05-10", "Checking in on legal review",
         "Checking in on legal review progress."),
        ("Katherine", "Reyes", "INCOMING_EMAIL", "2026-05-20", "Re: Checking in on legal review",
         "Apologies for delay, still in review internally."),
        ("Katherine", "Reyes", "EMAIL", "2026-06-01", "Following up once more",
         "Following up once more on where things stand."),
    ],
    "N1": [
        ("Brandon", "Lee", "EMAIL", "2026-07-08", "Great meeting you",
         "Great meeting you, sending some initial resources."),
        ("Brandon", "Lee", "INCOMING_EMAIL", "2026-07-10", "Re: Great meeting you",
         "Thanks, would love to see a demo next."),
        ("Brandon", "Lee", "EMAIL", "2026-07-15", "Checking in on the demo",
         "Wanted to see if you had time to look at the demo request."),
    ],
    "N2": [
        ("Jonathan", "Meyer", "EMAIL", "2026-07-06", "Relevant case studies",
         "Wanted to share some case studies relevant to your industry."),
        ("Jonathan", "Meyer", "INCOMING_EMAIL", "2026-07-09", "Re: Relevant case studies",
         "Appreciate this, comparing against one other option currently."),
        ("Jonathan", "Meyer", "EMAIL", "2026-07-13", "Checking in",
         "Checking in on the case studies I sent over."),
    ],
    "N3": [
        ("Derek", "Foster", "EMAIL", "2026-07-03", "Contract for your team's review",
         "Sending over the contract for your team's review."),
        ("Derek", "Foster", "INCOMING_EMAIL", "2026-07-07", "Re: Contract for your team's review",
         "Reviewing now, will follow up with any questions."),
        ("Derek", "Foster", "EMAIL", "2026-07-12", "Contract review timeline",
         "Just following up on the contract review timeline."),
    ],
    "N4": [
        ("Ashley", "Rourke", "EMAIL", "2026-07-02", "Following up after the demo",
         "Following up after the demo, let me know your thoughts."),
        ("Ashley", "Rourke", "INCOMING_EMAIL", "2026-07-05", "Re: Following up after the demo",
         "Really liked what we saw, have a few customization questions."),
        ("Ashley", "Rourke", "EMAIL", "2026-07-14", "Customization questions",
         "Wanted to check in on the customization questions you had."),
    ],
}


def main():
    with open("deal_id_mapping.json") as f:
        deal_lookup = {d["local_id"]: d["hubspot_id"] for d in json.load(f)}

    with open("contact_id_mapping.json") as f:
        contact_lookup = {
            (c["local_deal_id"], c["first_name"], c["last_name"]): c["hubspot_contact_id"]
            for c in json.load(f)
        }

    total = sum(len(v) for v in EMAILS.values())
    print(f"Creating {total} emails across {len(EMAILS)} deals...\n")

    records = []
    count = 0

    for local_id, sequence in EMAILS.items():
        deal_id = deal_lookup[local_id]
        print(f"[{local_id}] {len(sequence)} emails")

        for first, last, direction, date, subject, body in sequence:
            count += 1
            contact_id = contact_lookup.get((local_id, first, last))

            if not contact_id:
                print(f"    SKIP — no contact record for {first} {last}")
                continue

            result = post("/crm/v3/objects/emails", {
                "properties": {
                    "hs_timestamp": f"{date}T14:00:00.000Z",
                    "hs_email_direction": direction,
                    "hs_email_status": "SENT",
                    "hs_email_subject": subject,
                    "hs_email_text": body,
                },
                "associations": [
                    {
                        "to": {"id": deal_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOC_EMAIL_TO_DEAL}],
                    },
                    {
                        "to": {"id": contact_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOC_EMAIL_TO_CONTACT}],
                    },
                ],
            })

            arrow = "->" if direction == "EMAIL" else "<-"
            if result:
                print(f"    [{count}/{total}] {arrow} {first} {last} ({date}) {subject}")
                records.append({
                    "local_deal_id": local_id,
                    "hubspot_email_id": result["id"],
                    "contact_first": first,
                    "contact_last": last,
                    "direction": direction,
                    "date": date,
                })
            else:
                print(f"    [{count}/{total}] FAILED — {first} {last} ({date})")

            time.sleep(0.1)

    with open("email_id_mapping.json", "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nCreated {len(records)}/{total} emails.")


if __name__ == "__main__":
    main()
