import os
import datetime
import requests

CG_API_KEY = os.getenv("COURIERGUY_API_KEY", "").strip()
CG_RATES_URL = os.getenv("COURIERGUY_RATES_URL", "https://api-pudo.co.za/rates").strip()

def _from_address():
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

def parcels_from_cart_lines(lines):
    total_qty = 0
    for l in lines:
        try:
            total_qty += int(l.get("qty", 0))
        except:
            pass
    if total_qty <= 0:
        total_qty = 1

    # Very safe estimate: 1.5kg per bottle
    weight = max(1.0, total_qty * 1.5)

    return [{
        "submitted_length_cm": 35.0,
        "submitted_width_cm": 25.0,
        "submitted_height_cm": 15.0,
        "submitted_weight_kg": float(weight),
    }]

def get_best_rate(delivery_address: dict, lines: list, declared_value: int = 1500):
    if not CG_API_KEY:
        raise RuntimeError("Courier Guy not connected (COURIERGUY_API_KEY missing).")

    payload = {
        "collection_address": _from_address(),
        "delivery_address": delivery_address,
        "parcels": parcels_from_cart_lines(lines),
        "declared_value": declared_value,
        "collection_min_date": datetime.date.today().isoformat(),
        "delivery_min_date": datetime.date.today().isoformat(),
    }

    r = requests.post(CG_RATES_URL, params={"api_key": CG_API_KEY}, json=payload, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"Courier quote failed ({r.status_code}): {r.text}")

    data = r.json()

    rates = []
    if isinstance(data, dict):
        if isinstance(data.get("rates"), list):
            rates = data["rates"]
        elif isinstance(data.get("data"), list):
            rates = data["data"]
        elif isinstance(data.get("results"), list):
            rates = data["results"]

    if not rates:
        raise RuntimeError(f"No rates returned: {data}")

    def price_of(rate):
        for k in ["total", "price", "amount", "rate"]:
            v = rate.get(k, None)
            if isinstance(v, (int, float)):
                return float(v)
        return 1e18

    best = sorted(rates, key=price_of)[0]
    best_price = price_of(best)
    if best_price >= 1e18:
        raise RuntimeError(f"Could not read price from rate: {best}")

    return best, best_price
