from werkzeug.security import generate_password_hash
import os
from dotenv import load_dotenv
from app import create_app
from extensions import db
from models import Booking, StaffProfile, Trek, User

load_dotenv()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

if not ADMIN_EMAIL or not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_EMAIL and ADMIN_PASSWORD must be set in .env")


def initialize_database():
    app = create_app()

    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(email=ADMIN_EMAIL).first()
        if admin is None:
            admin = User(
                name="Admin",
                email=ADMIN_EMAIL,
                password_hash=generate_password_hash(ADMIN_PASSWORD),
                role="admin",
                status="active",
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created.")
        else:
            print("Admin user already exists.")

        print("Database initialized successfully.")


if __name__ == "__main__":
    initialize_database()
