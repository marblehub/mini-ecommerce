import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import app
from models.user import db, User

with app.app_context():
    db.create_all()

    # Create admin user
    admin = User(username="admin", is_admin=True)
    admin.set_password("admin123")

    db.session.add(admin)
    db.session.commit()

    print("Database initialized with admin account.")
