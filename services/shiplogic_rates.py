import os
import datetime as _dt
import requests

SHIPLOGIC_RATES_URL = os.getenv("SHIPLOGIC_RATES_URL", "https://api.shiplogic.com/rates").strip()

def normalize_zone(province_or_code: str) -> str:
    """
    Converts GP/WC/etc or 'Gauteng (GP)' into Shiplogic zone names.
    """
    if not province_or_code:
        return "Gauteng"

    s = province_or_code.strip()

    # "Gauteng (GP)" -> "Gauteng"
    if " (" in s:
        s = s.split(" (")[0].strip()

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

    return code_map.get(s, s)

def _today() -> str:
    return _dt.date.today().strftime("%Y-%m-%d")

def _collection_address_from_env() -> dict:
    """
    Your store/warehouse address (collection point).
    Set these on Render.
    """
    return {
        "type": os.getenv("SL_FROM_TYPE", "business"),
        "company": os.getenv("SL_FROM_COMPANY", "First Pour"),
        "street_address": os.getenv("SL_FROM_STREET", "").strip(),
        "local_area": os.getenv("SL_FROM_LOCAL_AREA", "").strip(),
        "city": os.getenv("SL_FROM_CITY", "").strip(),
        "zone": os.getenv("SL_FROM_ZONE", "Gauteng").strip(),  # must be province name
        "country": os.getenv("SL_FROM_COUNTRY", "ZA").strip(),
        "code": os.getenv("SL_FROM_CODE", "").strip(),
    }

def _parcels_default(total_qty: int) -> list:
    """
    Safe default packaging assumptions (you can refine later).
    """
    if total_qty <= 0:
        total_qty = 1

    # estimate 1.5kg per bottle
    weight = max(1.0, total_qty * 1.5)

    return [{
        "submitted_length_cm": float(os.getenv("SL_PARCEL_LEN_CM", "35")),
        "submitted_width_cm": float(os.getenv("SL_PARCEL_W_CM", "25")),
        "submitted_height_cm": float(os.getenv("SL_PARCEL_H_CM", "15")),
        "submitted_weight_kg": float(weight),
    }]

def get_rates(delivery_address: dict, declared_value: int = 1500) -> dict:
    """
    Calls Shiplogic:
      POST https://api.shiplogic.com/rates
      Authorization: Bearer <token>

    Env:
      SHIPLOGIC_API_KEY  (or TCG_API_KEY if that’s what you used)
    """
    api_key = (os.getenv("SHIPLOGIC_API_KEY") or os.getenv("TCG_API_KEY") or "").strip()
    if not api_key:
        raise Exception("Missing Shiplogic API key. Set SHIPLOGIC_API_KEY on Render (or TCG_API_KEY).")

    collection_address = _collection_address_from_env()

    # Validate collection address (prevents 404/no routes)
    required = ["street_address", "city", "zone", "code"]
    for k in required:
        if not collection_address.get(k):
            raise Exception(f"Store (collection) address missing '{k}'. Set SL_FROM_* env vars on Render.")

    # Count total qty from cart lines if present in delivery_address metadata
    total_qty = int(delivery_address.pop("_total_qty", 1))

    payload = {
        "collection_address": collection_address,
        "delivery_address": delivery_address,
        "parcels": _parcels_default(total_qty),
        "declared_value": int(declared_value),
        "collection_min_date": _today(),
        "delivery_min_date": _today(),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    r = requests.post(SHIPLOGIC_RATES_URL, json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        raise Exception(f"Shiplogic rates failed ({r.status_code}): {r.text}")

    return r.json()
