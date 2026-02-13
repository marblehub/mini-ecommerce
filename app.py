from models.order import Order, OrderItem
from models.user import db, User
from models.product import PhysicalProduct, DigitalProduct, SubscriptionProduct
from models.payment import CreditCard, PayPal, Bitcoin, BankTransfer
from models.cart import Cart
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import json
from math import ceil
from datetime import datetime, timedelta
from config import Config
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from decimal import Decimal, ROUND_HALF_UP


app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

cart = Cart()

def admin_required(func):
    @wraps(func)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            flash("Access denied. Admins only.")
            return redirect(url_for("index"))
        return func(*args, **kwargs)
    return wrapper


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

        obj.rating = rating
        product_objects[p["id"]] = obj

    return product_objects


products = load_products()

payments = {
    "credit/debit card": CreditCard(),
    "paypal": PayPal(),
    "bitcoin": Bitcoin(),
    "bank transfer": BankTransfer()
}


@app.route("/")
@app.route("/page/<int:page>")
def index(page=1):
    per_page = 6  # 2 rows × 3 cols
    all_products = list(products.values())
    total_pages = ceil(len(all_products) / per_page)
    
    start = (page - 1) * per_page
    end = start + per_page
    page_products = all_products[start:end]

    # Determine greeting based on time
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    # Determine username
    if current_user.is_authenticated:
        name = current_user.username
    else:
        name = "Guest"

    full_greeting = f"{greeting}, {name.title()}!"

    return render_template(
        "index.html",
        products=page_products,
        page=page,
        cart=cart,
        total_pages=total_pages,
        greeting=full_greeting,
        name=name
    )


@app.context_processor
def inject_cart():
    return dict(cart=cart)


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = products.get(product_id)

    if not product:
        abort(404)

    return render_template(
        "product_detail.html",
        product=product,
        cart=cart
    )



@app.route("/adds/<int:product_id>")
@login_required
def add_to_cart_s(product_id):
    product = products.get(product_id)
    if product:
        cart.add(product)
        flash(f"'{product.name}' added to cart.", "success")
    else:
        #flash("Product not found.")
        flash("Product not found.", "danger")
    return redirect(url_for("product_detail", product_id=product_id))


