import os
import uuid
import smtplib
from email.message import EmailMessage

import requests
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort

# -----------------------
# App config
# -----------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret-change-me"

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27645277314")
ADMIN_KEY = os.getenv("ADMIN_KEY", "1234")

# Yoco
YOCO_SECRET_KEY = os.getenv("YOCO_SECRET_KEY", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://127.0.0.1:5000").rstrip("/")
YOCO_CHECKOUT_URL = "https://payments.yoco.com/api/checkouts"

# Email / Leads (optional)
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "")  # where you want new signups sent
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

# -----------------------
# Products
# -----------------------
PRODUCTS = [
    {
        "id": "gin",
        "name": "First Pour – London Dry Gin",
        "price": 35000,  # cents
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

# Simple in-memory leads storage (Render disk is not guaranteed). For MVP display in admin.
LEADS = []


# -----------------------
# Helpers
# -----------------------
def product_by_id(pid: str):
    for p in PRODUCTS:
        if p["id"] == pid:
            return p
    return None


def get_cart() -> dict:
    cart = session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
    return cart


def cart_count(cart: dict) -> int:
    c = 0
    for _, qty in cart.items():
        try:
            c += int(qty)
        except:
            pass
    return c


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
                "img": p["img"],
            }
        )
    return lines


def cents_to_zar(cents: int) -> str:
    return f"R{cents/100:.2f}".replace(".00", "")


def send_lead_email(email_addr: str):
    # Optional: if SMTP not configured, just skip sending.
    if not (OWNER_EMAIL and SMTP_HOST and SMTP_USER and SMTP_PASS):
        return

    msg = EmailMessage()
    msg["Subject"] = "New First Pour signup"
    msg["From"] = SMTP_USER
    msg["To"] = OWNER_EMAIL
    msg.set_content(f"New email signup: {email_addr}")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


# -----------------------
# Shared context
# -----------------------
@app.context_processor
def inject_globals():
    cart = get_cart()
    return {
        "whatsapp_number": WHATSAPP_NUMBER,
        "cart_count": cart_count(cart),
    }


# -----------------------
# Pages
# -----------------------
@app.route("/")
def index():
    return render_template(
        "index.html",
        products=PRODUCTS,
    )


@app.route("/cart")
def cart_page():
    cart = get_cart()
    lines = cart_lines(cart)
    subtotal = cart_total_cents(cart)
    return render_template(
        "cart.html",
        lines=lines,
        subtotal_display=cents_to_zar(subtotal),
        subtotal_cents=subtotal,
    )


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = get_cart()
    lines = cart_lines(cart)
    subtotal = cart_total_cents(cart)

    delivery_method = session.get("delivery_method", "pickup")
    delivery_fee = 0 if delivery_method == "pickup" else 8000  # R80
    grand_total = subtotal + delivery_fee

    if request.method == "POST":
        delivery_method = request.form.get("delivery_method", "pickup")
        if delivery_method not in ["pickup", "delivery"]:
            delivery_method = "pickup"
        session["delivery_method"] = delivery_method

        session["customer_name"] = request.form.get("customer_name", "").strip()
        session["customer_phone"] = request.form.get("customer_phone", "").strip()
        session["customer_address"] = request.form.get("customer_address", "").strip()

        return redirect(url_for("checkout"))

    return render_template(
        "checkout.html",
        lines=lines,
        subtotal_display=cents_to_zar(subtotal),
        delivery_method=delivery_method,
        delivery_fee_display=cents_to_zar(delivery_fee),
        total_display=cents_to_zar(grand_total),
        total_cents=grand_total,
        public_url=PUBLIC_URL,
        yoco_enabled=bool(YOCO_SECRET_KEY),
    )


