"""
Deal Signal Agent — Step 6a: Generate the pre-read PDF.

Produces the long-form companion to the Slack message: a summary page with the
top-priority deals, then every deal in the pipeline organized by tier.

The cleared deals matter here. A brief that only lists problems asks a VP to
trust that everything unmentioned is fine. Including the full pipeline makes
the agent's reasoning auditable in both directions, which is what turns this
from an alert into something a leadership team can actually run a meeting off.

The structure mirrors how a board pre-read works: a page that stands alone, a
detailed section for anyone who wants it, and no requirement to read the second
part to understand the first.

Requires reportlab: pip install reportlab

Prerequisites: agent_04 and agent_05 have produced final_results.json and
brief_deals.json.
"""

import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from config import PDF_OUTPUT_PATH, QUOTA_GAP

TIER_ORDER = ["High-Confidence-Risk", "Confirmed-Risk", "Ambiguous", "Clear"]

TIER_COLORS = {
    "High-Confidence-Risk": colors.HexColor("#C0392B"),
    "Confirmed-Risk": colors.HexColor("#D68910"),
    "Ambiguous": colors.HexColor("#7F8C8D"),
    "Clear": colors.HexColor("#7D7D7D"),
}

HEADER_BG = colors.HexColor("#2C3E50")
ROW_ALT_BG = colors.HexColor("#F7F7F7")
GRID_COLOR = colors.HexColor("#CCCCCC")


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title_", parent=base["Title"], fontSize=20, spaceAfter=6),
        "subtitle": ParagraphStyle("Subtitle_", parent=base["Normal"], alignment=1, spaceAfter=6),
        "heading": ParagraphStyle("Heading_", parent=base["Heading2"], fontSize=12,
                                  spaceBefore=18, spaceAfter=8),
        "body": ParagraphStyle("Body_", parent=base["BodyText"], fontSize=10, leading=14),
        "summary": ParagraphStyle("Summary_", parent=base["BodyText"], fontSize=10,
                                  leading=15, spaceAfter=10),
    }


def build_summary_page(elements, styles, all_deals, brief):
    elements.append(Paragraph("Deal Signal Agent — Weekly Risk Pre-Read", styles["title"]))
    elements.append(Paragraph("Sans Pareil Analytics | Prepared for VP of Sales", styles["subtitle"]))
    elements.append(Spacer(1, 20))

    at_risk = [d for d in all_deals if d["final_tier"] != "Clear"]
    at_risk_value = sum(d["amount"] for d in at_risk)

    elements.append(Paragraph(
        f"<b>{len(at_risk)} deals</b> need attention this week, representing "
        f"<b>${at_risk_value:,.0f}</b> against a remaining quota gap of "
        f"<b>${QUOTA_GAP:,.0f}</b>. The top {len(brief)} are detailed below; the "
        f"full {len(all_deals)}-deal pipeline follows, organized by risk tier.",
        styles["summary"],
    ))

    elements.append(Paragraph("Top Priority Deals", styles["heading"]))

    for position, deal in enumerate(brief, start=1):
        flag = " (flagged: large stakes despite lower confidence)" if deal.get("flagged") else ""
        elements.append(Paragraph(
            f"<b>{position}. {deal['name']}</b> ({deal['ae']}, ${deal['amount']:,.0f}){flag}",
            styles["body"],
        ))
        elements.append(Paragraph(deal["explanation"], styles["body"]))
        elements.append(Spacer(1, 10))


def build_tier_table(tier_deals, styles):
    rows = [["Deal", "AE", "Amount", "Explanation"]]

    for deal in tier_deals:
        rows.append([
            Paragraph(deal["name"], styles["body"]),
            Paragraph(deal["ae"] or "", styles["body"]),
            f"${deal['amount']:,.0f}",
            Paragraph(deal["explanation"], styles["body"]),
        ])

    table = Table(rows, colWidths=[1.6 * inch, 1.0 * inch, 0.9 * inch, 2.8 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT_BG]),
    ]))
    return table


def build_full_pipeline(elements, styles, all_deals):
    elements.append(Paragraph(f"Full Pipeline — All {len(all_deals)} Deals", styles["title"]))
    elements.append(Spacer(1, 10))

    populated = [t for t in TIER_ORDER if any(d["final_tier"] == t for d in all_deals)]

    for index, tier in enumerate(populated):
        tier_deals = sorted(
            [d for d in all_deals if d["final_tier"] == tier],
            key=lambda d: -d["amount"],
        )

        elements.append(Paragraph(
            f'<font color="{TIER_COLORS[tier].hexval()}">{tier} ({len(tier_deals)})</font>',
            styles["heading"],
        ))
        elements.append(build_tier_table(tier_deals, styles))

        # No trailing spacer after the last table, which would otherwise push an
        # empty page onto the end of the document.
        if index < len(populated) - 1:
            elements.append(Spacer(1, 16))


def main():
    with open("final_results.json") as f:
        all_deals = json.load(f)

    with open("brief_deals.json") as f:
        brief = json.load(f)

    styles = build_styles()
    elements = []

    build_summary_page(elements, styles, all_deals, brief)
    elements.append(PageBreak())
    build_full_pipeline(elements, styles, all_deals)

    doc = SimpleDocTemplate(
        PDF_OUTPUT_PATH,
        pagesize=letter,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(elements)

    print(f"Saved {PDF_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