@app.route("/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):
    product = products.get(product_id)

    if product:
        quantity = int(request.form.get("quantity", 1))
        cart.add(product, quantity)
        flash(f"{product.name} (x{quantity}) added to cart.")
    else:
        flash("Product not found.")

    return redirect(url_for("product_detail", product_id=product_id))



# ---------- Cart routes ----------

@app.route("/cart")
@login_required
def view_cart():
	global vat, grand_total
	
	total=cart.total()
	vat = round(total * 0.1, 2)
	grand_total = round(total + vat, 2)

	return render_template(
		"cart.html",
		items=cart.list_items(),
		total=round(total, 2),
		vat=vat,
		grand_total=grand_total
	)


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
    country = request.form.get("country")
    delivery_company = request.form.get("delivery_company")
    payment_method = payment_key.title()

    if not all([address, city, zip_code, country, delivery_company, payment_method]):
        flash("Please fill all shipment details")
        return redirect(url_for("view_cart"))

    # Process payment
    total_amount = cart.total()
    payment.pay(total_amount)
    
    # Order/Delivery date
    order_date = datetime.now().strftime("%d-%m-%Y")
    delivery_date = (datetime.now() + timedelta(days=3)).strftime("%d-%m-%Y")

    # Create Order
    new_order = Order(
        user_id=current_user.id,
        address=address,
        city=city,
        zip_code=zip_code,
        country=country,
        delivery_company=delivery_company,
        order_date=order_date,
        payment_method=payment_method,
        delivery_date=delivery_date,
        total=total_amount,
    )

    db.session.add(new_order)
    
    for item in cart.items.values():
        product = item["product"]

        order_item = OrderItem(
            order=new_order,
            product_name=product.name,
            price=product.price,
            quantity=item["qty"],
            product_image=product.image  # ← save image filename
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

    # Calculate subtotal
    subtotal = sum(item.price * item.quantity for item in order.items)

    # VAT and total
    vat = round(subtotal * 0.1, 2)
    grand_total = round(subtotal + vat, 2)

    return render_template(
        "success.html",
        order=order,
        total=round(subtotal, 2),
        vat=vat,
        grand_total=grand_total
    )


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


@app.route("/invoice/<int:order_id>")
@login_required
def generate_invoice(order_id):
    order = Order.query.get_or_404(order_id)

    file_path = f"invoice_{order_id}.pdf"

    doc = SimpleDocTemplate(file_path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # --- Store Info ---
    elements.append(Paragraph("<b>Mini Store</b><sup>™</sup>", styles["Title"]))
    elements.append(Paragraph("123 Commerce Street", styles["Normal"]))
    elements.append(Paragraph("Berlin, Germany", styles["Normal"]))
    elements.append(Paragraph("Email: support@ministore.com", styles["Normal"]))
    elements.append(Spacer(1, 15))

    # --- Invoice Header ---
    elements.append(Paragraph(f"<b>Invoice</b>", styles["Heading1"]))
    elements.append(Paragraph(f"Invoice Number: {order.id}", styles["Normal"]))
    elements.append(Paragraph(f"Order Date: {order.order_date}", styles["Normal"]))
    elements.append(Spacer(1, 10))

    # --- Customer / Shipping ---
    elements.append(Paragraph("<b>Bill To:</b>", styles["Heading3"]))
    elements.append(Paragraph(order.address, styles["Normal"]))
    elements.append(Paragraph(f"{order.city}, {order.zip_code}", styles["Normal"]))
    elements.append(Paragraph(order.country, styles["Normal"]))
    elements.append(Spacer(1, 15))

    # --- Item Table ---
    table_data = [
        ["Item", "Qty", "Unit Price (€)", "Total (€)"]
    ]

    subtotal = Decimal("0.00")

    for item in order.items:
        unit_price = Decimal(str(item.price))
        quantity = Decimal(str(item.quantity))
        line_total = unit_price * quantity
        subtotal += line_total

        table_data.append([
            item.product_name,
            str(item.quantity),
            f"{unit_price:.2f}",
            f"{line_total:.2f}"
        ])

    vat = (subtotal * Decimal("0.1")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    grand_total = (subtotal + vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # --- Totals rows ---
    table_data.append(["", "", "Subtotal:", f"{subtotal:.2f}"])
    table_data.append(["", "", "VAT (10%):", f"{vat:.2f}"])
    table_data.append(["", "", "Total:", f"{grand_total:.2f}"])

    table = Table(table_data, colWidths=[220, 60, 100, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # --- Payment & Delivery ---
    elements.append(Paragraph(f"<b>Payment Method:</b> {order.payment_method}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Delivery Company:</b> {order.delivery_company}", styles["Normal"]))
    elements.append(Spacer(1, 15))

    # --- Footer ---
    elements.append(Paragraph(
        "Thank you for shopping with Mini Store.",
        styles["Italic"]
    ))

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
        flash("Account successfully created.")
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
    flash("Logged Out. Kindly login to continue shopping.")
    return redirect(url_for("index"))


# ---------- Admin ----------
@app.route("/admin")
@admin_required
def admin_dashboard():
    # if not current_user.is_admin:
        # flash("Access denied")
        # return redirect(url_for("index"))

    orders = Order.query.order_by(Order.id.desc()).all()
    total_revenue = sum(order.total for order in orders)

    return render_template(
        "admin.html",
        orders=orders,
        total_revenue=round(total_revenue, 2)
    )


@app.route("/register-admin", methods=["GET", "POST"])
@admin_required
def register_admin():
    # Only allow current admin users
    # if not current_user.is_admin:
        # flash("Access denied: only admins can create new admins.")
        # return redirect(url_for("index"))

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
        #return redirect(url_for("admin"))
        return render_template("admin.html")

    return render_template("register_admin.html")


@app.route("/admin/update_status/<int:order_id>", methods=["POST"])
@admin_required
def update_order_status(order_id):
    # if not current_user.is_admin:
        # flash("Access denied")
        # return redirect(url_for("index"))

    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status")

    order.status = new_status
    db.session.commit()

    flash(f"Order #{order.id} updated to {new_status}")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_order/<int:order_id>", methods=["POST"])
@admin_required
def delete_order(order_id):
    # if not current_user.is_admin:
        # flash("Access denied")
        # return redirect(url_for("index"))

    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()

    flash(f"Order #{order.id} deleted")
    return redirect(url_for("admin_dashboard"))


@app.route("/my-orders")
@login_required
def my_orders():
    orders = current_user.orders
    return render_template("my_orders.html", orders=orders)


if __name__ == "__main__":
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
	
