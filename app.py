DIFFICULTIES = ("Easy", "Moderate", "Hard")

TREK_STATUSES = (
    "Pending",
    "Approved",
    "Open",
    "Closed",
    "Ongoing",
    "Completed",
)

STAFF_TREK_STATUSES = (
    "Open",
    "Closed",
    "Ongoing",
    "Completed",
)

BOOKING_STATUSES = (
    "Booked",
    "Cancelled",
    "Completed",
)

from datetime import datetime
from functools import wraps
from auth.routes import (
    auth_bp,
    get_current_user,
    login_required,
    redirect_to_dashboard,
    role_required,
)
from admin import admin_bp
from staff import staff_bp
from user.routes import user_bp
from utils import parse_int, update_booking_status
from flask_wtf.csrf import CSRFProtect

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from dotenv import load_dotenv
import os
import re
from werkzeug.security import check_password_hash, generate_password_hash

csrf = CSRFProtect()

from extensions import db
from models import Booking, StaffProfile, Trek, User

load_dotenv()

def is_valid_email(email):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None


def is_valid_phone(phone):
    return not phone or re.fullmatch(r"[0-9+\-\s()]{7,20}", phone) is not None

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trekking.db"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    else:
        app.config.update(test_config)

    csrf.init_app(app)
    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(user_bp)

    @app.context_processor
    def inject_current_user():
        return {"current_user": get_current_user()}

    @app.route("/")
    def home():
        if get_current_user():
            return redirect_to_dashboard(get_current_user())
        return render_template("home.html")

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("errors/404.html"), 404


    @app.errorhandler(403)
    def access_forbidden(error):
        return render_template("errors/403.html"), 403


    @app.errorhandler(500)
    def internal_server_error(error):
        return render_template("errors/500.html"), 500

    return app


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def get_approved_staff():
    return (
        User.query.filter_by(role="staff", status="active")
        .join(StaffProfile)
        .filter(StaffProfile.approval_status == "approved")
        .order_by(User.name.asc())
        .all()
    )


def build_trek_from_form(trek):
    try:
        duration_days = int(request.form.get("duration_days", "0"))
        available_slots = int(request.form.get("available_slots", "0"))
        start_date = parse_date(request.form.get("start_date"))
        end_date = parse_date(request.form.get("end_date"))
    except ValueError:
        flash("Duration, slots, and dates must be valid.", "danger")
        return None

    name = request.form.get("name", "").strip()
    location = request.form.get("location", "").strip()
    difficulty = request.form.get("difficulty", "").strip()

    if difficulty not in DIFFICULTIES:
        flash("Invalid difficulty.", "danger")
        return None

    status = request.form.get("status", "Pending").strip()

    if status not in TREK_STATUSES:
        flash("Invalid trek status.", "danger")
        return None

    assigned_staff_raw = request.form.get("assigned_staff_id", "").strip()

    if assigned_staff_raw:
        try:
            assigned_staff_id = int(assigned_staff_raw)
        except ValueError:
            flash("Invalid staff selection.", "danger")
            return None

        staff = User.query.filter_by(
            id=assigned_staff_id,
            role="staff",
            status="Active"
        ).first()

        if (
            not staff
            or not staff.staff_profile
            or staff.staff_profile.approval_status != "Approved"
        ):
            flash("Selected staff member is not approved.", "danger")
            return None
    else:
        assigned_staff_id = None

    if not name or not location or not difficulty:
        flash("Trek name, location, and difficulty are required.", "danger")
        return None

    if duration_days <= 0 or available_slots < 0:
        flash("Duration must be positive and slots cannot be negative.", "danger")
        return None

    if start_date and end_date and end_date < start_date:
        flash("End date cannot be before start date.", "danger")
        return None

    trek.name = name
    trek.location = location
    trek.difficulty = difficulty
    trek.duration_days = duration_days
    trek.available_slots = available_slots
    trek.status = status
    trek.start_date = start_date
    trek.end_date = end_date
    trek.assigned_staff_id = assigned_staff_id
    return trek


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
