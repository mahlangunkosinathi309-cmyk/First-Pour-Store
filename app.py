import os, json, time, uuid, sqlite3
from flask import Flask, render_template, request, redirect
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27645277314")

# Luxury store catalog (with images + taglines)
PRODUCTS = [
    {
        "sku": "GIN_LONDON_DRY",
        "name": "London Dry Gin",
        "price_cents": 35000,
        "display_price": "R350",
        "image": "/static/img/first-pour-gin.jpg",
        "tagline": "Crisp · Aromatic · Classic",
    },
    {
        "sku": "VODKA_VANILLA",
        "name": "Vanilla Vodka",
        "price_cents": 35000,
        "display_price": "R350",
        "image": "/static/img/first-pour-vodka.jpg",
        "tagline": "Smooth · Sweet · Velvety",
    },
    {
        "sku": "WINE_SWEET_RED",
        "name": "Sweet Red Wine",
        "price_cents": 20000,
        "display_price": "R200",
        # Placeholder image until you upload a red-wine label
        "image": "/static/img/first-pour-white-wine.jpg",
        "tagline": "Rich · Juicy · Sweet",
    },
    {
        "sku": "WINE_SWEET_WHITE",
        "name": "Sweet White Wine",
        "price_cents": 20000,
        "display_price": "R200",
        "image": "/static/img/first-pour-white-wine.jpg",
        "tagline": "Light · Juicy · Sweet",
    },
]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            created_at INTEGER,
            customer_name TEXT,
            customer_phone TEXT,
            customer_email TEXT,
            address TEXT,
            items_json TEXT,
            amount_cents INTEGER,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

def find_product(sku: str):
    return next((p for p in PRODUCTS if p["sku"] == sku), None)

def calc_cart(items):
    total = 0
    lines = []
    for it in items:
        sku = it.get("sku")
        qty = int(it.get("qty", 0))
        if qty <= 0:
            continue
        p = find_product(sku)
        if not p:
            continue
        line = p["price_cents"] * qty
        total += line
        lines.append({"name": p["name"], "qty": qty, "line": line})
    return lines, total

@app.route("/")
def index():
    return render_template(
        "index.html",
        products=PRODUCTS,
        whatsapp_number=WHATSAPP_NUMBER
    )

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "GET":
        items = json.loads(request.args.get("cart", "[]"))
        lines, total = calc_cart(items)
        return render_template(
            "checkout.html",
            items=lines,
            total=total,
            cart_raw=request.args.get("cart", "[]")
        )

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    address = request.form.get("address", "").strip()
    items = json.loads(request.form.get("items_json", "[]"))

    lines, total = calc_cart(items)
    if total <= 0:
        return redirect("/")

    order_id = "ORD-" + uuid.uuid4().hex[:8]

    conn = db()
    conn.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)",
        (
            order_id,
            int(time.time()),
            name,
            phone,
            email,
            address,
            json.dumps(lines),
            total,
            "pending"
        )
    )
    conn.commit()
    conn.close()

    # WhatsApp message (simple & clean)
    msg = (
        f"First Pour Order%0A"
        f"Order ID: {order_id}%0A"
        f"Total: R{total/100:.2f}%0A"
        f"Name: {name}%0A"
        f"Phone: {phone}%0A"
        f"Email: {email}%0A"
        f"Address: {address}"
    )
    return redirect(f"https://wa.me/{WHATSAPP_NUMBER}?text={msg}")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
