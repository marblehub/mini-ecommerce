from models.order import Order, OrderItem
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import json

from config import Config
from models.user import db, User
from models.product import PhysicalProduct, DigitalProduct, SubscriptionProduct
from models.payment import CreditCard, PayPal, Bitcoin, BankTransfer
from models.cart import Cart

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

cart = Cart()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Load products
def load_products():
    with open("products.json") as f:
        data = json.load(f)

    product_objects = {}
    for p in data:
        rating = p.get("rating", 0)  # default 0 if not set
        if p["type"] == "physical":
            obj = PhysicalProduct(p["id"], p["name"], p["price"], p["image"])
        elif p["type"] == "digital":
            obj = DigitalProduct(p["id"], p["name"], p["price"], p["image"])
        else:
            obj = SubscriptionProduct(p["id"], p["name"], p["price"], p["image"])

        obj.rating = rating  # <-- add this line
        product_objects[p["id"]] = obj

    return product_objects


products = load_products()

payments = {
    "card": CreditCard(),
    "paypal": PayPal(),
    "bitcoin": Bitcoin(),
    "banktransfer": BankTransfer()
}


#@app.route("/")
#def index():
#    return render_template("index.html", products=products.values())


from math import ceil

@app.route("/")
@app.route("/page/<int:page>")
def index(page=1):
    per_page = 6  # 2 rows × 3 cols
    all_products = list(products.values())
    total_pages = ceil(len(all_products) / per_page)
    
    start = (page - 1) * per_page
    end = start + per_page
    page_products = all_products[start:end]

    return render_template(
        "index.html",
        products=page_products,
        page=page,
        total_pages=total_pages
    )


@app.route("/add/<int:product_id>")
@login_required
def add_to_cart(product_id):
    product = products.get(product_id)  # use the dict directly
    if product:
        cart.add(product)
        flash(f"{product.name} added to cart.")
    else:
        flash("Product not found.")
    return redirect(url_for("index"))


# ---------- Cart routes ----------
from flask import request, redirect, url_for, render_template, flash

@app.route("/cart")
@login_required
def view_cart():
    return render_template(
        "cart.html",
        items=cart.list_items(),
        total=cart.total(),
        message=""
    )

from datetime import datetime, timedelta
import random


@app.route("/cart", methods=["POST"])
@login_required
def checkout_cart():
    if not cart.items:
        flash("Your cart is empty!")
        return redirect(url_for("index"))

    payment_key = request.form.get("payment")
    payment = payments.get(payment_key)
    if not payment:
        flash("Please select a valid payment method")
        return redirect(url_for("view_cart"))

    # Shipment details
    address = request.form.get("address")
    city = request.form.get("city")
    zip_code = request.form.get("zip")
    delivery_company = request.form.get("delivery_company")

    if not all([address, city, zip_code, delivery_company]):
        flash("Please fill all shipment details")
        return redirect(url_for("view_cart"))

    # Process payment
    total_amount = cart.total()
    payment.pay(total_amount)

    # Delivery date
    delivery_date = (datetime.now() + timedelta(days=3)).strftime("%d-%m-%Y")

    # Create Order
    new_order = Order(
        user_id=current_user.id,
        address=address,
        city=city,
        zip_code=zip_code,
        delivery_company=delivery_company,
        delivery_date=delivery_date,
        total=total_amount,
    )

    db.session.add(new_order)

    # Save order items
    for item in cart.items.values():
        order_item = OrderItem(
            order=new_order,  # cleaner relationship usage
            product_name=item["product"].name,
            price=item["product"].price,
            quantity=item["qty"],
        )
        db.session.add(order_item)

    # Commit everything at once
    db.session.commit()

    # Clear cart
    cart.clear()

    return redirect(url_for("order_success", order_id=new_order.id))



