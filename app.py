# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for
import os, json
from urllib.parse import quote

app = Flask(__name__)

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27645277314")

DELIVERY_FEE_CENTS = 8000  # R80.00

PRODUCTS = [
    {
        "sku": "GIN_LONDON_DRY",
        "name": "London Dry Gin",
        "price_cents": 35000,
        "price": "R350",
        "tagline": "Crisp - Aromatic - Classic",
        "image": "first-pour-gin.jpg",
    },
    {
        "sku": "VODKA_VANILLA",
        "name": "Vanilla Vodka",
        "price_cents": 35000,
        "price": "R350",
        "tagline": "Smooth - Sweet - Velvety",
        "image": "first-pour-vodka.jpg",
    },
    {
        "sku": "WINE_SWEET_WHITE",
        "name": "Sweet White Wine",
        "price_cents": 20000,
        "price": "R200",
        "tagline": "Light - Juicy - Sweet",
        "image": "first-pour-white-wine.jpg",
    },
]

def find_product(sku: str):
    for p in PRODUCTS:
        if p["sku"] == sku:
            return p
    return None

def normalize_cart(raw_items):
    items = []
    for it in raw_items:
        sku = str(it.get("sku", "")).strip()
        try:
            qty = int(it.get("qty", 0))
        except Exception:
            qty = 0
        if not sku or qty <= 0:
            continue
        p = find_product(sku)
        if not p:
            continue
        items.append({"sku": sku, "qty": qty})
    return items

def calc_lines(items):
    lines = []
    subtotal_cents = 0
    for it in items:
        p = find_product(it["sku"])
        if not p:
            continue
        qty = it["qty"]
        line_cents = p["price_cents"] * qty
        subtotal_cents += line_cents
        lines.append({
            "sku": p["sku"],
            "name": p["name"],
            "qty": qty,
            "unit_cents": p["price_cents"],
            "line_cents": line_cents,
        })
    return lines, subtotal_cents

@app.route("/")
def index():
    return render_template(
        "index.html",
        products=PRODUCTS,
        whatsapp_number=WHATSAPP_NUMBER,
    )

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "GET":
        cart_json = request.args.get("cart", "[]")
        try:
            raw_items = json.loads(cart_json)
        except Exception:
            raw_items = []

        items = normalize_cart(raw_items)
        lines, subtotal_cents = calc_lines(items)

        return render_template(
            "checkout.html",
            lines=lines,
            subtotal_cents=subtotal_cents,
            delivery_fee_cents=DELIVERY_FEE_CENTS,
            cart_raw=json.dumps(items),
            whatsapp_number=WHATSAPP_NUMBER,
        )

    # POST
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    address = (request.form.get("address") or "").strip()
    delivery_method = (request.form.get("delivery_method") or "pickup").strip().lower()
    cart_raw = request.form.get("cart_raw") or "[]"

    try:
        raw_items = json.loads(cart_raw)
    except Exception:
        raw_items = []

    items = normalize_cart(raw_items)
    lines, subtotal_cents = calc_lines(items)

    if subtotal_cents <= 0:
        return redirect(url_for("index"))

    delivery_fee = 0
    delivery_label = "Pickup"
    if delivery_method == "delivery":
        delivery_fee = DELIVERY_FEE_CENTS
        delivery_label = "Delivery"

    total_cents = subtotal_cents + delivery_fee

    msg_lines = []
    msg_lines.append("FIRST POUR ORDER")
    msg_lines.append("")
    msg_lines.append("Customer:")
    msg_lines.append(f"Name: {name}")
    msg_lines.append(f"Phone: {phone}")
    msg_lines.append(f"Delivery: {delivery_label}")
    if delivery_label == "Delivery":
        msg_lines.append(f"Address: {address}")
    msg_lines.append("")
    msg_lines.append("Items:")
    for ln in lines:
        rands = ln["line_cents"] / 100.0
        msg_lines.append(f"- {ln['qty']} x {ln['name']} = R{rands:.2f}")
    msg_lines.append("")
    msg_lines.append(f"SUBTOTAL: R{(subtotal_cents/100.0):.2f}")
    msg_lines.append(f"DELIVERY: R{(delivery_fee/100.0):.2f}")
    msg_lines.append(f"TOTAL: R{(total_cents/100.0):.2f}")
    msg_lines.append("")
    msg_lines.append("Payment: EFT / Cash (Yoco coming soon)")

    msg = "\n".join(msg_lines)
    wa_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(msg)}"
    return redirect(wa_url)

if __name__ == "__main__":
    app.run(debug=True)
