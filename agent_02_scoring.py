"""
Deal Signal Agent — Step 2: Structural scoring.

Scores every deal on data that can be computed without reading anything a
human wrote: timestamps, stage durations, field presence. Notes and email
bodies are deliberately out of scope here; they belong to step 3, and only for
deals this step can't resolve on its own.

Four weighted categories, ordered by how hard the signal is to explain away:

  Behavioral (3)  a specific person's engagement changed
  Pace (2)        the deal is slow relative to its segment benchmark
  Activity (1)    nobody has been in touch recently
  Hygiene (0.5)   the CRM record itself has been neglected

Tiers: Clear 0-1.5, Ambiguous 2-4, High-Confidence-Risk 4.5+.

The corroboration rule is the important part. No single category can reach the
top tier alone, even behavioral at 3 points. Champion silence has innocent
explanations, and flagging a VP's largest deal as high risk on one data point
costs more in lost trust than a missed signal costs in lost revenue. Every
high-confidence verdict needs a second, independent category to back it.

The weights and thresholds are reasoned starting points, not calibrated ones.
There is no outcome data behind them, and pretending otherwise by assigning
finer-grained weights would be false precision.
"""

import json
from datetime import datetime

from config import REFERENCE_DATE

WEIGHTS = {
    "behavioral": 3,
    "pace": 2,
    "activity": 1,
    "hygiene": 0.5,
}

CLEAR_MAX = 1.5
AMBIGUOUS_MAX = 4.0

TIER_CLEAR = "Clear"
TIER_AMBIGUOUS = "Ambiguous"
TIER_HIGH_CONFIDENCE = "High-Confidence-Risk"

# Median days in stage, by segment. Derived from published B2B SaaS cycle
# research (Optifai, n=939; Prospeo 2026) rather than from this dataset, since
# a median calculated from 16 self-designed deals would just be the design
# restated back as a benchmark.
#
# Total cycles: 50 days Mid-Market, 120 Enterprise, 200 Enterprise Suite. Later
# stages take a larger share at bigger deal sizes, since legal review and
# procurement scale with contract complexity while first meetings do not.
BENCHMARKS = {
    "Mid-Market": {
        "appointmentscheduled": 6,
        "qualifiedtobuy": 10,
        "presentationscheduled": 12,
        "decisionmakerboughtin": 11,
        "contractsent": 11,
    },
    "Enterprise": {
        "appointmentscheduled": 10,
        "qualifiedtobuy": 18,
        "presentationscheduled": 28,
        "decisionmakerboughtin": 26,
        "contractsent": 38,
    },
    "Enterprise Suite": {
        "appointmentscheduled": 14,
        "qualifiedtobuy": 28,
        "presentationscheduled": 44,
        "decisionmakerboughtin": 42,
        "contractsent": 72,
    },
}

# A deal 20% past its benchmark trips the pace signal. An earlier version used
# 1.5x, which meant nothing registered until a deal was half again past normal,
# too late to be useful. 1.2x is safe because pace alone cannot reach the top
# tier, so a sensitive threshold costs one extra context fetch, not a false alarm.
PACE_MULTIPLIER = 1.2

# Champion silence is only meaningful once the buyer has committed to
# something. Going quiet during early discovery is normal; going quiet after a
# contract arrives is not.
CHAMPION_SILENCE_STAGES = {"contractsent", "decisionmakerboughtin"}
CHAMPION_SILENCE_DAYS = 7

ACTIVITY_GAP_DAYS = 10
CONTACT_DROP_WINDOW_DAYS = 21
LATENCY_GROWTH_DAYS = 3

INBOUND = ("INCOMING_EMAIL", "FORWARDED_EMAIL")
OUTBOUND = ("EMAIL",)


def parse_date(value):
    if not value:
        return None
    value = value.replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def days_since(date):
    return (REFERENCE_DATE - date).days


def score_pace(deal):
    stage_entered = parse_date(deal["stage_entered_date"])
    benchmark = BENCHMARKS.get(deal["segment"], {}).get(deal["stage"])

    if not stage_entered or not benchmark:
        return 0, None

    threshold = benchmark * PACE_MULTIPLIER
    duration = days_since(stage_entered)

    if duration > threshold:
        return WEIGHTS["pace"], (
            f"In stage {duration}d against a {threshold:.0f}d threshold "
            f"({benchmark}d {deal['segment']} benchmark)"
        )
    return 0, None


def score_activity(deal, champion_silence_fired):
    emails = deal["emails"]
    if not emails:
        return 0, None

    outbound = [e for e in emails if e["direction"] in OUTBOUND and e["timestamp"]]
    inbound = [e for e in emails if e["direction"] in INBOUND and e["timestamp"]]

    reasons = []

    if outbound:
        gap = days_since(max(parse_date(e["timestamp"]) for e in outbound))
        if gap >= ACTIVITY_GAP_DAYS:
            reasons.append(f"AE has not reached out in {gap}d")

    if inbound:
        gap = days_since(max(parse_date(e["timestamp"]) for e in inbound))
        if gap >= ACTIVITY_GAP_DAYS:
            reasons.append(f"No prospect reply in {gap}d")
    elif outbound and not champion_silence_fired:
        # Suppressed when champion silence already fired, because that is the
        # same fact described twice. Counting it in both categories would
        # manufacture the corroboration the tier rules are supposed to require.
        reasons.append("No prospect reply on record")

    if reasons:
        return WEIGHTS["activity"], "; ".join(reasons)
    return 0, None