@app.route("/success/<int:order_id>")
@login_required
def order_success(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("success.html", order=order)


@app.route("/track", methods=["GET", "POST"])
def track_order():
    order = None
    if request.method == "POST":
        order_id = request.form.get("order_id")
        order = Order.query.get(order_id)
    return render_template("track.html", order=order)


@app.route("/cart/delete/<int:product_id>")
@login_required
def delete_from_cart(product_id):
    cart.remove(product_id)
    flash("Item removed from cart.")
    return redirect(url_for("view_cart"))


@app.route("/cart/increase/<int:product_id>")
@login_required
def increase_qty(product_id):
    cart.increase(product_id)
    return redirect(url_for("view_cart"))


@app.route("/cart/decrease/<int:product_id>")
@login_required
def decrease_qty(product_id):
    cart.decrease(product_id)
    return redirect(url_for("view_cart"))


from flask import send_file
from reportlab.platypus import SimpleDocTemplate, Paragraph, ListItem, ListFlowable
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
import os
    

@app.route("/invoice/<int:order_id>")
@login_required
def generate_invoice(order_id):
    order = Order.query.get_or_404(order_id)

    file_path = f"invoice_{order_id}.pdf"

    doc = SimpleDocTemplate(file_path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Invoice - Order {order.id}", styles["Title"]))
    elements.append(Paragraph("Thank you for your purchase.", styles["Normal"]))
    elements.append(Paragraph("Items:", styles["Heading2"]))

    bullet_items = []
    for item in order.items:
        text = f"{item.product_name} ×{item.quantity} — €{item.price}"
        bullet_items.append(ListItem(Paragraph(text, styles["Normal"])))

    elements.append(ListFlowable(bullet_items))
    elements.append(Paragraph(f"Total: €{order.total}", styles["Heading3"]))

    doc.build(elements)

    return send_file(file_path, as_attachment=True)



# ---------- Auth ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User(username=username)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()
        flash("Account created.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials.")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


# ---------- Admin ----------
from flask import abort
@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("index"))

    orders = Order.query.order_by(Order.id.desc()).all()
    total_revenue = sum(order.total for order in orders)

    return render_template(
        "admin.html",
        orders=orders,
        total_revenue=total_revenue
    )


@app.route("/register-admin", methods=["GET", "POST"])
@login_required
def register_admin():
    # Only allow current admin users
    if not current_user.is_admin:
        flash("Access denied: only admins can create new admins.")
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Check if user already exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists.")
            return redirect(url_for("register_admin"))

        # Create new admin user
        new_admin = User(username=username)
        new_admin.set_password(password)
        new_admin.is_admin = True

        db.session.add(new_admin)
        db.session.commit()

        flash(f"Admin user '{username}' created successfully!")
        return redirect(url_for("admin"))

    return render_template("admin.html", users=users, orders=orders)


# @app.route("/admin/order/<int:order_id>/<status>")
# @login_required
# def update_order_status(order_id, status):
    # if not current_user.is_admin:
        # return "Access denied"

    # order = Order.query.get_or_404(order_id)
    # order.status = status
    # db.session.commit()

    # return f"Order {order_id} updated to {status}"


@app.route("/admin/update_status/<int:order_id>", methods=["POST"])
@login_required
def update_order_status(order_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("index"))

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status")

    order.status = new_status
    db.session.commit()

    flash(f"Order #{order.id} updated to {new_status}")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_order/<int:order_id>", methods=["POST"])
@login_required
def delete_order(order_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("index"))

    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()

    flash(f"Order #{order.id} deleted")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
	#with app.app_context():
	#	db.create_all()
		# app.py (at the bottom, inside if __name__ == "__main__": block)
	with app.app_context():
		db.create_all()  # make sure tables exist

		# Check if admin already exists
		admin = User.query.filter_by(username="admin").first()
		if not admin:
			admin = User(username="admin")
			admin.set_password("admin123")
			admin.is_admin = True
			db.session.add(admin)
			db.session.commit()
			print("Default admin created: username='admin', password='admin123'")
		else:
			print("Admin already exists.")

	app.run(debug=True)
	
