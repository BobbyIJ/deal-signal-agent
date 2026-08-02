"""
Deal Signal Agent — Shared configuration.

Credentials are read from environment variables so nothing sensitive is
committed to the repository. Set these before running any script:

    export HUBSPOT_TOKEN="your-hubspot-service-key"
    export ANTHROPIC_API_KEY="your-anthropic-key"
    export SLACK_BOT_TOKEN="xoxb-your-slack-bot-token"
    export SLACK_CHANNEL_ID="C0XXXXXXXXX"

On Windows PowerShell:

    $env:HUBSPOT_TOKEN="your-hubspot-service-key"
"""

import os
from datetime import datetime

# =============================================================================
# CREDENTIALS
# =============================================================================

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "")


def require(name, value):
    """Fail early with a clear message rather than a confusing 401 later."""
    if not value:
        raise SystemExit(
            f"Missing {name}. Set it as an environment variable before running.\n"
            f"See the docstring in config.py for the exact command."
        )
    return value


# =============================================================================
# HUBSPOT OWNER IDS
#
# These are specific to a single HubSpot portal. Run
# setup_02_lookup_owner_ids.py against your own sandbox and replace these
# with the IDs it prints.
# =============================================================================

OWNERS = {
    "Sarah Chen": "267416405",
    "James Rodriguez": "267416476",
    "Marcus Thompson": "267416491",
}

# =============================================================================
# HUBSPOT ASSOCIATION TYPE IDS
#
# HubSpot association types are directional: the ID for contact-to-deal is
# different from the ID for deal-to-contact. Using the wrong direction returns
# a 400 that misleadingly reports the source object as an invalid target, so
# each of these was confirmed against the /crm/v4/associations/{from}/{to}/labels
# endpoint before use.
# =============================================================================

ASSOC_CONTACT_TO_DEAL = 4
ASSOC_DEAL_TO_CONTACT = 3
ASSOC_DEAL_TO_COMPANY_PRIMARY = 5
ASSOC_CONTACT_TO_COMPANY_PRIMARY = 1
ASSOC_NOTE_TO_DEAL = 214
ASSOC_EMAIL_TO_DEAL = 210
ASSOC_EMAIL_TO_CONTACT = 198

# Custom "Champion" label, created by seed_05_apply_champion_labels.py.
# Also directional: 1 when writing from the contact side, 2 when reading from
# the deal side.
CHAMPION_LABEL_CONTACT_TO_DEAL = 1
CHAMPION_LABEL_DEAL_TO_CONTACT = 2

# =============================================================================
# SCENARIO CONSTANTS
# =============================================================================

# The dataset is a fixed snapshot rather than a live CRM, so the agent scores
# against a frozen date. Against a real pipeline this would be datetime.now().
REFERENCE_DATE = datetime(2026, 7, 19, 12, 0, 0)

# Sans Pareil Analytics quarterly scenario: $1.5M quota, $900K closed.
QUOTA_GAP = 600_000

PDF_OUTPUT_PATH = "deal_signal_agent_prereview.pdf"
