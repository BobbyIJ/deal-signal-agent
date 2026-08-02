"""
Deal Signal Agent — Setup 2: Look up HubSpot owner IDs.

The seed scripts assign each deal to one of three account executives. HubSpot
identifies owners by numeric ID rather than name, and those IDs are unique to
each portal, so the values in config.py will not match your sandbox.

Owners cannot be created through the API. Add three users through the HubSpot
UI first (Settings, then Users & Teams), then run this to get their IDs and
paste them into the OWNERS dict in config.py.

Tip: Gmail-style plus addressing (you+sarah@gmail.com) lets you create several
users against one inbox. Accept the invites in a private browser window so you
don't get signed out of your main account.
"""

from hubspot_client import get


def main():
    result = get("/crm/v3/owners")

    if not result:
        print("Lookup failed. Check that the Service Key has crm.objects.owners.read.")
        return

    owners = result.get("results", [])
    print(f"Found {len(owners)} owner(s):\n")

    for owner in owners:
        name = f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip()
        print(f'    "{name}": "{owner["id"]}",')

    print("\nCopy the lines above into the OWNERS dict in config.py.")


if __name__ == "__main__":
    main()
