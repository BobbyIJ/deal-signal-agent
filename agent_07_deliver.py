"""
Deal Signal Agent — Step 6b: Deliver to Slack.

Posts the ranked brief as a message and attaches the full pre-read PDF.

The message carries the deals a VP should act on this week. The PDF carries
everything, including what was cleared. Splitting them this way means the
channel stays readable while the full reasoning stays one click away.

File upload uses Slack's three-step external flow, which replaced files.upload
when that endpoint was retired in March 2025:
  1. ask for an upload URL
  2. PUT the bytes to it
  3. tell Slack to share the finished file into the channel

Requires a bot token with chat:write and files:write, and the bot invited to
the target channel. Slack returns not_in_channel rather than a permission
error if the invite is missing, which is easy to misread as a scope problem.

Prerequisites: agent_05 and agent_06 have produced brief_deals.json,
final_results.json, and the PDF.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from config import (
    PDF_OUTPUT_PATH, QUOTA_GAP, SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, require,
)


def slack_call(endpoint, payload=None, form=None):
    token = require("SLACK_BOT_TOKEN", SLACK_BOT_TOKEN)

    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        content_type = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        content_type = "application/json; charset=utf-8"

    req = urllib.request.Request(
        f"https://slack.com/api/{endpoint}",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode()}")
        return {"ok": False}


def build_message():
    with open("final_results.json") as f:
        all_deals = json.load(f)

    with open("brief_deals.json") as f:
        brief = json.load(f)

    at_risk = [d for d in all_deals if d["final_tier"] != "Clear"]
    at_risk_value = sum(d["amount"] for d in at_risk)

    lines = [
        "*Deal Signal Agent — Weekly Risk Brief*",
        f"{len(at_risk)} deals need attention this week, representing "
        f"${at_risk_value:,.0f} against a remaining quota gap of ${QUOTA_GAP:,.0f}.",
        "",
    ]

    for position, deal in enumerate(brief, start=1):
        flag = " _(flagged: large stakes despite lower confidence)_" if deal.get("flagged") else ""
        lines.append(f"*{position}. {deal['name']}* ({deal['ae']}, ${deal['amount']:,.0f}){flag}")
        lines.append(deal["explanation"])
        lines.append("")

    return "\n".join(lines)


def upload_pdf():
    if not os.path.exists(PDF_OUTPUT_PATH):
        print(f"    {PDF_OUTPUT_PATH} not found. Run agent_06_generate_pdf.py first.")
        return False

    filename = os.path.basename(PDF_OUTPUT_PATH)
    filesize = os.path.getsize(PDF_OUTPUT_PATH)

    reserved = slack_call(
        "files.getUploadURLExternal",
        form={"filename": filename, "length": filesize},
    )
    if not reserved.get("ok"):
        print(f"    Could not reserve an upload URL: {reserved}")
        return False

    with open(PDF_OUTPUT_PATH, "rb") as f:
        file_bytes = f.read()

    upload_req = urllib.request.Request(
        reserved["upload_url"],
        data=file_bytes,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(upload_req) as response:
            if response.status != 200:
                print(f"    Upload returned HTTP {response.status}")
                return False
    except urllib.error.HTTPError as e:
        print(f"    Upload failed: HTTP {e.code}")
        return False

    shared = slack_call("files.completeUploadExternal", payload={
        "files": [{"id": reserved["file_id"], "title": "Deal Signal Agent — Pre-Read"}],
        "channel_id": require("SLACK_CHANNEL_ID", SLACK_CHANNEL_ID),
        "initial_comment": "Full pipeline pre-read attached.",
    })

    if not shared.get("ok"):
        print(f"    Could not share the file: {shared}")
        return False

    return True


def main():
    channel = require("SLACK_CHANNEL_ID", SLACK_CHANNEL_ID)

    print("Posting the brief...")
    result = slack_call("chat.postMessage", payload={
        "channel": channel,
        "text": build_message(),
    })

    if not result.get("ok"):
        print(f"    Failed: {result}")
        if result.get("error") == "not_in_channel":
            print("    Invite the bot to the channel: /invite @YourBotName")
        return

    print("    Posted")

    print("Uploading the pre-read...")
    print("    Uploaded" if upload_pdf() else "    Upload failed")


if __name__ == "__main__":
    main()
