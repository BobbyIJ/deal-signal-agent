"""
Deal Signal Agent — Step 3: Conditional fetch and reasoning.

This is the step that makes the system an agent rather than a pipeline. Every
deal does not follow the same path: what happens next depends on what the
scoring step found.

  Clear                 no fetch, no model call, no cost. Appears in the full
                        PDF for completeness and nowhere else.
  Ambiguous             fetch the note and resolve it. The note might confirm
                        the concern, overturn it, or reveal something the
                        timestamps could never show.
  High-Confidence-Risk  fetch the note, but the verdict is settled. The job
                        here is to write the explanation a VP will act on.

The prompt for ambiguous deals is written to guard against a specific failure.
An early version escalated deals whenever the note did not contradict the
structural signal, which meant an AE writing "still feels warm" about a silent
champion counted as fresh evidence of risk. It was the same fact scored twice.
The prompt now insists on a concrete new detail before moving a tier, and
defaults to leaving it alone.

Results are cached in enriched_deals.json and reused on re-runs, since each
call costs money and the underlying notes rarely change between runs.

Prerequisite: agent_02_scoring.py has produced scored_deals.json.
"""

import json
import time
import urllib.error
import urllib.request

from config import ANTHROPIC_API_KEY, require
from hubspot_client import get

MODEL = "claude-sonnet-4-6"

# Generous ceiling. The model may spend tokens reasoning before it answers, and
# a tight limit truncates the response mid-JSON. Billing is on tokens used, not
# on the ceiling, so a high limit costs nothing.
MAX_TOKENS = 1024

AMBIGUOUS_TASK = """This deal was flagged as AMBIGUOUS by structural analysis alone (stage duration, email activity gaps, hygiene fields). Read the CRM note below and place it in exactly one of these cases.

1. The note restates or explains something already captured in the structural signals above. An AE describing the same silence or the same slow replies the score already counted is not new evidence, however concerning it sounds, because it is the same fact twice.
   verdict: "corroborated", tier_recommendation: "unchanged"

2. The note contains a concrete, specific fact no timestamp check could surface: a count of meeting reschedules, an internal escalation already underway, a named competing vendor, a stated budget freeze.
   verdict: "new_signal_found", tier_recommendation: "escalate_to_high_confidence"

3. The note gives real positive evidence against the structural flag: expanding stakeholder engagement, a concrete scheduled next step, forward motion the timestamps missed.
   verdict: "contradicted", tier_recommendation: "de-escalate_to_clear"

Default to case 1. Absence of contradiction is not evidence, so do not escalate merely because the note fails to argue against the existing signal."""

HIGH_CONFIDENCE_TASK = """This deal is already established as HIGH-CONFIDENCE-RISK by multiple corroborating structural signals. Do not re-litigate the verdict.

Write the explanation a VP of Sales needs in a prioritized brief: what is actually going wrong, grounded in what the note says, and what it implies about the next move."""


def get_note(deal_id):
    """Fetch the most recent note on a deal, stripped of HubSpot's HTML wrapper."""
    associations = get(f"/crm/v4/objects/deals/{deal_id}/associations/notes")
    if not associations or not associations.get("results"):
        return None

    note_id = associations["results"][0]["toObjectId"]
    note = get(f"/crm/v3/objects/notes/{note_id}?properties=hs_note_body")
    if not note:
        return None

    body = note["properties"].get("hs_note_body", "")
    for tag in ('<div style="" dir="auto" data-top-level="true">',
                '<p style="margin:0;">', "</p>", "</div>"):
        body = body.replace(tag, "")

    return body.strip()


def build_prompt(scored, note_text):
    task = AMBIGUOUS_TASK if scored["tier"] == "Ambiguous" else HIGH_CONFIDENCE_TASK
    signals = "; ".join(scored["reasons"]) if scored["reasons"] else "none"

    return f"""You are the reasoning step in a sales pipeline risk agent for Sans Pareil Analytics, a BI and data platform company.

Deal: {scored['name']}
Structural tier: {scored['tier']}
Structural score: {scored['total_score']}
Signals found: {signals}

Note written by the account executive:
"{note_text}"

{task}

Respond with JSON only, no other text:
{{
  "verdict": "corroborated" | "contradicted" | "new_signal_found" | "enriched",
  "tier_recommendation": "unchanged" | "escalate_to_high_confidence" | "de-escalate_to_clear",
  "explanation": "one or two sentences a VP of Sales can act on, grounded in the note"
}}"""


def call_claude(prompt):
    api_key = require("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as e:
        print(f"    Anthropic API error {e.code}: {e.read().decode()}")
        return None

    # The response may contain several content blocks; take the text one rather
    # than assuming it is first.
    text = next(
        (b.get("text") for b in result.get("content", []) if b.get("type") == "text"),
        None,
    )

    if text is None:
        print("    No text block in the response")
        return None

    text = text.strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    Response was not valid JSON: {e}")
        return None


def load_cache():
    """Prior successful results, so re-runs don't pay for the same calls twice."""
    try:
        with open("enriched_deals.json") as f:
            return {d["local_id"]: d for d in json.load(f) if d.get("claude_reasoning")}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def reason_over(scored_deals, deal_id_lookup, use_cache=True):
    cache = load_cache() if use_cache else {}
    if cache:
        print(f"Reusing {len(cache)} cached result(s) from a previous run.\n")

    results = []

    for scored in scored_deals:
        local_id = scored["local_id"]

        if scored["tier"] == "Clear":
            print(f"[{local_id}] Clear, no fetch")
            results.append({**scored, "claude_reasoning": None})
            continue

        if local_id in cache:
            print(f"[{local_id}] cached")
            results.append(cache[local_id])
            continue

        print(f"[{local_id}] {scored['tier']}, fetching note")
        note_text = get_note(deal_id_lookup[local_id])

        if not note_text:
            print("    no note found")
            results.append({**scored, "claude_reasoning": None})
            continue

        reasoning = call_claude(build_prompt(scored, note_text))

        if reasoning:
            print(f"    {reasoning['verdict']} -> {reasoning['tier_recommendation']}")
            print(f"    {reasoning['explanation']}")
        else:
            print("    reasoning failed, tier will stay as scored")

        results.append({**scored, "claude_reasoning": reasoning})
        time.sleep(0.3)
        print()

    return results


def main():
    with open("scored_deals.json") as f:
        scored_deals = json.load(f)

    with open("deal_id_mapping.json") as f:
        deal_id_lookup = {d["local_id"]: d["hubspot_id"] for d in json.load(f)}

    needs_fetch = sum(1 for d in scored_deals if d["tier"] != "Clear")
    print(f"{len(scored_deals)} deals scored: {needs_fetch} need a closer look, "
          f"{len(scored_deals) - needs_fetch} are clear\n")

    results = reason_over(scored_deals, deal_id_lookup)

    with open("enriched_deals.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"Saved {len(results)} deals to enriched_deals.json")


if __name__ == "__main__":
    main()
