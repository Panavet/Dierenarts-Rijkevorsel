from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from mollie.api.client import Client
from mollie.api.error import Error as MollieError

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Vervang in productie
MOLLIE_API_KEY = 'test_dzukRdmb7BnDuugMzHxRdddRJbCRJS'  # Vervang door je Mollie-testkey
mollie_client = Client()
mollie_client.set_api_key(MOLLIE_API_KEY)

# Database initialisatie
def init_db():
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL, stock INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cart 
                 (id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER, quantity INTEGER)''')
    # Voorbeelddata
    products = [
        ('Kippenvoer Premium', 'Pluimvee', 15.00, 50),
        ('Hondenshampoo', 'Huisdieren', 8.50, 30),
        ('Ontsmettingsmiddel', 'Bioveiligheid', 20.00, 20),
        ('Ontworming Rund', 'Rundvee', 25.00, 15),
    ]
    c.executemany("INSERT OR IGNORE INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)", products)
    conn.commit()
    conn.close()

# Loginpagina
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = sqlite3.connect('webshop.db')
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email = ? AND password = ?", (email, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            flash("Succesvol ingelogd!")
            return redirect(url_for('index'))
        else:
            flash("Ongeldige inloggegevens.")
    return render_template('login.html')

# Registratiepagina
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = sqlite3.connect('webshop.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
            conn.commit()
            flash("Account aangemaakt! Log in om verder te gaan.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("E-mailadres is al in gebruik.")
        conn.close()
    return render_template('register.html')

# Homepagina
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products")
    categories = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template('index.html', categories=categories)

# Producten per categorie
@app.route('/category/<category>')
def category(category):
    if 'user_id' not in session:
        return redirect(url_for('login'))
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
        return redirect(url_for('login'))
    product_id = request.form['product_id']
    quantity = int(request.form['quantity'])
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
    stock = c.fetchone()[0]
    if quantity > stock:
        flash("Niet genoeg voorraad beschikbaar!")
    else:
        c.execute("INSERT OR REPLACE INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)",
                  (session['user_id'], product_id, quantity))
        conn.commit()
        flash("Product toegevoegd aan winkelwagen!")
    conn.close()
    return redirect(request.referrer)

# Winkelwagen bekijken en aanpassen
@app.route('/cart', methods=['GET', 'POST'])
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    if request.method == 'POST':
        product_id = request.form['product_id']
        quantity = int(request.form['quantity'])
        c.execute("UPDATE cart SET quantity = ? WHERE user_id = ? AND product_id = ?",
                  (quantity, session['user_id'], product_id))
        conn.commit()
        flash("Aantal aangepast!")
    c.execute('''SELECT p.id, p.name, p.price, c.quantity 
                 FROM cart c JOIN products p ON c.product_id = p.id 
                 WHERE c.user_id = ?''', (session['user_id'],))
    cart_items = c.fetchall()
    total = sum(item[2] * item[3] for item in cart_items)
    conn.close()
    return render_template('cart.html', cart_items=cart_items, total=total)

# Afrekenen met Mollie
@app.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('webshop.db')
    c = conn.cursor()
    c.execute('''SELECT p.id, p.name, p.price, c.quantity 
                 FROM cart c JOIN products p ON c.product_id = p.id 
                 WHERE c.user_id = ?''', (session['user_id'],))
    cart_items = c.fetchall()
    total = sum(item[2] * item[3] for item in cart_items)
    try:
        payment = mollie_client.payments.create({
            'amount': {'currency': 'EUR', 'value': f'{total:.2f}'},
            'description': 'Bestelling bij Dierenarts Rijkevorsel',
            'redirectUrl': url_for('payment_success', _external=True),
            'webhookUrl': 'https://your-webhook-url.com',  # Voor productie nodig
        })
        session['payment_id'] = payment.id
        for product_id, _, _, quantity in cart_items:
            c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
        c.execute("DELETE FROM cart WHERE user_id = ?", (session['user_id'],))
        conn.commit()
        conn.close()
        return redirect(payment.checkout_url)
    except MollieError as e:
        flash(f"Fout bij betaling: {str(e)}")
        conn.close()
        return redirect(url_for('cart'))

# Betalingssucces
@app.route('/payment_success')
def payment_success():
    if 'payment_id' in session:
        payment_id = session.pop('payment_id')
        payment = mollie_client.payments.get(payment_id)
        if payment.is_paid():
            flash("Hartelijk dank voor uw beestelling!")
        else:
            flash("Betaling niet voltooid.")
    return redirect(url_for('index'))

# Uitloggen
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    if not os.path.exists('webshop.db'):
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)