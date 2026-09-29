from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Index

from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        nullable=False,
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="trekker",
    )

    phone = db.Column(
        db.String(20),
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="active",
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'staff', 'trekker')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "status IN ('active', 'pending', 'blacklisted', 'deactivated')",
            name="ck_users_status",
        ),
    )

    staff_profile = db.relationship(
        "StaffProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    trekker_profile = db.relationship(
        "TrekkerProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    assigned_treks = db.relationship(
        "Trek",
        back_populates="assigned_staff",
        passive_deletes=True,
    )

    bookings = db.relationship(
        "Booking",
        back_populates="user",
        passive_deletes=True,
    )


class StaffProfile(db.Model):
    __tablename__ = "staff_profiles"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        unique=True,
    )

    staff_code = db.Column(
        db.String(20),
        nullable=False,
        unique=True
    )

    contact_details = db.Column(
        db.String(150),
    )

    experience_years = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    approval_status = db.Column(
        db.String(20),
        nullable=False,
        default="pending",
    )

    bio = db.Column(
        db.Text,
    )

    __table_args__ = (
        CheckConstraint(
            "experience_years >= 0",
            name="ck_staff_profiles_experience_nonnegative",
        ),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_staff_profiles_approval_status",
        ),
    )

    user = db.relationship(
        "User",
        back_populates="staff_profile",
    )

class TrekkerProfile(db.Model):
    __tablename__ = "trekker_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    trekker_code = db.Column(db.String(20), nullable=False, unique=True)

    user = db.relationship("User", back_populates="trekker_profile")

class Trek(db.Model):
    __tablename__ = "treks"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(120),
        nullable=False,
    )

    location = db.Column(
        db.String(120),
        nullable=False,
    )

    difficulty = db.Column(
        db.String(20),
        nullable=False,
    )

    duration_days = db.Column(
        db.Integer,
        nullable=False,
    )

    available_slots = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending",
    )

    start_date = db.Column(
        db.Date,
    )

    end_date = db.Column(
        db.Date,
    )

    assigned_staff_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "duration_days > 0",
            name="ck_treks_duration_positive",
        ),
        CheckConstraint(
            "available_slots >= 0",
            name="ck_treks_slots_nonnegative",
        ),
        CheckConstraint(
            "difficulty IN ('Easy', 'Moderate', 'Hard')",
            name="ck_treks_difficulty",
        ),
        CheckConstraint(
            """
            status IN (
                'Pending',
                'Approved',
                'Open',
                'Closed',
                'Ongoing',
                'Completed',
                'Archived'
            )
            """,
            name="ck_treks_status",
        ),
        CheckConstraint(
            """
            start_date IS NULL
            OR end_date IS NULL
            OR end_date >= start_date
            """,
            name="ck_treks_date_order",
        ),
    )

    assigned_staff = db.relationship(
        "User",
        back_populates="assigned_treks",
    )

    bookings = db.relationship(
        "Booking",
        back_populates="trek",
        passive_deletes=True,
    )


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    trek_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "treks.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    booking_date = db.Column(
        db.Date,
        nullable=False,
        default=date.today,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="Booked",
    )

    payment_status = db.Column(
        db.String(20),
        nullable=False,
        default="Pending",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('Booked', 'Cancelled', 'Completed')",
            name="ck_bookings_status",
        ),
        CheckConstraint(
            "payment_status IN ('Pending', 'Paid', 'Failed', 'Refunded')",
            name="ck_bookings_payment_status",
        ),
        Index(
            "uq_active_booking_user_trek",
            "user_id",
            "trek_id",
            unique=True,
            sqlite_where=(
                status.in_(["Booked", "Completed"])
            ),
        ),
    )

    user = db.relationship(
        "User",
        back_populates="bookings",
    )

    trek = db.relationship(
        "Trek",
        back_populates="bookings",
    )