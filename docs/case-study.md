# Deal Signal Agent — Case Study

## Overview

Deal Signal Agent reads a B2B sales pipeline from HubSpot, works out which
deals are at risk and why, and delivers a prioritized brief to a VP of Sales in
Slack with a full pre-read PDF attached. It runs against a 16-deal synthetic
pipeline built for a fictional BI and data analytics company, Sans Pareil
Analytics, with 59 contacts, 58 emails, and 16 AE-written notes spread across
three reps covering Enterprise and Mid-Market.

This is not a production deployment. It is a working system that pulls from
real APIs, makes conditional decisions about which deals need deeper
investigation, calls Claude to reason over actual CRM content, and posts to a
real Slack channel. Every design decision below was made before the code that
implements it was written, and every claim about the system's behavior was
checked against known expected outcomes after it ran.

---

## Problem framing

The starting question sounds simple: why do deals slip through pipeline
reviews? The obvious answer, that nobody noticed, turns out to be wrong. AEs
usually have some sense a deal is softening. What breaks down is what happens
to that awareness before it reaches anyone who can act on it.

Four distinct failure modes:

- **Limited AE bandwidth.** A rep carrying 30 to 50 live deals can't watch all
  of them equally. Attention goes to whichever deal is loudest that week, not
  necessarily the one that most needs it. The concern exists in the rep's head
  but doesn't surface until the Monday review, by which point the window to
  intervene has narrowed.
- **Incentive to keep deals looking healthy.** A rep under quota pressure has a
  rational reason to leave a wobbly deal marked on track for as long as
  possible. The stage doesn't move because the rep hasn't given up, not because
  the deal is fine.
- **Risk shows up outside structured fields first.** A reply that took a week
  instead of a day, a hedge in a call note, a rescheduled meeting. None of that
  changes a CRM field, and the VP only sees fields.
- **No cross-team visibility.** Even with every rep individually well informed,
  the VP is trying to read a pattern across eight to twelve pipelines at once.
  No rep is positioned or incentivized to roll that up.

The VP of Sales is the primary consumer because they carry the consequence.
They're accountable for the number and they find out a deal is dying in the
same meeting where it's too late. The agent's job is to close the gap between
"the signal is somewhere in the CRM" and "the VP knows and can act."

---

## Signal hierarchy design

Treating risk signals as a flat list produces either noise or blind spots.
The hierarchy ended up as two separate axes, after an early version that
combined detection confidence and business impact into a single number didn't
hold up: it would rank a large healthy deal above a small dying one.

### Axis 1: Detection

Nine indicators across four categories, weighted by how hard the signal is to
explain away.

**Behavioral (3 points).** Four indicators, all about a specific person's
engagement changing rather than general quiet:

- Champion silence after a proposal: the primary contact stops replying once
  contract terms are out
- Contact count dropping: engagement narrows from several stakeholders to one
  or none
- Reply latency growing: the person who answered same-day during discovery now
  takes four or five days
- Meeting reschedules: two or more with no new time proposed

A fifth indicator, detecting hedging language or tone shifts in prospect
emails, was designed and then dropped. Hand-writing synthetic emails that
demonstrate a sentiment shift convincingly would be difficult to distinguish
from a rigged demo, so it's noted as a future extension rather than built.

**Pace against benchmark (2 points).** Compares time in current stage against a
per-segment, per-stage median. Benchmarks come from published research rather
than from this dataset:

