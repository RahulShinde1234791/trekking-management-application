from datetime import date, datetime

from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="trekker")
    phone = db.Column(db.String(20))
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    staff_profile = db.relationship(
        "StaffProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    assigned_treks = db.relationship("Trek", back_populates="assigned_staff")
    bookings = db.relationship(
        "Booking",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class StaffProfile(db.Model):
    __tablename__ = "staff_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    contact_details = db.Column(db.String(150))
    experience_years = db.Column(db.Integer, nullable=False, default=0)
    approval_status = db.Column(db.String(20), nullable=False, default="pending")
    bio = db.Column(db.Text)

    user = db.relationship("User", back_populates="staff_profile")


class Trek(db.Model):
    __tablename__ = "treks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    available_slots = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    assigned_staff_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    assigned_staff = db.relationship("User", back_populates="assigned_treks")
    bookings = db.relationship(
        "Booking",
        back_populates="trek",
        cascade="all, delete-orphan",
    )


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    trek_id = db.Column(db.Integer, db.ForeignKey("treks.id"), nullable=False)
    booking_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), nullable=False, default="Booked")
    payment_status = db.Column(db.String(20), nullable=False, default="Pending")

    user = db.relationship("User", back_populates="bookings")
    trek = db.relationship("Trek", back_populates="bookings")
