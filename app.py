# -*- coding: utf-8 -*-
from flask import Flask, render_template
import os

app = Flask(__name__)

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "27645277314")

PRODUCTS = [
    {
        "name": "London Dry Gin",
        "price": "R350",
        "tagline": "Crisp - Aromatic - Classic",
        "image": "first-pour-gin.jpg",
    },
    {
        "name": "Vanilla Vodka",
        "price": "R350",
        "tagline": "Smooth - Sweet - Velvety",
        "image": "first-pour-vodka.jpg",
    },
    {
        "name": "Sweet White Wine",
        "price": "R200",
        "tagline": "Light - Juicy - Sweet",
        "image": "first-pour-white-wine.jpg",
    },
]

@app.route("/")
def index():
    return render_template(
        "index.html",
        products=PRODUCTS,
        whatsapp_number=WHATSAPP_NUMBER,
    )

if __name__ == "__main__":
    app.run(debug=True)
