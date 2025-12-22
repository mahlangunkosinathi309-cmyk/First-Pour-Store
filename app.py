# -*- coding: utf-8 -*-
import os
import json
import uuid
import sqlite3
import urllib.parse
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, abort

app = Flask(__name__)

# ======================
# CONFIG
# ======================
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "27645277314")  # SA: 27..., no +
ADMIN_KEY = os.environ.get("ADMIN_KEY", "1234")  # change on Render

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")


# ======================
# DB HELPERS
# ======================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            sku TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tagline TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            image TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Default settings
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ("delivery_fee_cents", "8000"))

    # Seed products if table empty
    count = cur.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    if count == 0:
        seed = [
            ("GIN", "London Dry Gin", "Crisp · Aromatic · Classic", 35000, "first-pour-gin.jpg", 1, 1),
            ("VODKA", "Vanilla Vodka", "Smooth · Sweet · Velvety", 35000, "first-pour-vodka.jpg", 1, 2),
            ("WHITE_WINE", "Sweet White Wine", "Light · Juicy · Sweet", 20000, "first-pour-white-wine.jpg", 1, 3),
            ("RED_WINE", "Sweet Red Wine", "Smooth · Juicy · Sweet", 20000, "first-pour-red-wine.jpg", 1, 4),
        ]
        cur.executemany("""
            INSERT INTO products (sku, name, tagline, price_cents, image, active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, seed)

    conn.commit()
    conn.close()


def get_setting_int(key: str, default: int) -> int:
    conn = db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return default
    try:
        return int(row["value"])
    except Exception:
        return default


def set_setting_int(key: str, value: int):
    conn = db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(int(value))))
    conn.commit()
    conn.close()


def get_products(active_only=True):
    conn = db()
    if active_only:
        rows = conn.execute("""
            SELECT sku, name, tagline, price_cents, image, active, sort_order
            FROM products
            WHERE active = 1
            ORDER BY sort_order ASC, name ASC
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT sku, name, tagline, price_cents, image, active, sort_order
            FROM products
            ORDER BY sort_order ASC, name ASC
        """).fetchall()
    conn.close()

    products = []
    for r in rows:
        products.append({
            "sku": r["sku"],
            "name": r["name"],
            "tagline": r["tagline"],
            "price_cents": int(r["price_cents"]),
            "price": f"R{int(r['price_cents'])//100}",
            "image": r["image"],
            "active": int(r["active"]),
            "sort_order": int(r["sort_order"]),
        })
    return products


def get_product_map(active_only=True):
    products = get_products(active_only=active_only)
    return {p["sku"]: p for p in products}


# ======================
# CART HELPERS
# ======================
def safe_parse_cart(cart_str: str, sku_map):
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
            if sku in sku_map and isinstance(qty, int) and qty > 0:
                cleaned.append({"sku": sku, "qty": qty})
        return cleaned
    except Exception:
        return []


def cart_to_lines(cart, sku_map):
    lines = []
    subtotal = 0
    for item in cart:
        p = sku_map[item["sku"]]
        qty = item["qty"]
        line_total = p["price_cents"] * qty
        subtotal += line_total
        lines.append({
            "sku": item["sku"],
            "name": p["name"],
            "qty": qty,
            "unit_price": p["price"],
            "line_total_cents": line_total,
            "line_total": f"R{line_total//100}",
        })
    return lines, subtotal


# ======================
# AUTH (ADMIN)
# ======================
def admin_required():
    if not session.get("is_admin"):
        return False
    return True


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    # If already logged in, go dashboard
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        key = (request.form.get("key") or "").strip()
        if key == ADMIN_KEY:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Wrong key. Try again.")

    return render_template("admin_login.html", error="")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin/dashboard", methods=["GET"])
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))

    products = get_products(active_only=False)
    delivery_fee_cents = get_setting_int("delivery_fee_cents", 8000)

    return render_template(
        "admin.html",
        products=products,
        delivery_fee=delivery_fee_cents // 100
    )


@app.route("/admin/save", methods=["POST"])
def admin_save():
    if not admin_required():
        return redirect(url_for("admin_login"))

    # Save delivery fee
    delivery_fee = int((request.form.get("delivery_fee") or "80").strip() or "80")
    set_setting_int("delivery_fee_cents", delivery_fee * 100)

    # Save products (multi-form fields)
    conn = db()
    cur = conn.cursor()

    skus = request.form.getlist("sku")
    for sku in skus:
        name = (request.form.get(f"name_{sku}") or "").strip()
        tagline = (request.form.get(f"tagline_{sku}") or "").strip()
        price = int((request.form.get(f"price_{sku}") or "0").strip() or "0")
        image = (request.form.get(f"image_{sku}") or "").strip()
        sort_order = int((request.form.get(f"sort_{sku}") or "0").strip() or "0")
        active = 1 if request.form.get(f"active_{sku}") == "on" else 0

        # Basic safety
        if price < 0:
            price = 0

        cur.execute("""
            UPDATE products
            SET name = ?, tagline = ?, price_cents = ?, image = ?, active = ?, sort_order = ?
            WHERE sku = ?
        """, (name, tagline, price * 100, image, active, sort_order, sku))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))


# ======================
# STORE ROUTES
# ======================
@app.route("/")
def index():
    products = get_products(active_only=True)
    return render_template("index.html", products=products, whatsapp_number=WHATSAPP_NUMBER)


@app.route("/checkout")
def checkout():
    sku_map = get_product_map(active_only=True)
    cart_raw = request.args.get("cart", "")
    cart = safe_parse_cart(cart_raw, sku_map)

    lines, subtotal = cart_to_lines(cart, sku_map)

    delivery_fee_cents = get_setting_int("delivery_fee_cents", 8000)
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
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    method = (request.form.get("method") or "pickup").strip()  # pickup | delivery
    address = (request.form.get("address") or "").strip()

    sku_map = get_product_map(active_only=True)
    cart_raw = request.form.get("cart_raw", "")
    cart = safe_parse_cart(cart_raw, sku_map)

    if not cart:
        return redirect(url_for("checkout", cart=cart_raw))

    lines, subtotal = cart_to_lines(cart, sku_map)

    delivery_fee_cents = get_setting_int("delivery_fee_cents", 8000)
    total_cents = subtotal + (delivery_fee_cents if method == "delivery" else 0)

    order_id = uuid.uuid4().hex[:8].upper()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    msg = []
    msg.append("🍸 *FIRST POUR ORDER*")
    msg.append(f"*Order ID:* {order_id}")
    msg.append(f"*Time:* {ts}")
    msg.append("")
    msg.append(f"*Customer:* {name if name else 'N/A'}")
    msg.append(f"*Phone:* {phone if phone else 'N/A'}")
    msg.append("")
    msg.append("*Items:*")
    for L in lines:
        msg.append(f"- {L['name']} x{L['qty']} ({L['unit_price']}) = {L['line_total']}")
    msg.append("")
    msg.append(f"*Subtotal:* R{subtotal//100}")

    if method == "delivery":
        msg.append(f"*Delivery:* R{delivery_fee_cents//100}")
        msg.append(f"*Address:* {address if address else 'N/A'}")
    else:
        msg.append("*Pickup:* Free")

    msg.append(f"*Total:* R{total_cents//100}")
    msg.append("")
    msg.append("✅ Please confirm availability & payment method.")
    msg.append("(Yoco coming soon)")

    wa_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={urllib.parse.quote(chr(10).join(msg))}"
    return redirect(wa_url)


# ======================
# STARTUP
# ======================
init_db()

if __name__ == "__main__":
    app.run(debug=True)
