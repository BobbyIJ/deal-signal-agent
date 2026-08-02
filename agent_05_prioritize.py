"""
Deal Signal Agent — Step 5: Prioritize and compose the brief.

Ranks the at-risk deals for a VP who will read the top of the list and skim
the rest.

Sorting is ordinal: every High-Confidence-Risk deal ranks above every
Confirmed-Risk deal, and within each tier the larger deal ranks first. The
alternative, multiplying deal value by some confidence weight, would need a
number expressing how much more certain one tier is than the other. There is
no data behind such a number, so the ranking would look precise while resting
on an invented ratio.

That leaves one real gap: a large deal with a single confirmed signal can
matter more than a small one with several. Rather than bury that in a blended
score, those deals are flagged. Any Confirmed-Risk deal worth a quarter or
more of the remaining quota gap surfaces in the brief regardless of rank, with
the reason stated, so the VP can make the judgment rather than inherit it.

The brief is the top three plus anything flagged, so a large lower-confidence
deal is never dropped for finishing fourth.

Prerequisite: agent_04_finalize.py has produced final_results.json.
"""

import json

from config import QUOTA_GAP

FLAG_THRESHOLD_PCT = 0.25
FLAG_THRESHOLD_AMOUNT = QUOTA_GAP * FLAG_THRESHOLD_PCT

TIER_RANK = {
    "High-Confidence-Risk": 0,
    "Confirmed-Risk": 1,
}

BRIEF_SIZE = 3


def prioritize(deals):
    at_risk = [d for d in deals if d["final_tier"] in TIER_RANK]
    at_risk.sort(key=lambda d: (TIER_RANK[d["final_tier"]], -d["amount"]))

    for rank, deal in enumerate(at_risk, start=1):
        deal["rank"] = rank
        deal["pct_of_gap"] = round(deal["amount"] / QUOTA_GAP * 100, 1)
        deal["flagged"] = (
            deal["final_tier"] == "Confirmed-Risk"
            and deal["amount"] >= FLAG_THRESHOLD_AMOUNT
        )

    return at_risk


def compose_brief(at_risk):
    top = at_risk[:BRIEF_SIZE]
    top_ids = {d["local_id"] for d in top}
    also_flagged = [d for d in at_risk if d["flagged"] and d["local_id"] not in top_ids]
    return top + also_flagged


def main():
    with open("final_results.json") as f:
        deals = json.load(f)

    at_risk = prioritize(deals)
    brief = compose_brief(at_risk)

    print(f"{len(at_risk)} deals at risk against a ${QUOTA_GAP:,} quota gap")
    print(f"Flag threshold: ${FLAG_THRESHOLD_AMOUNT:,.0f}\n")

    for deal in at_risk:
        flag = "  [flagged: large stakes, lower confidence]" if deal["flagged"] else ""
        print(f"{deal['rank']}. {deal['name']} ({deal['ae']}){flag}")
        print(f"   {deal['final_tier']} | ${deal['amount']:,.0f} | {deal['pct_of_gap']}% of gap")
        print(f"   {deal['explanation']}\n")

    print(f"Brief: {len(brief)} deals "
          f"(top {min(BRIEF_SIZE, len(at_risk))}"
          f"{f' plus {len(brief) - BRIEF_SIZE} flagged' if len(brief) > BRIEF_SIZE else ''})")

    with open("brief_deals.json", "w") as f:
        json.dump(brief, f, indent=2)

    with open("ranked_at_risk.json", "w") as f:
        json.dump(at_risk, f, indent=2)

    print("Saved brief_deals.json and ranked_at_risk.json")


if __name__ == "__main__":
    main()
