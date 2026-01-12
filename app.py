import os
import uuid
import requests
from flask import Flask, render_template, request, redirect, url_for, session, abort

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-secret-change-me"

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27600000000")
ADMIN_KEY = os.getenv("ADMIN_KEY", "1234")

YOCO_SECRET_KEY = os.getenv("YOCO_SECRET_KEY", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://127.0.0.1:5000").rstrip("/")

YOCO_CHECKOUT_URL = "https://payments.yoco.com/api/checkouts"

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
        q = int(qty)
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
    return redirect(url_for("checkout"))


@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session["cart"] = {}
    return redirect(url_for("checkout"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart", {})
    lines = cart_lines(cart)
    subtotal = cart_total_cents(cart)

    delivery_method = session.get("delivery_method", "pickup")
    delivery_fee = 0 if delivery_method == "pickup" else 8000
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

    yoco_error = session.pop("yoco_error", "")

    return render_template(
        "checkout.html",
        products=PRODUCTS,
        whatsapp_number=WHATSAPP_NUMBER,
        lines=lines,
        subtotal_display=cents_to_zar(subtotal),
        delivery_method=delivery_method,
        delivery_fee_display=cents_to_zar(delivery_fee),
        total_display=cents_to_zar(grand_total),
        total_cents=grand_total,
        public_url=PUBLIC_URL,
        yoco_enabled=bool(YOCO_SECRET_KEY),
        yoco_error=yoco_error,
    )


@app.route("/pay/yoco/start", methods=["POST"])
def yoco_start():
    if not YOCO_SECRET_KEY:
        session["yoco_error"] = "YOCO_SECRET_KEY not set on Render."
        return redirect(url_for("checkout"))

    cart = session.get("cart", {})
    lines = cart_lines(cart)
    if not lines:
        session["yoco_error"] = "Cart is empty."
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
        },
        "lineItems": [{"name": l["name"], "quantity": l["qty"], "unitPrice": l["unit_cents"]} for l in lines],
    }

    headers = {
        "Authorization": f"Bearer {YOCO_SECRET_KEY}",
        "Content-Type": "application/json",
        "Idempotency-Key": order_id,
    }

    try:
        r = requests.post(YOCO_CHECKOUT_URL, json=payload, headers=headers, timeout=30)
    except Exception as e:
        session["yoco_error"] = f"Request to Yoco failed: {e}"
        return redirect(url_for("checkout"))

    print("YOCO STATUS:", r.status_code)
    print("YOCO BODY:", r.text)

    if r.status_code != 200:
        session["yoco_error"] = f"Yoco rejected request ({r.status_code}). Check secret key + PUBLIC_URL."
        return redirect(url_for("checkout"))

    data = r.json()
    redirect_url = data.get("redirectUrl") or ""

    if not redirect_url:
        session["yoco_error"] = "Yoco returned no redirectUrl. Check your key or account permissions."
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
    return {"ok": True, "yoco_enabled": bool(YOCO_SECRET_KEY), "public_url": PUBLIC_URL, "products": PRODUCTS}


if __name__ == "__main__":
    app.run(debug=True)
