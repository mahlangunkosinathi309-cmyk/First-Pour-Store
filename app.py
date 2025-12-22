import os, json, time, uuid, sqlite3
from flask import Flask, render_template, request, redirect
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27645277314")

PRODUCTS = [
    {"sku": "GIN_LONDON_DRY", "name": "First Pour – London Dry Gin", "price_cents": 35000, "display_price": "R350"},
    {"sku": "VODKA_VANILLA", "name": "First Pour – Vanilla Vodka", "price_cents": 35000, "display_price": "R350"},
    {"sku": "WINE_SWEET_RED", "name": "First Pour – Sweet Red Wine", "price_cents": 20000, "display_price": "R200"},
    {"sku": "WINE_SWEET_WHITE", "name": "First Pour – Sweet White Wine", "price_cents": 20000, "display_price": "R200"},
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

def find_product(sku):
    return next((p for p in PRODUCTS if p["sku"] == sku), None)

def calc_cart(items):
    total = 0
    lines = []
    for it in items:
        p = find_product(it["sku"])
        qty = int(it["qty"])
        line = p["price_cents"] * qty
        total += line
        lines.append({"name": p["name"], "qty": qty, "line": line})
    return lines, total

@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS)

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "GET":
        items = json.loads(request.args.get("cart", "[]"))
        lines, total = calc_cart(items)
        return render_template("checkout.html", items=lines, total=total)

    name = request.form["name"]
    phone = request.form["phone"]
    email = request.form["email"]
    address = request.form["address"]
    items = json.loads(request.form["items_json"])

    lines, total = calc_cart(items)
    order_id = "ORD-" + uuid.uuid4().hex[:8]

    conn = db()
    conn.execute(
        "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
        (order_id, int(time.time()), name, phone, email, address,
         json.dumps(lines), total, "pending")
    )
    conn.commit()
    conn.close()

    msg = f"Order {order_id}%0ATotal R{total/100}%0AName {name}%0APhone {phone}"
    return redirect(f"https://wa.me/{WHATSAPP_NUMBER}?text={msg}")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
