"""
Deal Signal Agent — Run the full pipeline.

Runs every step in sequence, holding data in memory rather than reading and
writing the intermediate JSON files. This is the production-shaped entry point:
one scheduled trigger, one pass, one delivered brief.

The individual agent_0*.py scripts do the same work but persist their output at
each stage, which is what makes the scoring rules testable in isolation without
re-hitting the API or paying for model calls on every iteration. Those files
are a development convenience. Nothing in the agent's logic depends on them.

Usage:
    python agent_run.py            full run, posts to Slack
    python agent_run.py --dry-run  everything except posting
"""

import json
import sys

import agent_01_fetch as fetch
import agent_02_scoring as scoring
import agent_03_reason as reason
import agent_04_finalize as finalize
import agent_05_prioritize as prioritize


def main():
    dry_run = "--dry-run" in sys.argv

    with open("deal_id_mapping.json") as f:
        mapping = json.load(f)
    deal_id_lookup = {d["local_id"]: d["hubspot_id"] for d in mapping}
    aes = {d["local_id"]: d["ae"] for d in mapping}

    print("Observing: pulling deals from HubSpot")
    deals = fetch.fetch_all()

    print("\nScoring against structural signals")
    scored = scoring.score_all(deals)

    needs_review = sum(1 for d in scored if d["tier"] != "Clear")
    print(f"  {needs_review} of {len(scored)} deals need a closer look\n")

    print("Reading notes on the deals that need one")
    # use_cache=False so a scheduled run always reflects current CRM content
    enriched = reason.reason_over(scored, deal_id_lookup, use_cache=False)

    print("\nReconciling final tiers")
    amounts = {d["local_id"]: d["amount"] for d in deals}
    segments = {d["local_id"]: d["segment"] for d in deals}
    final = finalize.finalize(enriched, amounts, segments, aes)

    at_risk = prioritize.prioritize(final)
    brief = prioritize.compose_brief(at_risk)

    print(f"\n{len(at_risk)} deals at risk, {len(brief)} in the brief:")
    for deal in brief:
        flag = " [flagged]" if deal.get("flagged") else ""
        print(f"  {deal['rank']}. {deal['name']} ({deal['ae']}, ${deal['amount']:,.0f}){flag}")

    if dry_run:
        print("\nDry run, nothing delivered.")
        return

    # The PDF and Slack steps read from disk, so persist what they need.
    with open("final_results.json", "w") as f:
        json.dump(final, f, indent=2)
    with open("brief_deals.json", "w") as f:
        json.dump(brief, f, indent=2)

    import agent_06_generate_pdf as pdf
    import agent_07_deliver as deliver

    print("\nGenerating the pre-read")
    pdf.main()

    print("Delivering to Slack")
    deliver.main()


if __name__ == "__main__":
    main()
