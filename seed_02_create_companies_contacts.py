"""
Deal Signal Agent — Seed 2: Create companies and contacts.

Creates one company per deal and the buying committee behind it: 59 contacts
across the 16 deals. Committee size scales with segment (2-3 for Mid-Market,
4-5 for Enterprise, 6-8 for Enterprise Suite), reflecting published research
showing the average B2B buying group has grown to roughly 6.8 stakeholders.

Associations created:
  company -> deal      (Primary)
  contact -> company   (Primary)
  contact -> deal      (default)

The champion for each deal is tracked here but deliberately not written to
HubSpot yet. seed_05 applies it as a custom association label, which is scoped
to the specific contact-deal relationship. HubSpot's native hs_buying_role
property looks like the right home for this but sits on the contact record, so
it would wrongly apply to every deal that contact touches.

Outputs, split along the same operational/answer-key boundary as seed_01:
  company_id_mapping.json
  contact_id_mapping.json   - no champion flags
  contact_answer_key.json   - champion flags, read by seed_05 only

Prerequisite: seed_01 completed.
"""

import json
import time

from config import (
    ASSOC_CONTACT_TO_COMPANY_PRIMARY,
    ASSOC_CONTACT_TO_DEAL,
    ASSOC_DEAL_TO_COMPANY_PRIMARY,
)
from hubspot_client import post, put

# HubSpot's industry field is a fixed enumeration. These values are the exact
# allowed options, which are not always the obvious English word: healthcare is
# HOSPITAL_HEALTH_CARE, logistics is LOGISTICS_AND_SUPPLY_CHAIN, and so on.
COMPANIES = {
    "C1": {"name": "Ridgeline Health Systems", "industry": "HOSPITAL_HEALTH_CARE", "domain": "ridgelinehealth.com", "employees": 4200},
    "C2": {"name": "Foxwood Credit Union", "industry": "FINANCIAL_SERVICES", "domain": "foxwoodcu.com", "employees": 320},
    "C3": {"name": "Atlas Logistics", "industry": "LOGISTICS_AND_SUPPLY_CHAIN", "domain": "atlaslogistics.com", "employees": 850},
    "C4": {"name": "Halcyon Manufacturing", "industry": "MECHANICAL_OR_INDUSTRIAL_ENGINEERING", "domain": "halcyonmfg.com", "employees": 1400},
    "A1": {"name": "Palisade Media Group", "industry": "RETAIL", "domain": "palisademedia.com", "employees": 2100},
    "A2": {"name": "Crestline SaaS", "industry": "COMPUTER_SOFTWARE", "domain": "crestlinesaas.com", "employees": 240},
    "A3": {"name": "Stratos Insurance", "industry": "INSURANCE", "domain": "stratosinsurance.com", "employees": 5600},
    "A4": {"name": "Driftwood Brands", "industry": "RETAIL", "domain": "driftwoodbrands.com", "employees": 180},
    "H1": {"name": "Ironshore Capital", "industry": "FINANCIAL_SERVICES", "domain": "ironshorecap.com", "employees": 3400},
    "H2": {"name": "Keystone Freight", "industry": "LOGISTICS_AND_SUPPLY_CHAIN", "domain": "keystonefreight.com", "employees": 4800},
    "H3": {"name": "Orion Therapeutics", "industry": "PHARMACEUTICALS", "domain": "oriontx.com", "employees": 2900},
    "H4": {"name": "Blackwater Industrial", "industry": "MECHANICAL_OR_INDUSTRIAL_ENGINEERING", "domain": "blackwaterind.com", "employees": 12000},
    "N1": {"name": "Timber Ridge Co-op", "industry": "RETAIL", "domain": "timberridgecoop.com", "employees": 140},
    "N2": {"name": "Vanguard Property Group", "industry": "FINANCIAL_SERVICES", "domain": "vanguardpg.com", "employees": 1800},
    "N3": {"name": "Apex Distribution", "industry": "LOGISTICS_AND_SUPPLY_CHAIN", "domain": "apexdist.com", "employees": 2600},
    "N4": {"name": "Pinehurst Digital", "industry": "COMPUTER_SOFTWARE", "domain": "pinehurstdigital.com", "employees": 190},
}

