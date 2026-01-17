import os
import datetime as _dt
import requests


def normalize_zone(province: str) -> str:
    """
    Shiplogic zones are typically province names (e.g. Gauteng, Western Cape).
    Your UI uses 'Gauteng (GP)' etc.
    This converts 'Gauteng (GP)' -> 'Gauteng'
    """
    if not province:
        return "Gauteng"
    province = province.strip()
    if " (" in province:
        province = province.split(" (")[0].strip()
    # Accept short codes too
    code_map = {
        "GP": "Gauteng",
        "WC": "Western Cape",
        "KZN": "KwaZulu-Natal",
        "EC": "Eastern Cape",
        "FS": "Free State",
        "LP": "Limpopo",
        "MP": "Mpumalanga",
        "NW": "North West",
        "NC": "Northern Cape",
    }
    if province in code_map:
        return code_map[province]
    return province


def _today_yyyy_mm_dd() -> str:
    return _dt.date.today().strftime("%Y-%m-%d")


def get_rates(payload: dict) -> dict:
    """
    Shiplogic rates endpoint:
      POST https://api.shiplogic.com/rates
    Auth:
      Authorization: Bearer <token>

    Env var expected:
      SHIPLOGIC_API_KEY  (or TCG_API_KEY if you stored it that way)

    Returns JSON response dict.
    Raises Exception on non-200/201 responses with server message.
    """
    api_key = os.getenv("SHIPLOGIC_API_KEY") or os.getenv("TCG_API_KEY") or ""
    if not api_key:
        raise Exception("Missing Shiplogic API key. Set SHIPLOGIC_API_KEY (or TCG_API_KEY) on Render.")

    url = os.getenv("SHIPLOGIC_RATES_URL", "https://api.shiplogic.com/rates")

    # Ensure dates exist (Shiplogic requires min dates in many accounts)
    payload = dict(payload)
    payload.setdefault("collection_min_date", _today_yyyy_mm_dd())
    payload.setdefault("delivery_min_date", _today_yyyy_mm_dd())

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    r = requests.post(url, json=payload, headers=headers, timeout=30)

    # Shiplogic commonly returns 200, but handle 201 as well.
    if r.status_code not in (200, 201):
        # Provide useful error text
        raise Exception(f"Shiplogic rates failed ({r.status_code}): {r.text}")

    return r.json()