# -----------------------
# Cart actions (NO redirect to checkout!)
# -----------------------
@app.route("/cart/add", methods=["POST"])
def cart_add():
    pid = request.form.get("product_id", "").strip()
    qty = request.form.get("qty", "1").strip()

    p = product_by_id(pid)
    if not p:
        return jsonify({"ok": False, "message": "Product not found"}), 400

    try:
        qty_i = int(qty)
    except:
        qty_i = 1
    qty_i = max(1, min(99, qty_i))

    cart = get_cart()
    cart[pid] = int(cart.get(pid, 0)) + qty_i
    session["cart"] = cart

    # If request is AJAX → return JSON, else redirect back
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or "")
    if wants_json:
        return jsonify({"ok": True, "cart_count": cart_count(cart), "message": "Added to cart"})

    return redirect(url_for("index"))


@app.route("/cart/update", methods=["POST"])
def cart_update():
    cart = get_cart()
    for pid in list(cart.keys()):
        new_qty = request.form.get(f"qty_{pid}", None)
        if new_qty is None:
            continue
        try:
            q = int(new_qty)
        except:
            q = 0
        if q <= 0:
            cart.pop(pid, None)
        else:
            cart[pid] = min(99, q)
    session["cart"] = cart
    return redirect(url_for("cart_page"))


@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session["cart"] = {}
    return redirect(url_for("cart_page"))


# -----------------------
# Leads (email signup)
# -----------------------
@app.route("/subscribe", methods=["POST"])
def subscribe():
    email_addr = request.form.get("email", "").strip()
    if not email_addr or "@" not in email_addr:
        return redirect(url_for("index") + "#signup")

    LEADS.append(email_addr)

    # Optional email to you
    try:
        send_lead_email(email_addr)
    except:
        pass

    session["signup_ok"] = True
    return redirect(url_for("index") + "#signup")


# -----------------------
# YOCO: Start payment
# -----------------------
@app.route("/pay/yoco/start", methods=["POST"])
def yoco_start():
    if not YOCO_SECRET_KEY:
        return redirect(url_for("checkout"))

    cart = get_cart()
    lines = cart_lines(cart)
    if not lines:
        return redirect(url_for("cart_page"))

    subtotal = cart_total_cents(cart)
    delivery_method = session.get("delivery_method", "pickup")
    delivery_fee = 0 if delivery_method == "pickup" else 8000
    amount = subtotal + delivery_fee

    order_id = "FP-" + uuid.uuid4().hex[:10].upper()
    session["order_id"] = order_id

    # Yoco wants lineItems with displayName + pricingDetails (unitAmount)
    yoco_line_items = []
    for l in lines:
        yoco_line_items.append(
            {
                "displayName": l["name"],
                "quantity": l["qty"],
                "pricingDetails": {
                    "unitAmount": l["unit_cents"],
                    "currency": "ZAR",
                },
            }
        )

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
        "lineItems": yoco_line_items,
    }

    headers = {
        "Authorization": f"Bearer {YOCO_SECRET_KEY}",
        "Content-Type": "application/json",
        "Idempotency-Key": order_id,
    }

    r = requests.post(YOCO_CHECKOUT_URL, json=payload, headers=headers, timeout=30)
    if r.status_code != 200:
        session["yoco_error"] = f"Yoco rejected request ({r.status_code}). Response: {r.text}"
        return redirect(url_for("checkout"))

    data = r.json()
    redirect_url = data.get("redirectUrl", "")
    return redirect(redirect_url)


# -----------------------
# Payment return pages
# -----------------------
@app.route("/payment/success")
def payment_success():
    return render_template("success.html", order_id=session.get("order_id", ""))


@app.route("/payment/cancel")
def payment_cancel():
    return render_template("failed.html", title="Payment cancelled", message="You cancelled the payment.")


@app.route("/payment/failed")
def payment_failed():
    return render_template("failed.html", title="Payment failed", message="Payment did not complete. Please try again.")


# -----------------------
# Admin
# -----------------------
@app.route("/admin")
def admin():
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        abort(403)

    return {
        "ok": True,
        "public_url": PUBLIC_URL,
        "yoco_enabled": bool(YOCO_SECRET_KEY),
        "whatsapp_number": WHATSAPP_NUMBER,
        "products": PRODUCTS,
        "leads_count": len(LEADS),
        "leads": LEADS[-50:],  # last 50
        "cart_session_example": get_cart(),
    }


if __name__ == "__main__":
    app.run(debug=True)