# champion=True marks the deal's primary advocate. Committees follow a
# realistic shape: an analytics owner who champions the purchase, a finance
# approver, an IT or security reviewer, and at Enterprise Suite size, separate
# compliance and procurement stakeholders.
CONTACTS = {
    "C1": [
        {"first": "Elena", "last": "Vasquez", "title": "VP Clinical Analytics", "champion": True},
        {"first": "Marcus", "last": "Webb", "title": "Director of IT", "champion": False},
        {"first": "Patricia", "last": "Chen", "title": "CFO", "champion": False},
        {"first": "Robert", "last": "Klein", "title": "Data Security Lead", "champion": False},
    ],
    "C2": [
        {"first": "Jennifer", "last": "Ortiz", "title": "Head of Analytics", "champion": True},
        {"first": "David", "last": "Park", "title": "Operations Manager", "champion": False},
    ],
    "C3": [
        {"first": "Michael", "last": "Torres", "title": "Analytics Manager", "champion": True},
        {"first": "Sandra", "last": "Wu", "title": "Operations Director", "champion": False},
        {"first": "Kevin", "last": "Brooks", "title": "IT Manager", "champion": False},
    ],
    "C4": [
        {"first": "Angela", "last": "Ferreira", "title": "Head of Analytics", "champion": True},
        {"first": "Thomas", "last": "Reed", "title": "Plant Operations Manager", "champion": False},
    ],
    "A1": [
        {"first": "Rachel", "last": "Kim", "title": "VP Data & Analytics", "champion": True},
        {"first": "Brian", "last": "Malone", "title": "Director of RevOps", "champion": False},
        {"first": "Susan", "last": "Whitfield", "title": "CFO", "champion": False},
        {"first": "Carlos", "last": "Mendes", "title": "IT Security Lead", "champion": False},
    ],
    "A2": [
        {"first": "Nicole", "last": "Andrews", "title": "Head of Analytics", "champion": True},
        {"first": "James", "last": "Holt", "title": "Operations Manager", "champion": False},
    ],
    "A3": [
        {"first": "Daniel", "last": "Cho", "title": "VP Data & Analytics", "champion": True},
        {"first": "Laura", "last": "Simmons", "title": "Director of RevOps", "champion": False},
        {"first": "Peter", "last": "Nakamura", "title": "CFO", "champion": False},
        {"first": "Grace", "last": "Liu", "title": "IT Security Lead", "champion": False},
        {"first": "Victor", "last": "Okafor", "title": "Head of BI", "champion": False},
    ],
    "A4": [
        {"first": "Melissa", "last": "Grant", "title": "Head of Analytics", "champion": True},
        {"first": "Tyler", "last": "Brooks", "title": "Operations Manager", "champion": False},
        {"first": "Olivia", "last": "Bennett", "title": "IT Manager", "champion": False},
    ],
    "H1": [
        {"first": "Amanda", "last": "Ross", "title": "VP Data & Analytics", "champion": True},
        {"first": "Gregory", "last": "Payne", "title": "Director of RevOps", "champion": False},
        {"first": "Christine", "last": "Ndiaye", "title": "CFO", "champion": False},
        {"first": "Marcus", "last": "Feldman", "title": "IT Security Lead", "champion": False},
    ],
    "H2": [
        {"first": "Steven", "last": "Kowalski", "title": "VP Data & Analytics", "champion": True},
        {"first": "Diane", "last": "Torres", "title": "Director of RevOps", "champion": False},
        {"first": "Frank", "last": "Delgado", "title": "CFO", "champion": False},
        {"first": "Priya", "last": "Sharma", "title": "IT Security Lead", "champion": False},
        {"first": "Wendy", "last": "Adeyemi", "title": "Head of BI", "champion": False},
    ],
    "H3": [
        {"first": "Sarah", "last": "Lindqvist", "title": "VP Data & Analytics", "champion": True},
        {"first": "Michael", "last": "Osei", "title": "Director of Clinical Ops", "champion": False},
        {"first": "Linda", "last": "Park", "title": "CFO", "champion": False},
        {"first": "Robert", "last": "Nguyen", "title": "IT Security Lead", "champion": False},
    ],
    "H4": [
        {"first": "Katherine", "last": "Reyes", "title": "Chief Data Officer", "champion": True},
        {"first": "Andrew", "last": "Kessler", "title": "VP Data & Analytics", "champion": False},
        {"first": "Monica", "last": "Alves", "title": "Director of RevOps", "champion": False},
        {"first": "Richard", "last": "Blackwood", "title": "CFO", "champion": False},
        {"first": "Sophie", "last": "Tanaka", "title": "VP Engineering", "champion": False},
        {"first": "Marcus", "last": "Delgado", "title": "Head of Compliance", "champion": False},
        {"first": "Elena", "last": "Popov", "title": "Head of Procurement", "champion": False},
    ],
    "N1": [
        {"first": "Brandon", "last": "Lee", "title": "Head of Analytics", "champion": True},
        {"first": "Karen", "last": "Diaz", "title": "Operations Manager", "champion": False},
    ],
    "N2": [
        {"first": "Jonathan", "last": "Meyer", "title": "VP Data & Analytics", "champion": True},
        {"first": "Rebecca", "last": "Sung", "title": "Director of RevOps", "champion": False},
        {"first": "Alan", "last": "Whitfield", "title": "CFO", "champion": False},
        {"first": "Nadia", "last": "Hassan", "title": "IT Security Lead", "champion": False},
    ],
    "N3": [
        {"first": "Derek", "last": "Foster", "title": "VP Data & Analytics", "champion": True},
        {"first": "Michelle", "last": "Obi", "title": "Director of RevOps", "champion": False},
        {"first": "Gary", "last": "Lindholm", "title": "CFO", "champion": False},
        {"first": "Tanya", "last": "Reyes", "title": "IT Security Lead", "champion": False},
        {"first": "Samuel", "last": "Osborne", "title": "Head of BI", "champion": False},
    ],
    "N4": [
        {"first": "Ashley", "last": "Rourke", "title": "Head of Analytics", "champion": True},
        {"first": "Connor", "last": "Blake", "title": "Operations Manager", "champion": False},
        {"first": "Priya", "last": "Nair", "title": "IT Manager", "champion": False},
    ],
}


