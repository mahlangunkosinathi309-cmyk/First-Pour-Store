import os
import uuid
import requests
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash
from courier_guy import courier_bp


app = Flask(__name__)
app.register_blueprint(courier_bp)

app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret-change-me"

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27645277314")
ADMIN_KEY = os.getenv("ADMIN_KEY", "1234")

YOCO_SECRET_KEY = os.getenv("YOCO_SECRET_KEY", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://127.0.0.1:5000").rstrip("/")
YOCO_CHECKOUT_URL = "https://payments.yoco.com/api/checkouts"

PRODUCTS = [
    {"id": "gin", "name": "First Pour – London Dry Gin", "price": 35000, "price_display": "R350", "desc": "Crisp · Aromatic · Classic", "img": "first-pour-gin.jpg"},
    {"id": "vodka", "name": "First Pour – Vanilla Vodka", "price": 35000, "price_display": "R350", "desc": "Smooth · Sweet · Velvety", "img": "first-pour-vodka.jpg"},
    {"id": "whitewine", "name": "First Pour – Sweet White Wine", "price": 20000, "price_display": "R200", "desc": "Light · Juicy · Sweet", "img": "first-pour-white-wine.jpg"},
]

def product_by_id(pid):
    for p in PRODUCTS:
        if p["id"] == pid:
            return p
    return None

def cart_total_cents(cart):
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

def cart_lines(cart):
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
        lines.append({"name": p["name"], "qty": q, "unit_display": p["price_display"], "line_cents": p["price"] * q})
    return lines

def cart_qty(cart):
    s = 0
    for _, qty in cart.items():
        try:
            s += int(qty)
        except:
            pass
    return s

def cents_to_zar(cents):
    s = f"{cents/100:.2f}"
    if s.endswith(".00"):
        s = s[:-3]
    return f"R{s}"

@app.context_processor
def inject_globals():
    cart = session.get("cart", {})
    return {"cart_qty": cart_qty(cart), "yoco_enabled": bool(YOCO_SECRET_KEY)}

@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS, whatsapp_number=WHATSAPP_NUMBER)

@app.route("/cart/add", methods=["POST"])
def cart_add():
    pid = (request.form.get("product_id") or "").strip()
    qty = (request.form.get("qty") or "1").strip()
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

    flash("Added to cart.")
    return redirect(url_for("index") + "#shop")

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart", {})
    lines = cart_lines(cart)
    subtotal = cart_total_cents(cart)

    delivery_method = session.get("delivery_method", "pickup")
    delivery_fee = 0 if delivery_method == "pickup" else 8000
    total = subtotal + delivery_fee

    if request.method == "POST":
        dm = request.form.get("delivery_method", "pickup")
        if dm not in ["pickup", "delivery"]:
            dm = "pickup"
        session["delivery_method"] = dm
        session["customer_name"] = (request.form.get("customer_name") or "").strip()
        session["customer_phone"] = (request.form.get("customer_phone") or "").strip()
        session["customer_address"] = (request.form.get("customer_address") or "").strip()
        return redirect(url_for("checkout"))

    delivery_method = session.get("delivery_method", "pickup")
    delivery_fee = 0 if delivery_method == "pickup" else 8000
    total = subtotal + delivery_fee

    return render_template(
        "checkout.html",
        whatsapp_number=WHATSAPP_NUMBER,
        lines=lines,
        subtotal_display=cents_to_zar(subtotal),
        delivery_method=delivery_method,
        delivery_fee_display=cents_to_zar(delivery_fee),
        total_display=cents_to_zar(total),
        total_cents=total,
        public_url=PUBLIC_URL,
    )

# -----------------------
# YOCO START (NO lineItems, NO pricingDetails)
# -----------------------
@app.route("/pay/yoco/start", methods=["POST"])
def yoco_start():
    if not YOCO_SECRET_KEY:
        flash("Yoco is not connected yet.")
        return redirect(url_for("checkout"))

    cart = session.get("cart", {})
    if cart_qty(cart) <= 0:
        flash("Your cart is empty.")
        return redirect(url_for("checkout"))

    subtotal = cart_total_cents(cart)
    delivery_method = session.get("delivery_method", "pickup")
    delivery_fee = 0 if delivery_method == "pickup" else 8000
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
    }

    headers = {
        "Authorization": f"Bearer {YOCO_SECRET_KEY}",
        "Content-Type": "application/json",
        "Idempotency-Key": order_id,
    }

    r = requests.post(YOCO_CHECKOUT_URL, json=payload, headers=headers, timeout=30)

    if r.status_code != 200:
        flash(f"Yoco rejected request ({r.status_code}). Response: {r.text}")
        return redirect(url_for("checkout"))

    data = r.json()
    redirect_url = data.get("redirectUrl", "")
    if not redirect_url:
        flash("Yoco did not return redirectUrl.")
        return redirect(url_for("checkout"))

    return redirect(redirect_url)

@app.route("/payment/success")
def payment_success():
    return render_template("success.html", order_id=session.get("order_id", ""))

@app.route("/payment/cancel")
def payment_cancel():
    return render_template("failed.html", title="Payment cancelled", message="You cancelled the payment.")

@app.route("/payment/failed")
def payment_failed():
    return render_template("failed.html", title="Payment failed", message="Payment did not complete. Please try again.")

@app.route("/admin")
def admin():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        abort(403)
    return {
        "ok": True,
        "public_url": PUBLIC_URL,
        "yoco_enabled": bool(YOCO_SECRET_KEY),
        "has_lineitems": False,
    }

if __name__ == "__main__":
    app.run(debug=True)