- [Optifai Pipeline Study](https://optif.ai/learn/questions/sales-cycle-length-benchmark/)
  (n=939 B2B SaaS companies): cycle length by ACV segment, median 84 days
  overall
- [Prospeo SaaS Sales Cycle Benchmarks](https://prospeo.io/s/b2b-sales-cycle-length):
  ranges by deal size and industry with stage-level breakdowns
- [Gartner B2B Buying Survey](https://www.gartner.com/en/sales/insights/b2b-buying):
  average buying committee of 6.8 stakeholders, up from 5.4 in 2020

Total cycles used: 50 days Mid-Market, 120 Enterprise, 200 Enterprise Suite,
distributed across five stages with later stages weighted more heavily at
larger deal sizes, since legal review and procurement scale with contract
complexity while first meetings don't.

External benchmarks were a deliberate choice. A median calculated from 16
self-designed deals would be both statistically meaningless and circular: the
system would be measured against a number derived from the same data it was
being tested on. The architecture reads benchmarks from a dictionary at
startup, so swapping to company-calculated medians once real volume exists is a
data change rather than a code change.

The pace multiplier is 1.2x. An earlier version used 1.5x, which meant a deal
had to be half again past normal before pace registered at all, too late to be
useful. The lower threshold is safe because pace alone can never reach the top
tier, so a more sensitive trigger costs one extra context fetch rather than a
false alarm in the brief.

**Activity (1 point).** Two indicators:

- Days since the prospect last replied, not since the AE last sent something,
  since outbound volume measures rep effort rather than buyer engagement
- Days since the AE's own last outbound touch, which is a different failure:
  the rep has disengaged too

Both use a 10-day threshold.

**Hygiene (0.5 points).** Two indicators:

- No next step logged after the most recent activity
- Close date already passed without the deal moving or the date being updated

These are the weakest signals individually, but they corroborate stronger ones.

### Axis 2: Prioritization

Deal size relative to the remaining quota gap is applied after detection, never
during it. A $500K deal can be perfectly healthy; portfolio context speaks to
stakes, not risk.

Ranking is ordinal, tier first and size second, rather than a blended score.
Blending would require a number expressing how much more certain one tier is
than another, and no data supports any particular value. The ranking would look
precise while resting on an invention.

That leaves one real gap: a large deal with a single confirmed signal can
matter more than a small one with several. Rather than hide that in a composite
number, those deals get flagged. Any Confirmed-Risk deal worth 25% or more of
the remaining gap appears in the brief regardless of rank, with the reason
stated, so the VP makes the call rather than inheriting it.

---

## Agentic architecture

"Agentic" here means something specific and testable: the path a deal takes
through the pipeline depends on what the system observed, rather than every
deal running the same fixed sequence.

**Step 1, Observe.** Pull open deals from HubSpot. Deal properties from the
standard CRM API, email metadata from the legacy Engagements API, champion
identity from a custom association label.

**Step 2, Score.** Apply the nine indicators using structured data only. No
note text, no email bodies. Produces a score and a tier: Clear (0 to 1.5),
Ambiguous (2 to 4), High-Confidence-Risk (4.5+).

**Step 3, Decide.** The branch point:

- **Clear** deals stop here. No note read, no model call, no cost. They appear
  in the full PDF for completeness and nowhere else.
- **Ambiguous** deals get their note fetched to resolve whether the risk is
  real.
- **High-Confidence** deals get their note fetched too, but for a different
  reason: the verdict is settled, so the note's job is producing the
  explanation a VP will act on.

The branching mechanism is rule-based thresholds, not the model judging its own
confidence. That's testable, auditable, and matches how agentic systems are
actually deployed today. Fully autonomous triage is the stated evolution path,
but it needs eval infrastructure this project doesn't have.

**Step 4, Reason.** Claude reads the note alongside the structural findings and
classifies into one of three cases:

- The note restates something already scored (corroborated, tier unchanged)
- The note contains a concrete fact no timestamp check could surface (new
  signal, may escalate)
- The note gives real evidence against the flag (contradicted, de-escalate)

This prevents escalating a deal simply because the AE's note doesn't argue
against the structural signal. Absence of contradiction is not evidence.

**Step 5, Prioritize.** Rank at-risk deals, apply the 25% flag. This sits
outside the per-deal loop: one synthesis pass over resolved deals, not a
branching decision.

**Step 6, Act.** Post the ranked brief to Slack, attach a PDF covering all 16
deals by tier. The three-layer output mirrors board-pack practice: a summary
that stands alone, a discussion section, and a pre-read appendix.

---

## Threshold design

Weights are flat within each category (behavioral 3, pace 2, activity 1,
hygiene 0.5) rather than differentiated per indicator. An earlier version
weighted champion silence above contact-count drop, which created a cascading
problem: if behavioral needed two tiers, consistency demanded the same across
all four categories, producing a nested system with four sub-arguments to
defend. None of that precision was backed by outcome data.

The corroboration rule is the most consequential threshold decision. No single
category, including behavioral at 3 points, reaches High-Confidence-Risk alone.
Every high-confidence verdict needs a second, independent category behind it. A
single behavioral signal can have an innocent explanation, and flagging a VP's
largest deal as high risk on one data point erodes trust in the brief faster
than a missed signal costs revenue.

---

## Synthetic data design

The dataset was reverse-engineered from target outcomes. Each deal's field
values were set to produce a specific predetermined score, then verified
independently once the scoring code ran.

Sans Pareil Analytics sells in three tiers:

- **Team Analytics** (Mid-Market, $45K to $120K): fewer seats, standard
  connectors, pre-built dashboards
- **Platform** (Enterprise, $150K to $275K): unlimited seats, custom
  integrations, dedicated CSM, governance controls
- **Enterprise Suite** ($300K+): embedded analytics, custom data models,
  on-prem or hybrid deployment

Customers span healthcare, financial services, retail, logistics,
manufacturing, and technology. Deal sizes, committee sizes, and cycle
expectations follow the benchmarks cited above.

Three AEs carry the pipeline:

- **Sarah Chen** (Enterprise, 4 deals)
- **James Rodriguez** (Mid-Market, 7 deals)
- **Marcus Thompson** (Enterprise, 5 deals)

More deals at Mid-Market and fewer at Enterprise mirrors real team structure.

**The A1/H1 matched pair** is the most important design choice in the dataset.
Both share the same behavioral trigger (champion silence), the same stage
(Contract Sent), similar values ($150K and $160K), and the same AE. The only
meaningful difference is that H1 also trips the pace signal, at 48 days in
stage against a 38-day Enterprise benchmark. Under the corroboration rule A1
stays Ambiguous and H1 reaches High-Confidence-Risk, which demonstrates that
the system distinguishes one strong signal from two corroborating ones.

**H2 tests the conditional fetch.** Its structural score is only 2.5, from pace
and a lapsed close date. The reschedule pattern that makes it genuinely risky
exists only in the AE's note, invisible to any timestamp check. If the fetch
step were doing nothing useful, H2 would sit in the Ambiguous pile and the VP
would never hear about a $275K deal on its third reschedule.

**Four noise deals** (N1 to N4) carry semi-random values and no predetermined
tier. They exist so the scoring code runs against cases that weren't tuned to
match its own rules, which a fully reverse-engineered dataset can't provide.

---

## Build narrative

What follows is a set of real obstacles and the decisions they forced,
organized by theme rather than chronology.

### HubSpot's scope gaps

The most persistent friction came from HubSpot's granular scope system, where
what the API requires and what the scope picker exposes don't always match.

Notes and emails were both writable from the start, but reading them back
required scopes (`crm.objects.notes.read`, `crm.objects.emails.read`) that
don't appear in the Service Key picker. Community threads confirm this as a
known, long-standing gap rather than a misconfiguration.

The two resolved differently:

- **Notes** turned out to be readable through the Associations API using only
  the deals and contacts scopes already granted. The dedicated notes-read scope
  wasn't necessary for association-based reads.
- **Emails** were genuinely blocked on the v3 CRM API regardless of how the
  request was structured, including a plain properties-only GET. The fix was
  the legacy Engagements v1 API, which returns the same metadata (timestamp,
  direction, associated contacts) using only the contacts scope.

The first attempted workaround for email was reading metadata from a local file
captured at creation time. It worked, but only because the dataset was
self-created; against real customer emails there would be no such file. That
was the reason to keep looking rather than ship it.

### Directional association type IDs

HubSpot association types come in pairs, one ID per direction. Using the wrong
one returns a 400 that reports the source object as an invalid target, which
reads like a data problem rather than a direction problem.

This came up three times:

- Note-to-deal is 214, not the 213 used for deal-to-note
- The Champion label writes with typeId 1 from the contact side and reads with
  typeId 2 from the deal side
- Email-to-deal is 210, with 209 as its pair

The fix each time was querying the labels endpoint for both directions before
committing to a value. Both champion IDs now live in `config.py` with a comment
explaining why there are two.

### Champion identification

Three approaches, each abandoned for a specific reason.

The first inferred champion status from email volume: whoever the AE
corresponded with most was treated as the champion. Workable, but wrong in a
realistic case where an AE emails a CFO ten times chasing budget approval while
the actual champion is a lighter-touch VP.

The second used HubSpot's native `hs_buying_role` property, which has a
Champion option built in. This looked correct until the data model became
clear: the field sits on the contact record, not the contact-deal relationship.
A procurement lead evaluating two deals would be marked champion on both, or
neither.

The third, and the one shipped, is a custom association label scoped to the
specific contact-deal pair. That matches how buying committees actually work,
where the same person can drive one purchase and merely observe another.
Creating the label is a single API call with the Service Key. A 401 on the
first attempt looked like an authentication wall and briefly suggested OAuth
would be required; it turned out the token simply hadn't been pasted into that
run. The label creation call worked as documented once it had credentials.

### Double-counting the same fact

Champion silence sits in the behavioral category and "no prospect reply on
record" sits in activity, but on a deal where the champion never replied they
describe one event. Both triggering inflated the score by counting a single
fact twice, which manufactured exactly the corroboration the tier rules were
supposed to require from independent signals.

The fix passes a flag from the behavioral scorer to the activity scorer: if
champion silence already fired, the generic no-inbound fallback is suppressed
for that deal. Activity can still trigger on its own when the silence comes
from a non-champion or when the AE has also stopped reaching out.

### Prompt iteration

The first reasoning prompt treated "the note doesn't contradict the structural
signal" as grounds to escalate. On A1, where the AE wrote that the deal "still
feels warm" about a champion who had gone silent, that produced an escalation
from a note containing no new information at all.

The corrected prompt names three cases explicitly and defaults to leaving the
tier alone unless the note contains a concrete fact absent from the structural
signals. The A1/H1 pair was what surfaced the problem: A1 escalating meant the
pair no longer demonstrated anything, since both deals ended up in the same
tier for different reasons.

### Dataset timing artifacts

Two rounds of correction were needed after the scoring code first ran against
the full dataset.

Most conversations had been dated well before the reference date, which meant
deals designed to look healthy were tripping the 10-day inactivity threshold
purely because of when their emails happened to be written. Nine deals needed a
recent outbound touch, then three needed a recent inbound reply for the same
reason on the prospect side.

Both fixes belong in the data rather than the scoring rules. A deal meant to
read as healthy should have a recent conversation; special-casing the scoring
code to ignore old timestamps would have hidden the problem rather than fixed
it. Both patches are folded into `seed_04_create_emails.py` in the published
repository, so the dataset builds correctly in a single pass.

---

## Design compromises

Each is a tradeoff with a named resolution path.

- **Frozen reference date.** Scoring runs against a hardcoded date rather than
  `datetime.now()`. The dataset is a fixed snapshot, so real elapsed time would
  make every deal's duration grow each day the demo sat unrun, eventually
  turning healthy deals into false positives. Against a live CRM the same code
  uses the current date.
- **Seeded benchmarks.** Pace benchmarks come from published research rather
  than company history. The architecture supports both; the difference is which
  dictionary the scoring function reads at startup.
- **Rule-based triage.** The fetch decision is a threshold check rather than
  the model assessing its own confidence. This matches production norms, and
  the autonomous version needs eval infrastructure that doesn't exist yet.
- **Demo-scale dataset.** Sixteen deals exercises every indicator and tests the
  corroboration rule, but doesn't test behavior at the 50 to 200 deals a real
  VP would see. The architecture scales without modification; the constraint is
  data population.
- **Email scope workaround.** Metadata reads through the legacy Engagements API
  because of the documented v3 scope gap. The email-reading function is
  isolated so swapping the underlying call is a single-function change if the
  gap closes.

---

## What I'd build next

- **Live scheduling.** Replace the manual trigger with a scheduled run, via
  GitHub Actions cron or a small cloud function. Deployment configuration, not
  an architecture change.
- **Company-specific benchmarks.** At roughly 50+ closed deals per segment,
  calculate per-stage medians from actual history instead of published
  research.
- **LLM-judged triage.** Let the model decide whether it needs more context.
  This requires eval infrastructure first: deals labeled with known outcomes,
  systematic calibration testing, and drift monitoring.
- **Tone and phrasing detection.** The fifth behavioral indicator, dropped here
  because it can't be demonstrated convincingly on synthetic data. With real
  email history and a validated classification approach it becomes a genuine
  signal.
- **Slack as an input source.** The original design included reading a channel
  where AEs discuss deals informally. It was scoped out because HubSpot's notes
  and email metadata covered every indicator the system needed. In an
  organization where reps talk about deals in Slack, that commentary is a
  distinct signal from what they log in the CRM: what the rep actually believes
  versus what they're willing to record.
