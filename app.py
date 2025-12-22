# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import json
import uuid
import urllib.parse

app = Flask(__name__)

# --- CONFIG ---
WHATSAPP_NUMBER = "27645277314"  # no +, country code first (South Africa: 27)

PRODUCTS = [
    {
        "sku": "GIN",
        "name": "London Dry Gin",
        "tagline": "Crisp · Aromatic · Classic",
        "price_cents": 35000,
        "price": "R350",
        "image": "first-pour-gin.jpg",
    },
    {
        "sku": "VODKA",
        "name": "Vanilla Vodka",
        "tagline": "Smooth · Sweet · Velvety",
        "price_cents": 35000,
        "price": "R350",
        "image": "first-pour-vodka.jpg",
    },
    {
        "sku": "WHITE_WINE",
        "name": "Sweet White Wine",
        "tagline": "Light · Juicy · Sweet",
        "price_cents": 20000,
        "price": "R200",
        "image": "first-pour-white-wine.jpg",
    },
    {
        "sku": "RED_WINE",
        "name": "Sweet Red Wine",
        "tagline": "Smooth · Juicy · Sweet",
        "price_cents": 20000,
        "price": "R200",
        "image": "first-pour-white-wine.jpg",  # placeholder image (replace later)
    },
]

SKU_MAP = {p["sku"]: p for p in PRODUCTS}


def safe_parse_cart(cart_str: str):
    """
    cart_str is urlencoded JSON like: [{"sku":"GIN","qty":2}, ...]
    """
    if not cart_str:
        return []
    try:
        decoded = urllib.parse.unquote(cart_str)
        data = json.loads(decoded)
        if not isinstance(data, list):
            return []
        cleaned = []
        for item in data:
            if not isinstance(item, dict):
                continue
            sku = str(item.get("sku", "")).strip()
            qty = item.get("qty", 0)
            if sku in SKU_MAP and isinstance(qty, int) and qty > 0:
                cleaned.append({"sku": sku, "qty": qty})
        return cleaned
    except Exception:
        return []


def cart_to_lines(cart):
    lines = []
    subtotal = 0
    for item in cart:
        p = SKU_MAP[item["sku"]]
        qty = item["qty"]
        line_total = p["price_cents"] * qty
        subtotal += line_total
        lines.append(
            {
                "sku": item["sku"],
                "name": p["name"],
                "qty": qty,
                "unit_price": p["price"],
                "line_total_cents": line_total,
                "line_total": f"R{line_total/100:.0f}",
            }
        )
    return lines, subtotal


@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS, whatsapp_number=WHATSAPP_NUMBER)


@app.route("/checkout")
def checkout():
    cart_raw = request.args.get("cart", "")
    cart = safe_parse_cart(cart_raw)
    lines, subtotal = cart_to_lines(cart)

    # defaults
    delivery_fee_cents = 8000  # R80
    pickup_fee_cents = 0

    return render_template(
        "checkout.html",
        whatsapp_number=WHATSAPP_NUMBER,
        cart_raw=cart_raw,
        cart=cart,
        lines=lines,
        subtotal_cents=subtotal,
        delivery_fee_cents=delivery_fee_cents,
        pickup_fee_cents=pickup_fee_cents,
    )


@app.route("/place-order", methods=["POST"])
def place_order():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    method = request.form.get("method", "pickup").strip()  # pickup | delivery
    address = request.form.get("address", "").strip()

    cart_raw = request.form.get("cart_raw", "")
    cart = safe_parse_cart(cart_raw)

    if not cart:
        return redirect(url_for("checkout", cart=cart_raw))

    lines, subtotal = cart_to_lines(cart)

    delivery_fee_cents = 8000  # R80
    total_cents = subtotal + (delivery_fee_cents if method == "delivery" else 0)

    order_id = uuid.uuid4().hex[:8].upper()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build WhatsApp message (clean, readable)
    msg_lines = []
    msg_lines.append(f"🍸 *FIRST POUR ORDER*")
    msg_lines.append(f"*Order ID:* {order_id}")
    msg_lines.append(f"*Time:* {ts}")
    msg_lines.append("")
    msg_lines.append(f"*Customer:* {name if name else 'N/A'}")
    msg_lines.append(f"*Phone:* {phone if phone else 'N/A'}")
    msg_lines.append("")
    msg_lines.append("*Items:*")
    for L in lines:
        msg_lines.append(f"- {L['name']} x{L['qty']} ({L['unit_price']}) = {L['line_total']}")
    msg_lines.append("")
    msg_lines.append(f"*Subtotal:* R{subtotal/100:.0f}")

    if method == "delivery":
        msg_lines.append(f"*Delivery:* R{delivery_fee_cents/100:.0f}")
        msg_lines.append(f"*Address:* {address if address else 'N/A'}")
    else:
        msg_lines.append(f"*Pickup:* Free")

    msg_lines.append(f"*Total:* R{total_cents/100:.0f}")
    msg_lines.append("")
    msg_lines.append("✅ Please confirm availability & payment method.")
    msg_lines.append("(Yoco coming soon)")

    message = "\n".join(msg_lines)
    wa_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={urllib.parse.quote(message)}"
    return redirect(wa_url)


if __name__ == "__main__":
    app.run(debug=True)
