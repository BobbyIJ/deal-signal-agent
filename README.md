# Deal Signal Agent

An agentic risk-detection system for B2B sales pipelines. It reads an entire
pipeline from HubSpot, decides on its own which deals warrant a closer look,
has Claude read the CRM notes on those deals, and delivers a ranked, explained
brief to Slack with a full pre-read PDF attached.

Built as portfolio work: not a production deployment, but a working system that
hits real APIs, makes real conditional decisions, and produces a real
deliverable.

[Architecture](docs/architecture-diagram.png) 

## The problem

Weekly pipeline reviews look backwards. Reps carry 30 to 50 live deals and
can't watch all of them equally, they have a rational incentive to keep wobbly
deals looking healthy for as long as possible, and the earliest warning signs
(a reply that took a week instead of a day, a champion who stopped answering)
show up in email and notes well before they show up in a CRM field. Nobody is
positioned to aggregate that across a team in time, so a VP of Sales finds out
a deal is dying in the same meeting where it's too late to act.

## What it does

1. **Observe** — pull every open deal from HubSpot.
2. **Score** — rate each deal on four rule-based categories (behavioral
  signals, pace against a segment benchmark, activity recency, CRM hygiene)
   and assign a tier: Clear, Ambiguous, or High-Confidence-Risk.
3. **Decide** — the agentic branch. Clear deals stop here, with no model call
  and no cost. Ambiguous deals get their note read to resolve the question.
   High-Confidence deals get their note read to sharpen the explanation.
4. **Reason** — Claude reads the note and either confirms the tier, escalates
  it on a genuinely new fact, or overturns it on real contrary evidence.
5. **Prioritize** — rank by tier, then deal size, flagging any lower-confidence
  deal large enough to matter anyway.
6. **Deliver** — post the ranked brief to Slack, attach the full pre-read.

Step 3 is what makes this an agent rather than a pipeline with a model call in
it. The path a deal takes depends on what the system found, so a healthy deal
and a stalling one are handled differently rather than being pushed through the
same fixed sequence.

## Sample output

From a run against the 16-deal synthetic pipeline:

> **Deal Signal Agent — Weekly Risk Brief**
> 7 deals need attention this week, representing $1,380,000 against a remaining
> quota gap of $600,000.
>
> **1. Blackwater Industrial — Enterprise Suite** (Marcus Thompson, $450,000)
> AE confirms a multi-threaded stall: Katherine, compliance, and procurement
> have all gone silent, with legal review stuck well past normal duration. The
> AE is already escalating internally and considering VP-level engagement.
>
> **4. Palisade Media Group — Platform** (Sarah Chen, $150,000) *(flagged:
> large stakes despite lower confidence)*
> The note restates the same champion silence already captured structurally.
> The AE's optimism is subjective sentiment rather than a concrete new fact, so
> the tier stays where it is.

Palisade ranks fifth on signal strength but appears in the brief anyway,
because at 25% of the quota gap it's too large to drop for finishing fourth.

## Repository structure

**Setup** — run once against a fresh sandbox


| File                                 | Purpose                                                                    |
| ------------------------------------ | -------------------------------------------------------------------------- |
| `setup_01_create_custom_property.py` | Creates the writable `stage_entered_date` field the pace signal depends on |
| `setup_02_lookup_owner_ids.py`       | Prints owner IDs for `config.py`                                           |


**Seed** — build the synthetic dataset, run in order


| File                                   | Purpose                                               |
| -------------------------------------- | ----------------------------------------------------- |
| `seed_01_create_deals.py`              | 16 deals, each reverse-engineered from a target score |
| `seed_02_create_companies_contacts.py` | 16 companies, 59 contacts                             |
| `seed_03_create_notes.py`              | AE notes and next-step fields                         |
| `seed_04_create_emails.py`             | 58 emails carrying the behavioral signal              |
| `seed_05_apply_champion_labels.py`     | Custom association label marking each deal's champion |


**Agent** — the pipeline itself


| File                       | Purpose                                            |
| -------------------------- | -------------------------------------------------- |
| `agent_01_fetch.py`        | Observe                                            |
| `agent_02_scoring.py`      | Structural scoring and tier assignment             |
| `agent_03_reason.py`       | Conditional fetch and Claude reasoning             |
| `agent_04_finalize.py`     | Reconcile structural tier with the model's verdict |
| `agent_05_prioritize.py`   | Rank and flag                                      |
| `agent_06_generate_pdf.py` | Pre-read PDF                                       |
| `agent_07_deliver.py`      | Slack delivery                                     |
| `agent_run.py`             | Runs all of the above in one pass, in memory       |


**Shared** — `config.py` (credentials, thresholds, association IDs),
`hubspot_client.py` (HTTP wrapper)

Each `agent_0*.py` script writes its output to a JSON file so the scoring rules
can be tested without re-hitting the API or paying for model calls on every
iteration. `agent_run.py` does the same work in memory and never touches those
files: that's the production-shaped path.

## Prerequisites

- Python 3.10+
- A HubSpot developer sandbox with a Service Key. Scopes needed:
`crm.objects.deals`, `crm.objects.contacts`, `crm.objects.companies`,
`crm.objects.owners.read`, `crm.schemas.deals.write`
- An Anthropic API key
- A Slack workspace with a bot app (`chat:write`, `files:write`) invited to
your target channel
- Three users created in HubSpot to act as account executives



## Running it

```bash
pip install -r requirements.txt

export HUBSPOT_TOKEN="your-service-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
export SLACK_BOT_TOKEN="xoxb-your-token"
export SLACK_CHANNEL_ID="C0XXXXXXXXX"

# One-time setup
python setup_01_create_custom_property.py
python setup_02_lookup_owner_ids.py   # paste the IDs into config.py

# Build the dataset
python seed_01_create_deals.py
python seed_02_create_companies_contacts.py
python seed_03_create_notes.py
python seed_04_create_emails.py
python seed_05_apply_champion_labels.py

# Run the agent
python agent_run.py --dry-run   # everything except posting
python agent_run.py             # full run
```



## Design decisions worth explaining

Full reasoning in the [case study.](docs/case-study.md)

**The corroboration rule.** No single category, however strong, can reach the
top tier alone. Champion silence has innocent explanations, and flagging a VP's
largest deal as high risk on one data point costs more in lost trust than a
missed signal costs in revenue.

**Champion identity as an association label.** HubSpot's native
`hs_buying_role` field looks right until you notice it lives on the contact
record, so a procurement lead evaluating two deals would be marked champion on
both. Association labels attach to the specific contact-deal pair, matching how
buying committees actually work.

**Ordinal ranking rather than a blended score.** Weighting deal value by tier
confidence would require a number expressing how much more certain one tier is
than another. No data supports such a number, so the ranking would look precise
while resting on an invention. Large lower-confidence deals get flagged
explicitly instead.

**Rule-based triage.** The decision to fetch is a threshold check, not the
model judging its own confidence. That matches how agentic systems are actually
deployed today, and the more autonomous version needs eval infrastructure that
doesn't exist here yet.

## What isn't production-ready

- Runs on demand rather than on a schedule. A deployment change, not an
architectural one.
- Pace benchmarks come from published research rather than company history. The
dataset is too small to compute meaningful medians, and the architecture
supports either source.
- Email metadata reads through the legacy Engagements API, because the current
endpoint requires a scope HubSpot doesn't expose in the Service Key picker.
- The scoring reference date is frozen, since the dataset is a fixed snapshot
rather than a live CRM.



## License

MIT. Shared for portfolio and demonstration purposes.