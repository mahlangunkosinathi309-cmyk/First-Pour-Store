import os
import uuid
from urllib.parse import quote

import requests
from flask import Flask, render_template, request, redirect, url_for, session, abort

from courier_guy import get_best_rate

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret-change-me"

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27645277314")
ADMIN_KEY = os.getenv("ADMIN_KEY", "1234")

# Yoco
YOCO_SECRET_KEY = os.getenv("YOCO_SECRET_KEY", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://127.0.0.1:5000").rstrip("/")
YOCO_CHECKOUT_URL = "https://payments.yoco.com/api/checkouts"

PROVINCES = [
    "Gauteng (GP)",
    "Western Cape (WC)",
    "KwaZulu-Natal (KZN)",
    "Eastern Cape (EC)",
    "Free State (FS)",
    "Limpopo (LP)",
    "Mpumalanga (MP)",
    "North West (NW)",
    "Northern Cape (NC)",
]


PRODUCTS = [
    {
        "id": "gin",
        "name": "First Pour – London Dry Gin",
        "price": 35000,
        "price_display": "R350",
        "desc": "Crisp · Aromatic · Classic",
        "img": "first-pour-gin.jpg",
    },
    {
        "id": "vodka",
        "name": "First Pour – Vanilla Vodka",
        "price": 35000,
        "price_display": "R350",
        "desc": "Smooth · Sweet · Velvety",
        "img": "first-pour-vodka.jpg",
    },
    {
        "id": "whitewine",
        "name": "First Pour – Sweet White Wine",
        "price": 20000,
        "price_display": "R200",
        "desc": "Light · Juicy · Sweet",
        "img": "first-pour-white-wine.jpg",
    },
]


def product_by_id(pid: str):
    for p in PRODUCTS:
        if p["id"] == pid:
            return p
    return None


def cart_total_cents(cart: dict) -> int:
    total = 0
    for pid, qty in cart.items():
        p = product_by_id(pid)
        if not p:
            continue
        try:
            q = int(qty)
        except:
            q = 0
        if q > 0:
            total += p["price"] * q
    return total


def cart_lines(cart: dict):
    lines = []
    for pid, qty in cart.items():
        p = product_by_id(pid)
        if not p:
            continue
        try:
            q = int(qty)
        except:
            q = 0
        if q <= 0:
            continue
        lines.append(
            {
                "id": pid,
                "name": p["name"],
                "qty": q,
                "unit_cents": p["price"],
                "unit_display": p["price_display"],
                "line_cents": p["price"] * q,
            }
        )
    return lines


def cents_to_zar(cents: int) -> str:
    return f"R{cents/100:.2f}".replace(".00", "")


def cart_count(cart: dict) -> int:
    c = 0
    for _, qty in cart.items():
        try:
            c += int(qty)
        except:
            pass
    return c


@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS, whatsapp_number=WHATSAPP_NUMBER)


@app.route("/cart/add", methods=["POST"])
def cart_add():
    pid = request.form.get("product_id", "").strip()
    qty = request.form.get("qty", "1").strip()

    p = product_by_id(pid)
    if not p:
        return redirect(url_for("index"))

    try:
        qty_i = int(qty)
    except:
        qty_i = 1

    qty_i = max(1, min(99, qty_i))

    cart = session.get("cart", {})
    cart[pid] = int(cart.get(pid, 0)) + qty_i
    session["cart"] = cart

    # keep your current behavior (go to checkout). we can change later safely.
    return redirect(url_for("checkout"))


@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session["cart"] = {}
    session["delivery_fee_cents"] = 0
    session["cg_quote_raw"] = None
    session["cg_error"] = ""
    return redirect(url_for("checkout"))


@app.route("/checkout", methods=["GET"])
def checkout():
    cart = session.get("cart", {})
    lines = cart_lines(cart)
    subtotal = cart_total_cents(cart)

    # Cache lines for courier quoting without touching Yoco later
    session["cart_lines_cache"] = lines

    delivery_method = session.get("delivery_method", "pickup")

    # Delivery fee logic:
    if delivery_method == "pickup":
        delivery_fee = 0
    elif delivery_method == "flat":
        delivery_fee = 8000  # R80
    elif delivery_method == "courier_guy":
        delivery_fee = int(session.get("delivery_fee_cents", 0) or 0)
    else:
        delivery_method = "pickup"
        delivery_fee = 0

    total = subtotal + delivery_fee

    # courier ui values
    cg_error = session.get("cg_error", "")
    cg_quote_raw = session.get("cg_quote_raw", None)
    cg_quote_text = ""
    if isinstance(cg_quote_raw, dict):
        # show something readable
        cg_quote_text = str(cg_quote_raw.get("service_level", "")) or "Quote loaded"

    customer_name = session.get("customer_name", "")
    customer_phone = session.get("customer_phone", "")
    customer_email = session.get("customer_email", "")
    cg_street = session.get("cg_street", "")
    cg_suburb = session.get("cg_suburb", "")
    cg_city = session.get("cg_city", "")
    cg_postal = session.get("cg_postal", "")
    cg_province = session.get("cg_province", "Gauteng (GP)")

    whatsapp_text = f"Hi First Pour. I want to order:%0A"
    for l in lines:
        whatsapp_text += f"- {l['name']} x{l['qty']}%0A"
    whatsapp_text += f"%0ASubtotal: {cents_to_zar(subtotal)}%0ADelivery: {cents_to_zar(delivery_fee)}%0ATotal: {cents_to_zar(total)}"

    return render_template(
        "checkout.html",
        whatsapp_number=WHATSAPP_NUMBER,
        lines=lines,
        cart_count=cart_count(cart),
        subtotal_display=cents_to_zar(subtotal),
        delivery_method=delivery_method,
        delivery_fee_display=cents_to_zar(delivery_fee),
        total_display=cents_to_zar(total),
        total_cents=total,
        yoco_enabled=bool(YOCO_SECRET_KEY),
        cg_error=cg_error,
        cg_quote_text=cg_quote_text,
        provinces=PROVINCES,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        cg_street=cg_street,
        cg_suburb=cg_suburb,
        cg_city=cg_city,
        cg_postal=cg_postal,
        cg_province=cg_province,
        whatsapp_text=whatsapp_text,
    )


