import os
import datetime
import requests
from flask import Blueprint, request, session, redirect, url_for

courier_bp = Blueprint("courier_bp", __name__)

CG_API_KEY = os.getenv("COURIERGUY_API_KEY", "").strip()

# PUDO / Courier Guy rates endpoint
CG_RATES_URL = "https://api-pudo.co.za/rates"

def _from_address():
    # collection_address required fields (per API docs)
    return {
        "type": os.getenv("CG_FROM_TYPE", "business"),
        "company": os.getenv("CG_FROM_COMPANY", "First Pour"),
        "street_address": os.getenv("CG_FROM_STREET", ""),
        "local_area": os.getenv("CG_FROM_LOCAL_AREA", ""),
        "city": os.getenv("CG_FROM_CITY", ""),
        "zone": os.getenv("CG_FROM_ZONE", "Gauteng"),
        "country": os.getenv("CG_FROM_COUNTRY", "ZA"),
        "code": os.getenv("CG_FROM_CODE", ""),
    }

def _parcels_from_cart(lines):
    """
    Simple default parcel sizing.
    You can refine later per bottle count.
    API requires parcels with submitted dimensions + weight.
    """
    total_qty = sum(int(l.get("qty", 0)) for l in lines) or 1
    # rough weight: 1.5kg per bottle (safe estimate)
    weight = max(1.0, total_qty * 1.5)

    return [{
        "submitted_length_cm": 35.0,
        "submitted_width_cm": 25.0,
        "submitted_height_cm": 15.0,
        "submitted_weight_kg": float(weight),
    }]

def get_rates(delivery_address, lines, declared_value=1500):
    if not CG_API_KEY:
        raise RuntimeError("Courier Guy not connected (COURIERGUY_API_KEY missing).")

    payload = {
        "collection_address": _from_address(),
        "delivery_address": delivery_address,
        "parcels": _parcels_from_cart(lines),
        "declared_value": declared_value,
        "collection_min_date": datetime.date.today().isoformat(),
        "delivery_min_date": datetime.date.today().isoformat(),
    }

    # API uses api_key (docs show api_key usage on endpoints; we pass as query param)
    r = requests.post(CG_RATES_URL, params={"api_key": CG_API_KEY}, json=payload, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"Courier quote failed ({r.status_code}): {r.text}")

    return r.json()

@courier_bp.route("/courier/quote", methods=["POST"])
def courier_quote():
    # We expect your main app to store checkout details in session:
    # session["delivery_*"] fields + session["cart_lines_cache"] for quoting
    # If your app uses different names, tell me and I will align it.

    # delivery address required structure
    delivery_address = {
        "type": "residential",
        "company": "",
        "street_address": (session.get("cg_street") or "").strip(),
        "local_area": (session.get("cg_suburb") or "").strip(),
        "city": (session.get("cg_city") or "").strip(),
        "zone": (session.get("cg_province") or "Gauteng").strip(),
        "country": "ZA",
        "code": (session.get("cg_postal") or "").strip(),
    }

    lines = session.get("cart_lines_cache", [])
    if not lines:
        session["cg_error"] = "Cart is empty — add items first."
        return redirect(url_for("checkout"))

    try:
        data = get_rates(delivery_address, lines)
    except Exception as e:
        session["cg_error"] = str(e)
        return redirect(url_for("checkout"))

    # Pick the cheapest rate (you can change this to fastest, etc.)
    # We don't know exact response shape for every account, so we handle common structures safely.
    rates = []
    if isinstance(data, dict):
        if "rates" in data and isinstance(data["rates"], list):
            rates = data["rates"]
        elif "data" in data and isinstance(data["data"], list):
            rates = data["data"]

    if not rates:
        session["cg_error"] = f"No rates returned: {data}"
        return redirect(url_for("checkout"))

    def _price(r):
        # try common fields
        for key in ["total", "price", "amount", "rate"]:
            if key in r and isinstance(r[key], (int, float)):
                return float(r[key])
        return 1e18

    best = sorted(rates, key=_price)[0]
    session["cg_quote_raw"] = best
    session["cg_error"] = ""
    return redirect(url_for("checkout"))
