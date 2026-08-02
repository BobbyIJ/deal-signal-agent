"""
Deal Signal Agent — Minimal HubSpot HTTP client.

Thin wrappers over urllib so the seed and agent scripts don't each repeat the
same request-building and error-handling boilerplate. Deliberately dependency
free: the whole project runs on the standard library plus reportlab.
"""

import json
import urllib.error
import urllib.request

from config import HUBSPOT_TOKEN, require

BASE = "https://api.hubapi.com"


def _request(method, url, payload=None):
    token = require("HUBSPOT_TOKEN", HUBSPOT_TOKEN)

    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.read().decode()}")
        return None


def get(path):
    return _request("GET", f"{BASE}{path}")


def post(path, payload):
    return _request("POST", f"{BASE}{path}", payload)


def patch(path, payload):
    return _request("PATCH", f"{BASE}{path}", payload)


def put(path, payload):
    return _request("PUT", f"{BASE}{path}", payload)
