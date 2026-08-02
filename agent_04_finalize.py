"""
Deal Signal Agent — Step 4: Reconcile the final tier.

Combines what the structural scoring found with what the model concluded from
the note, and settles on one tier per deal.

  Clear stays Clear                     no fetch happened, nothing to revisit
  Ambiguous + corroborated              Confirmed-Risk
  Ambiguous + new signal found          High-Confidence-Risk
  Ambiguous + contradicted              Clear
  Ambiguous + no reasoning available    stays Ambiguous
  High-Confidence-Risk                  unchanged, the note only added detail

Confirmed-Risk is a deliberate middle tier rather than a rounding of Ambiguous
up or down. It means the risk is real but rests on a single structural signal
the note merely restated, which is genuinely different from a deal where two
independent signals agree. The brief shows that distinction so a VP can weight
it themselves.

When the model produced nothing, the tier holds rather than resolving in either
direction. Guessing without reasoning would defeat the point of fetching.

Prerequisite: agent_03_reason.py has produced enriched_deals.json.
"""

import json

TIER_CLEAR = "Clear"
TIER_AMBIGUOUS = "Ambiguous"
TIER_CONFIRMED = "Confirmed-Risk"
TIER_HIGH_CONFIDENCE = "High-Confidence-Risk"

VERDICT_TO_TIER = {
    "contradicted": TIER_CLEAR,
    "new_signal_found": TIER_HIGH_CONFIDENCE,
    "corroborated": TIER_CONFIRMED,
}

TIER_DISPLAY_ORDER = [TIER_HIGH_CONFIDENCE, TIER_CONFIRMED, TIER_AMBIGUOUS, TIER_CLEAR]


def reconcile_tier(structural_tier, reasoning):
    if structural_tier == TIER_CLEAR:
        return TIER_CLEAR

    if structural_tier == TIER_HIGH_CONFIDENCE:
        return TIER_HIGH_CONFIDENCE

    if not reasoning:
        return TIER_AMBIGUOUS

    return VERDICT_TO_TIER.get(reasoning.get("verdict"), TIER_AMBIGUOUS)


def build_explanation(deal):
    structural = "; ".join(deal["reasons"]) if deal["reasons"] else "No structural signals"
    reasoning = deal.get("claude_reasoning")

    if not reasoning:
        return structural

    return f"{reasoning['explanation']} (Structural basis: {structural})"


def finalize(enriched_deals, amounts, segments, aes):
    results = []

    for deal in enriched_deals:
        local_id = deal["local_id"]

        results.append({
            "local_id": local_id,
            "name": deal["name"],
            "ae": aes.get(local_id),
            "amount": float(amounts.get(local_id, 0)),
            "segment": segments.get(local_id),
            "structural_tier": deal["tier"],
            "structural_score": deal["total_score"],
            "final_tier": reconcile_tier(deal["tier"], deal.get("claude_reasoning")),
            "explanation": build_explanation(deal),
        })

    return results


def main():
    with open("enriched_deals.json") as f:
        enriched = json.load(f)

    with open("fetched_deal_data.json") as f:
        fetched = json.load(f)
    amounts = {d["local_id"]: d["amount"] for d in fetched}
    segments = {d["local_id"]: d["segment"] for d in fetched}

    with open("deal_id_mapping.json") as f:
        aes = {d["local_id"]: d["ae"] for d in json.load(f)}

    results = finalize(enriched, amounts, segments, aes)

    print(f"Reconciling {len(results)} deals\n")

    for r in results:
        moved = "" if r["structural_tier"] == r["final_tier"] else "  <- changed by the note"
        print(f"[{r['local_id']}] {r['name']}")
        print(f"    {r['structural_tier']} ({r['structural_score']}) -> {r['final_tier']}{moved}")

    with open("final_results.json", "w") as f:
        json.dump(results, f, indent=2)

    counts = {}
    for r in results:
        counts[r["final_tier"]] = counts.get(r["final_tier"], 0) + 1

    print("\nFinal tiers:")
    for tier in TIER_DISPLAY_ORDER:
        if tier in counts:
            print(f"  {tier}: {counts[tier]}")

    print("\nSaved to final_results.json")


if __name__ == "__main__":
    main()