def score_hygiene(deal):
    reasons = []

    if not deal["next_step"]:
        reasons.append("No next step logged")

    close_date = parse_date(deal["close_date"])
    if close_date and close_date < REFERENCE_DATE:
        reasons.append(f"Close date passed on {deal['close_date'][:10]}")

    if reasons:
        return WEIGHTS["hygiene"], "; ".join(reasons)
    return 0, None


def check_champion_silence(emails, champion_id, stage):
    """Champion was contacted after the deal reached a committed stage and never replied."""
    if stage not in CHAMPION_SILENCE_STAGES or not champion_id:
        return None

    sent = [e for e in emails
            if e["contact_id"] == champion_id and e["direction"] in OUTBOUND and e["timestamp"]]
    replies = [e for e in emails
               if e["contact_id"] == champion_id and e["direction"] in INBOUND and e["timestamp"]]

    if not sent or replies:
        return None

    silent_days = days_since(min(parse_date(e["timestamp"]) for e in sent))
    if silent_days >= CHAMPION_SILENCE_DAYS:
        return f"Champion has not replied in {silent_days}d despite outreach"
    return None


def check_contact_drop(emails):
    """A multi-threaded deal has narrowed to one active contact or none."""
    last_touch = {}
    for e in emails:
        if e["contact_id"] and e["timestamp"]:
            date = parse_date(e["timestamp"])
            existing = last_touch.get(e["contact_id"])
            if not existing or date > existing:
                last_touch[e["contact_id"]] = date

    if len(last_touch) < 2:
        return None  # never multi-threaded, so nothing to drop from

    still_active = sum(1 for d in last_touch.values() if days_since(d) <= CONTACT_DROP_WINDOW_DAYS)

    if still_active <= 1 and len(last_touch) - still_active >= 1:
        return f"Engagement narrowed from {len(last_touch)} contacts to {still_active}"
    return None


def check_latency_increase(emails, champion_id):
    """
    The champion still replies, but takes longer each time.

    Pairs each outbound email with the reply that follows it and compares the
    first gap to the last. Needs at least two pairs, so a single slow reply
    does not read as a trend.
    """
    if not champion_id:
        return None

    thread = sorted(
        [e for e in emails if e["contact_id"] == champion_id and e["timestamp"]],
        key=lambda e: parse_date(e["timestamp"]),
    )

    gaps = []
    for current, following in zip(thread, thread[1:]):
        if current["direction"] in OUTBOUND and following["direction"] in INBOUND:
            gaps.append(
                (parse_date(following["timestamp"]) - parse_date(current["timestamp"])).days
            )

    if len(gaps) >= 2 and (gaps[-1] - gaps[0]) >= LATENCY_GROWTH_DAYS:
        return f"Reply time grew from {gaps[0]}d to {gaps[-1]}d across {len(gaps)} exchanges"
    return None


def score_behavioral(deal):
    """
    Returns (score, reason, champion_silence_fired).

    The third value lets the activity check know whether champion silence has
    already accounted for the absence of replies.
    """
    emails = deal["emails"]
    champion_id = deal["champion_contact_id"]

    silence = check_champion_silence(emails, champion_id, deal["stage"])
    triggers = [
        silence,
        check_contact_drop(emails),
        check_latency_increase(emails, champion_id),
    ]
    triggers = [t for t in triggers if t]

    if triggers:
        return WEIGHTS["behavioral"], "; ".join(triggers), bool(silence)
    return 0, None, False


def assign_tier(total, categories_triggered):
    # Corroboration rule: a top-tier score built on one category is downgraded.
    if total > AMBIGUOUS_MAX and categories_triggered < 2:
        return TIER_AMBIGUOUS
    if total <= CLEAR_MAX:
        return TIER_CLEAR
    if total <= AMBIGUOUS_MAX:
        return TIER_AMBIGUOUS
    return TIER_HIGH_CONFIDENCE


def score_deal(deal):
    behavioral, behavioral_reason, silence_fired = score_behavioral(deal)
    pace, pace_reason = score_pace(deal)
    activity, activity_reason = score_activity(deal, silence_fired)
    hygiene, hygiene_reason = score_hygiene(deal)

    scores = [behavioral, pace, activity, hygiene]
    total = sum(scores)
    triggered = sum(1 for s in scores if s > 0)

    return {
        "local_id": deal["local_id"],
        "name": deal["name"],
        "total_score": total,
        "tier": assign_tier(total, triggered),
        "categories_triggered": triggered,
        "behavioral_score": behavioral,
        "pace_score": pace,
        "activity_score": activity,
        "hygiene_score": hygiene,
        "reasons": [r for r in [behavioral_reason, pace_reason, activity_reason, hygiene_reason] if r],
    }


def score_all(deals):
    return [score_deal(d) for d in deals]


def main():
    with open("fetched_deal_data.json") as f:
        deals = json.load(f)

    print(f"Scoring {len(deals)} deals against a reference date of "
          f"{REFERENCE_DATE:%Y-%m-%d}\n")

    results = score_all(deals)

    for r in results:
        print(f"[{r['local_id']}] {r['name']}")
        print(f"    {r['total_score']} points, {r['tier']}, "
              f"{r['categories_triggered']} categor{'y' if r['categories_triggered'] == 1 else 'ies'}")
        for reason in r["reasons"]:
            print(f"      - {reason}")
        print()

    with open("scored_deals.json", "w") as f:
        json.dump(results, f, indent=2)

    counts = {}
    for r in results:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1

    print("Structural tiers:")
    for tier in (TIER_CLEAR, TIER_AMBIGUOUS, TIER_HIGH_CONFIDENCE):
        if tier in counts:
            print(f"  {tier}: {counts[tier]}")

    print(f"\nSaved to scored_deals.json")


if __name__ == "__main__":
    main()