def make_email(first, last, domain):
    return f"{first.lower()}.{last.lower()}@{domain}"


def create_companies(deal_lookup):
    print("Creating companies...")
    company_ids = {}

    for local_id, company in COMPANIES.items():
        if local_id not in deal_lookup:
            continue

        result = post("/crm/v3/objects/companies", {
            "properties": {
                "name": company["name"],
                "domain": company["domain"],
                "industry": company["industry"],
                "numberofemployees": str(company["employees"]),
            }
        })

        if result:
            company_ids[local_id] = result["id"]
            print(f"  [{local_id}] {company['name']}")
        else:
            print(f"  [{local_id}] FAILED — check crm.objects.companies.write scope")

        time.sleep(0.1)

    return company_ids


def link_companies_to_deals(company_ids, deal_lookup):
    print("\nLinking companies to deals...")

    for local_id, company_id in company_ids.items():
        result = put(
            f"/crm/v4/objects/deals/{deal_lookup[local_id]}/associations/companies/{company_id}",
            [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOC_DEAL_TO_COMPANY_PRIMARY}],
        )
        print(f"  [{local_id}] {'linked' if result is not None else 'FAILED'}")
        time.sleep(0.1)


def create_contacts(company_ids, deal_lookup):
    print("\nCreating contacts...")
    records = []

    for local_id, contact_list in CONTACTS.items():
        if local_id not in deal_lookup:
            continue

        deal_id = deal_lookup[local_id]
        company_id = company_ids.get(local_id)
        company = COMPANIES[local_id]

        print(f"\n  [{local_id}] {company['name']} — {len(contact_list)} contacts")

        for contact in contact_list:
            email = make_email(contact["first"], contact["last"], company["domain"])

            associations = [{
                "to": {"id": deal_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOC_CONTACT_TO_DEAL}],
            }]

            if company_id:
                associations.append({
                    "to": {"id": company_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOC_CONTACT_TO_COMPANY_PRIMARY}],
                })

            result = post("/crm/v3/objects/contacts", {
                "properties": {
                    "firstname": contact["first"],
                    "lastname": contact["last"],
                    "email": email,
                    "jobtitle": contact["title"],
                    "company": company["name"],
                },
                "associations": associations,
            })

            marker = "*" if contact["champion"] else " "
            if result:
                print(f"     {marker} {contact['first']} {contact['last']} — {contact['title']}")
                records.append({
                    "local_deal_id": local_id,
                    "hubspot_contact_id": result["id"],
                    "hubspot_deal_id": deal_id,
                    "hubspot_company_id": company_id,
                    "first_name": contact["first"],
                    "last_name": contact["last"],
                    "email": email,
                    "title": contact["title"],
                    "is_intended_champion": contact["champion"],
                })
            else:
                print(f"     {marker} {contact['first']} {contact['last']} — FAILED")

            time.sleep(0.1)

    return records


def main():
    with open("deal_id_mapping.json") as f:
        deal_lookup = {d["local_id"]: d["hubspot_id"] for d in json.load(f)}

    print(f"Loaded {len(deal_lookup)} deals.\n")

    company_ids = create_companies(deal_lookup)
    link_companies_to_deals(company_ids, deal_lookup)
    contacts = create_contacts(company_ids, deal_lookup)

    with open("company_id_mapping.json", "w") as f:
        json.dump([
            {"local_id": lid, "hubspot_id": cid, "name": COMPANIES[lid]["name"]}
            for lid, cid in company_ids.items()
        ], f, indent=2)

    # Operational file: champion flag stripped out.
    with open("contact_id_mapping.json", "w") as f:
        json.dump([
            {k: v for k, v in c.items() if k != "is_intended_champion"}
            for c in contacts
        ], f, indent=2)

    # Answer key: seed_05 reads this to know which contact to label.
    with open("contact_answer_key.json", "w") as f:
        json.dump([
            {
                "local_deal_id": c["local_deal_id"],
                "hubspot_contact_id": c["hubspot_contact_id"],
                "email": c["email"],
                "is_intended_champion": c["is_intended_champion"],
            }
            for c in contacts
        ], f, indent=2)

    expected = sum(len(v) for v in CONTACTS.values())
    print(f"\nCompanies: {len(company_ids)}/{len(COMPANIES)}")
    print(f"Contacts:  {len(contacts)}/{expected}")


if __name__ == "__main__":
    main()