@app.route("/checkout/details", methods=["POST"])
def checkout_details():
    session["delivery_method"] = request.form.get("delivery_method", "pickup")

    session["customer_name"] = request.form.get("customer_name", "").strip()
    session["customer_phone"] = request.form.get("customer_phone", "").strip()
    session["customer_email"] = request.form.get("customer_email", "").strip()

    session["cg_street"] = request.form.get("cg_street", "").strip()
    session["cg_suburb"] = request.form.get("cg_suburb", "").strip()
    session["cg_city"] = request.form.get("cg_city", "").strip()
    session["cg_postal"] = request.form.get("cg_postal", "").strip()
    session["cg_province"] = request.form.get("cg_province", "Gauteng (GP)").strip()

    # if they changed details, clear old quote so they must re-quote
    session["delivery_fee_cents"] = 0
    session["cg_quote_raw"] = None
    session["cg_error"] = ""

    return redirect(url_for("checkout"))


@app.route("/courier/quote", methods=["POST"])
def courier_quote():
    session["cg_error"] = ""
    session["cg_quote_raw"] = None
    session["delivery_fee_cents"] = 0

    cart_lines_cache = session.get("cart_lines_cache", [])
    if not cart_lines_cache:
        session["cg_error"] = "Cart empty. Add items first."
        return redirect(url_for("checkout"))

    delivery_address = {
        "type": "residential",
        "company": "",
        "street_address": (session.get("cg_street") or "").strip(),
        "local_area": (session.get("cg_suburb") or "").strip(),
        "city": (session.get("cg_city") or "").strip(),
        "zone": (session.get("cg_province") or "Gauteng (GP)").split(" (")[0].strip() or "Gauteng",
        "country": "ZA",
        "code": (session.get("cg_postal") or "").strip(),
    }

    # basic validation to avoid 404 nonsense
    if not delivery_address["street_address"] or not delivery_address["city"] or not delivery_address["code"]:
        session["cg_error"] = "Fill Street address, City, and Postal code before quoting."
        return redirect(url_for("checkout"))

    try:
        best, best_price = get_best_rate(delivery_address, cart_lines_cache)
        # best_price is in ZAR (usually). Convert to cents safely.
        fee_cents = int(round(float(best_price) * 100))
        session["delivery_fee_cents"] = max(0, fee_cents)
        session["cg_quote_raw"] = best
        session["cg_error"] = ""
        session["delivery_method"] = "courier_guy"
    except Exception as e:
        session["cg_error"] = str(e)

    return redirect(url_for("checkout"))


# -----------------------
# YOCO: Start payment (DO NOT CHANGE)
# -----------------------
@app.route("/pay/yoco/start", methods=["POST"])
def yoco_start():
    if not YOCO_SECRET_KEY:
        return redirect(url_for("checkout"))

    cart = session.get("cart", {})
    lines = cart_lines(cart)
    if not lines:
        return redirect(url_for("checkout"))

    subtotal = cart_total_cents(cart)

    delivery_method = session.get("delivery_method", "pickup")
    if delivery_method == "pickup":
        delivery_fee = 0
    elif delivery_method == "flat":
        delivery_fee = 8000
    elif delivery_method == "courier_guy":
        delivery_fee = int(session.get("delivery_fee_cents", 0) or 0)
    else:
        delivery_fee = 0

    amount = subtotal + delivery_fee

    order_id = "FP-" + uuid.uuid4().hex[:10].upper()
    session["order_id"] = order_id

    payload = {
        "amount": amount,
        "currency": "ZAR",
        "successUrl": f"{PUBLIC_URL}/payment/success",
        "cancelUrl": f"{PUBLIC_URL}/payment/cancel",
        "failureUrl": f"{PUBLIC_URL}/payment/failed",
        "clientReferenceId": order_id,
        "metadata": {
            "order_id": order_id,
            "delivery_method": delivery_method,
            "subtotal_cents": subtotal,
            "delivery_cents": delivery_fee,
        },
        "lineItems": [
    {
        "displayName": l["name"],
        "quantity": l["qty"],
        "pricingDetails": {
            "price": l["unit_cents"],
            "currency": "ZAR",
        },

        # keep these too (harmless, helps if YOCO accepts older fields)
        "name": l["name"],
        "unitPrice": l["unit_cents"],
    }
    for l in lines
],

    }

    headers = {
        "Authorization": f"Bearer {YOCO_SECRET_KEY}",
        "Content-Type": "application/json",
        "Idempotency-Key": order_id,
    }

    r = requests.post(YOCO_CHECKOUT_URL, json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        session["cg_error"] = f"Yoco error {r.status_code}: {r.text}"
        return redirect(url_for("checkout"))

    data = r.json()
    redirect_url = data.get("redirectUrl", "")
    return redirect(redirect_url)


@app.route("/payment/success")
def payment_success():
    return "Payment successful ✅"


@app.route("/payment/cancel")
def payment_cancel():
    return "Payment cancelled"


@app.route("/payment/failed")
def payment_failed():
    return "Payment failed"


@app.route("/admin")
def admin():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        abort(403)
    return {"ok": True, "products": PRODUCTS}


if __name__ == "__main__":
    app.run(debug=True)
