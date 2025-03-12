from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Vervang in productie

# Database initialisatie
def init_db():
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL, stock INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cart 
                 (id INTEGER PRIMARY KEY, user_id TEXT, product_id INTEGER, quantity INTEGER)''')
    # Voorbeelddata
    products = [
        ('Kippenvoer Premium', 'Pluimvee', 15.00, 50),
        ('Hondenshampoo', 'Huisdieren', 8.50, 30),
        ('Ontsmettingsmiddel', 'Bioveiligheid', 20.00, 20),
        ('Ontworming Rund', 'Rundvee', 25.00, 15),
        ('Kattenvoer', 'Huisdieren', 12.00, 40),
        ('Koeienmineralen', 'Rundvee', 30.00, 10)
    ]
    c.executemany("INSERT OR IGNORE INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)", products)
    conn.commit()
    conn.close()

# Homepagina
@app.route('/')
def index():
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products")
    categories = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template('index.html', categories=categories)

# Producten per categorie
@app.route('/category/<category>')
def category(category):
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute("SELECT id, name, price, stock FROM products WHERE category = ?", (category,))
    products = c.fetchall()
    conn.close()
    return render_template('category.html', category=category, products=products)

# Toevoegen aan winkelwagen
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        session['user_id'] = 'guest'  # Simpele gebruikersidentificatie
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])

    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
    stock = c.fetchone()[0]
    
    if quantity > stock:
        flash("Niet genoeg voorraad beschikbaar!")
    else:
        c.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)",
                  (session['user_id'], product_id, quantity))
        conn.commit()
        flash("Product toegevoegd aan winkelwagen!")
    conn.close()
    return redirect(request.referrer)

# Winkelwagen bekijken
@app.route('/cart')
def cart():
    if 'user_id' not in session:
        session['user_id'] = 'guest'
    
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute('''SELECT p.id, p.name, p.price, c.quantity 
                 FROM cart c JOIN products p ON c.product_id = p.id 
                 WHERE c.user_id = ?''', (session['user_id'],))
    cart_items = c.fetchall()
    total = sum(item[2] * item[3] for item in cart_items)  # Prijs * hoeveelheid
    conn.close()
    return render_template('cart.html', cart_items=cart_items, total=total)

# Betalingssimulatie
@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('cart'))
    
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute("SELECT product_id, quantity FROM cart WHERE user_id = ?", (session['user_id'],))
    cart_items = c.fetchall()
    
    for product_id, quantity in cart_items:
        c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
    c.execute("DELETE FROM cart WHERE user_id = ?", (session['user_id'],))
    conn.commit()
    conn.close()
    
    flash("Betaling succesvol! Bedankt voor je aankoop!")
    return redirect(url_for('index'))

if __name__ == '__main__':
    if not os.path.exists('webshop.db'):
        init_db()
    app.run(debug=True)