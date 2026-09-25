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

    @app.context_processor
    def inject_current_user():
        return {"current_user": get_current_user()}

    @app.route("/")
    def home():
        if get_current_user():
            return redirect_to_dashboard(get_current_user())
        return render_template("home.html")

    @app.route("/admin/dashboard")
    @role_required("admin")
    def admin_dashboard():
        stats = {
            "treks": Trek.query.count(),
            "trekkers": User.query.filter_by(role="trekker").count(),
            "staff": User.query.filter_by(role="staff").count(),
            "bookings": Booking.query.count(),
        }
        recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(5).all()
        pending_staff = (
            User.query.filter_by(role="staff", status="pending")
            .order_by(User.created_at.desc())
            .all()
        )
        return render_template(
            "admin/dashboard.html",
            stats=stats,
            recent_bookings=recent_bookings,
            pending_staff=pending_staff,
        )

    @app.route("/admin/treks")
    @role_required("admin")
    def admin_treks():
        query = request.args.get("q", "").strip()
        treks_query = Trek.query
        if query:
            treks_query = treks_query.filter(
                db.or_(
                    Trek.name.ilike(f"%{query}%"),
                    Trek.location.ilike(f"%{query}%"),
                    Trek.id == parse_int(query, fallback=-1),
                )
            )
        treks = treks_query.order_by(Trek.start_date.asc().nullslast(), Trek.name.asc()).all()
        staff_members = get_approved_staff()
        return render_template(
            "admin/treks.html",
            treks=treks,
            staff_members=staff_members,
            query=query,
        )

    @app.route("/admin/treks/create", methods=["GET", "POST"])
    @role_required("admin")
    def create_trek():
        staff_members = get_approved_staff()
        if request.method == "POST":
            trek = build_trek_from_form(Trek())
            if trek is None:
                return render_template("admin/trek_form.html", trek=None, staff_members=staff_members)
            db.session.add(trek)
            db.session.commit()
            flash("Trek created successfully.", "success")
            return redirect(url_for("admin_treks"))

        return render_template("admin/trek_form.html", trek=None, staff_members=staff_members)

    @app.route("/admin/treks/<int:trek_id>/edit", methods=["GET", "POST"])
    @role_required("admin")
    def edit_trek(trek_id):
        trek = Trek.query.get_or_404(trek_id)
        staff_members = get_approved_staff()
        if request.method == "POST":
            updated_trek = build_trek_from_form(trek)
            if updated_trek is None:
                return render_template("admin/trek_form.html", trek=trek, staff_members=staff_members)
            db.session.commit()
            flash("Trek updated successfully.", "success")
            return redirect(url_for("admin_treks"))

        return render_template("admin/trek_form.html", trek=trek, staff_members=staff_members)

    @app.route("/admin/treks/<int:trek_id>/delete", methods=["POST"])
    @role_required("admin")
    def delete_trek(trek_id):
        trek = Trek.query.get_or_404(trek_id)
        db.session.delete(trek)
        db.session.commit()
        flash("Trek removed successfully.", "info")
        return redirect(url_for("admin_treks"))

    @app.route("/admin/treks/<int:trek_id>/assign", methods=["POST"])
    @role_required("admin")
    def assign_staff(trek_id):
        trek = Trek.query.get_or_404(trek_id)
        staff_id = parse_int(request.form.get("assigned_staff_id"), fallback=None)
        if staff_id is None:
            trek.assigned_staff_id = None
        else:
            staff = User.query.filter_by(id=staff_id, role="staff", status="active").first()
            if not staff:
                flash("Please select an approved staff member.", "danger")
                return redirect(url_for("admin_treks"))
            trek.assigned_staff_id = staff.id
        db.session.commit()
        flash("Staff assignment updated.", "success")
        return redirect(url_for("admin_treks"))

    @app.route("/admin/staff")
    @role_required("admin")
    def admin_staff():
        query = request.args.get("q", "").strip()
        staff_query = User.query.filter_by(role="staff")
        if query:
            staff_query = staff_query.filter(
                db.or_(
                    User.name.ilike(f"%{query}%"),
                    User.email.ilike(f"%{query}%"),
                    User.id == parse_int(query, fallback=-1),
                )
            )
        staff_members = staff_query.order_by(User.created_at.desc()).all()
        return render_template("admin/staff.html", staff_members=staff_members, query=query)

    @app.route("/admin/staff/create", methods=["GET", "POST"])
    @role_required("admin")
    def create_staff():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            contact_details = request.form.get("contact_details", "").strip()
            experience_years = request.form.get("experience_years", "0").strip()
            password = request.form.get("password", "")

            if not name or not email or not password:
                flash("Name, email, and password are required.", "danger")
                return render_template("admin/staff_form.html")

            if User.query.filter_by(email=email).first():
                flash("An account with this email already exists.", "danger")
                return render_template("admin/staff_form.html")

            try:
                experience_value = max(0, int(experience_years or 0))
            except ValueError:
                flash("Experience must be a number.", "danger")
                return render_template("admin/staff_form.html")

            staff = User(
                name=name,
                email=email,
                phone=phone,
                password_hash=generate_password_hash(password),
                role="staff",
                status="active",
            )
            staff.staff_profile = StaffProfile(
                contact_details=contact_details,
                experience_years=experience_value,
                approval_status="approved",
            )
            db.session.add(staff)
            db.session.commit()
            flash("Staff member added and approved.", "success")
            return redirect(url_for("admin_staff"))

        return render_template("admin/staff_form.html")

    @app.route("/admin/staff/<int:user_id>/approve", methods=["POST"])
    @role_required("admin")
    def approve_staff(user_id):
        staff = User.query.filter_by(id=user_id, role="staff").first_or_404()
        staff.status = "active"
        if staff.staff_profile:
            staff.staff_profile.approval_status = "approved"
        db.session.commit()
        flash("Staff member approved.", "success")
        return redirect(url_for("admin_staff"))

    @app.route("/admin/staff/<int:user_id>/blacklist", methods=["POST"])
    @role_required("admin")
    def blacklist_staff(user_id):
        staff = User.query.filter_by(id=user_id, role="staff").first_or_404()
        staff.status = "blacklisted"
        if staff.staff_profile:
            staff.staff_profile.approval_status = "rejected"
        db.session.commit()
        flash("Staff member blacklisted.", "warning")
        return redirect(url_for("admin_staff"))

    @app.route("/admin/staff/<int:user_id>/activate", methods=["POST"])
    @role_required("admin")
    def activate_staff(user_id):
        staff = User.query.filter_by(id=user_id, role="staff").first_or_404()
        staff.status = "active"
        if staff.staff_profile:
            staff.staff_profile.approval_status = "approved"
        db.session.commit()
        flash("Staff member activated.", "success")
        return redirect(url_for("admin_staff"))

    @app.route("/admin/staff/<int:user_id>/delete", methods=["POST"])
    @role_required("admin")
    def delete_staff(user_id):
        staff = User.query.filter_by(id=user_id, role="staff").first_or_404()
        for trek in staff.assigned_treks:
            trek.assigned_staff_id = None
        db.session.delete(staff)
        db.session.commit()
        flash("Staff member removed.", "info")
        return redirect(url_for("admin_staff"))

    @app.route("/admin/users")
    @role_required("admin")
    def admin_users():
        query = request.args.get("q", "").strip()
        users_query = User.query.filter_by(role="trekker")
        if query:
            users_query = users_query.filter(
                db.or_(
                    User.name.ilike(f"%{query}%"),
                    User.email.ilike(f"%{query}%"),
                    User.id == parse_int(query, fallback=-1),
                )
            )
        users = users_query.order_by(User.created_at.desc()).all()
        return render_template("admin/users.html", users=users, query=query)

    @app.route("/admin/users/<int:user_id>/blacklist", methods=["POST"])
    @role_required("admin")
    def blacklist_user(user_id):
        user = User.query.filter_by(id=user_id, role="trekker").first_or_404()
        user.status = "blacklisted"
        db.session.commit()
        flash("User blacklisted.", "warning")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<int:user_id>/activate", methods=["POST"])
    @role_required("admin")
    def activate_user(user_id):
        user = User.query.filter_by(id=user_id, role="trekker").first_or_404()
        user.status = "active"
        db.session.commit()
        flash("User activated.", "success")
        return redirect(url_for("admin_users"))

    @app.route("/admin/bookings")
    @role_required("admin")
    def admin_bookings():
        query = request.args.get("q", "").strip()
        bookings_query = Booking.query.join(User).join(Trek)
        if query:
            bookings_query = bookings_query.filter(
                db.or_(
                    User.name.ilike(f"%{query}%"),
                    Trek.name.ilike(f"%{query}%"),
                    Booking.id == parse_int(query, fallback=-1),
                )
            )
        bookings = bookings_query.order_by(Booking.booking_date.desc()).all()
        return render_template("admin/bookings.html", bookings=bookings, query=query)

    @app.route("/staff/dashboard")
    @role_required("staff")
    def staff_dashboard():
        staff = get_current_user()
        treks = Trek.query.filter_by(assigned_staff_id=staff.id).order_by(Trek.start_date.asc()).all()
        return render_template("staff/dashboard.html", treks=treks)

    @app.route("/staff/profile", methods=["GET", "POST"])
    @role_required("staff")
    def staff_profile():
        staff = get_current_user()
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()

            if not name:
                flash("Name is required.", "danger")
                return render_template("staff/profile.html", staff=staff)

            if len(name) > 100:
                flash("Name is too long.", "danger")
                return render_template("staff/profile.html", staff=staff)

            if not is_valid_phone(phone):
                flash("Please enter a valid phone number.", "danger")
                return render_template("staff/profile.html", staff=staff)

            staff.name = name
            staff.phone = phone
            profile = staff.staff_profile
            if profile:
                profile.contact_details = request.form.get("contact_details", "").strip()
                profile.bio = request.form.get("bio", "").strip()
                try:
                    profile.experience_years = max(
                        0,
                        int(request.form.get("experience_years", "0") or 0),
                    )
                except ValueError:
                    flash("Experience must be a number.", "danger")
                    return render_template("staff/profile.html", staff=staff)
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("staff_profile"))

        return render_template("staff/profile.html", staff=staff)

    @app.route("/staff/treks/<int:trek_id>")
    @role_required("staff")
    def staff_trek_detail(trek_id):
        trek = get_assigned_trek_or_404(trek_id)
        return render_template("staff/trek_detail.html", trek=trek)

    @app.route("/staff/treks/<int:trek_id>/update", methods=["POST"])
    @role_required("staff")
    def update_staff_trek(trek_id):
        trek = get_assigned_trek_or_404(trek_id)
        try:
            available_slots = int(request.form.get("available_slots", "0"))
        except ValueError:
            flash("Available slots must be a number.", "danger")
            return redirect(url_for("staff_trek_detail", trek_id=trek.id))

        status = request.form.get("status", "").strip()
        if status not in ["Open", "Closed", "Ongoing", "Completed"]:
            flash("Staff can update trek status only to Open, Closed, Ongoing, or Completed.", "danger")
            return redirect(url_for("staff_trek_detail", trek_id=trek.id))

        if available_slots < 0:
            flash("Available slots cannot be negative.", "danger")
            return redirect(url_for("staff_trek_detail", trek_id=trek.id))

        trek.available_slots = available_slots
        trek.status = status
        if status == "Completed":
            complete_booked_participants(trek)
        db.session.commit()
        flash("Trek details updated.", "success")
        return redirect(url_for("staff_trek_detail", trek_id=trek.id))

    @app.route("/staff/bookings/<int:booking_id>/status", methods=["POST"])
    @role_required("staff")
    def update_participant_status(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        get_assigned_trek_or_404(booking.trek_id)
        status = request.form.get("status", "").strip()
        if status not in ["Booked", "Cancelled", "Completed"]:
            flash("Invalid booking status.", "danger")
            return redirect(url_for("staff_trek_detail", trek_id=booking.trek_id))

        message, category = update_booking_status(booking, status)
        db.session.commit()
        flash(message, category)
        return redirect(url_for("staff_trek_detail", trek_id=booking.trek_id))

    @app.route("/user/dashboard")
    @role_required("trekker")
    def user_dashboard():
        user = get_current_user()
        open_treks = Trek.query.filter_by(status="Open").order_by(Trek.start_date.asc()).limit(5).all()
        bookings = Booking.query.filter_by(user_id=user.id).order_by(Booking.booking_date.desc()).all()
        return render_template("user/dashboard.html", open_treks=open_treks, bookings=bookings)

    @app.route("/user/profile", methods=["GET", "POST"])
    @role_required("trekker")
    def user_profile():
        user = get_current_user()
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()

            if not name:
                flash("Name is required.", "danger")
                return render_template("user/profile.html", user=user)

            if len(name) > 100:
                flash("Name is too long.", "danger")
                return render_template("user/profile.html", user=user)

            if not is_valid_phone(phone):
                flash("Please enter a valid phone number.", "danger")
                return render_template("user/profile.html", user=user)
            if not name:
                flash("Name is required.", "danger")
                return render_template("user/profile.html", user=user)
            user.name = name
            user.phone = phone
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("user_profile"))

        return render_template("user/profile.html", user=user)

    @app.route("/user/treks")
    @role_required("trekker")
    def user_treks():
        difficulty = request.args.get("difficulty", "").strip()
        location = request.args.get("location", "").strip()
        treks_query = Trek.query.filter_by(status="Open")
        if difficulty:
            treks_query = treks_query.filter(Trek.difficulty == difficulty)
        if location:
            treks_query = treks_query.filter(Trek.location.ilike(f"%{location}%"))
        treks = treks_query.order_by(Trek.start_date.asc().nullslast(), Trek.name.asc()).all()
        user_bookings = {
            booking.trek_id: booking
            for booking in Booking.query.filter_by(user_id=get_current_user().id).all()
            if booking.status in ["Booked", "Completed"]
        }
        return render_template(
            "user/treks.html",
            treks=treks,
            difficulty=difficulty,
            location=location,
            user_bookings=user_bookings,
        )

    @app.route("/user/treks/<int:trek_id>/book", methods=["POST"])
    @role_required("trekker")
    def book_trek(trek_id):
        user = get_current_user()
        trek = Trek.query.get_or_404(trek_id)

        existing_booking = Booking.query.filter(
            Booking.user_id == user.id,
            Booking.trek_id == trek.id,
            Booking.status.in_(["Booked", "Completed"]),
        ).first()
        if existing_booking:
            flash("You already have a booking record for this trek.", "warning")
            return redirect(url_for("user_treks"))

        if trek.status != "Open":
            flash("This trek is not open for booking.", "danger")
            return redirect(url_for("user_treks"))

        if trek.available_slots <= 0:
            flash("This trek is full.", "danger")
            return redirect(url_for("user_treks"))

        booking = Booking(
            user_id=user.id,
            trek_id=trek.id,
            status="Booked",
            payment_status="Pending",
        )
        trek.available_slots -= 1
        db.session.add(booking)
        db.session.commit()
        flash("Trek booked successfully.", "success")
        return redirect(url_for("user_history"))

    @app.route("/user/history")
    @role_required("trekker")
    def user_history():
        bookings = (
            Booking.query.filter_by(user_id=get_current_user().id)
            .order_by(Booking.booking_date.desc())
            .all()
        )
        return render_template("user/history.html", bookings=bookings)

    @app.route("/user/bookings/<int:booking_id>/cancel", methods=["POST"])
    @role_required("trekker")
    def cancel_booking(booking_id):
        booking = Booking.query.filter_by(id=booking_id, user_id=get_current_user().id).first_or_404()
        if booking.status != "Booked":
            flash("Only booked treks can be cancelled.", "warning")
            return redirect(url_for("user_history"))

        message, category = update_booking_status(booking, "Cancelled")
        db.session.commit()
        flash(message, category)
        return redirect(url_for("user_history"))

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

def parse_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


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


def get_assigned_trek_or_404(trek_id):
    staff = get_current_user()
    return Trek.query.filter_by(id=trek_id, assigned_staff_id=staff.id).first_or_404()


def update_booking_status(booking, new_status):
    old_status = booking.status
    if old_status == new_status:
        return "Booking status unchanged.", "info"

    if new_status == "Booked" and old_status == "Cancelled":
        if booking.trek.status != "Open":
            return "Cancelled bookings can be restored only when the trek is Open.", "danger"
        if booking.trek.available_slots <= 0:
            return "Cannot restore booking because the trek is full.", "danger"
        booking.trek.available_slots -= 1

    if new_status == "Cancelled" and old_status == "Booked":
        booking.trek.available_slots += 1

    booking.status = new_status
    return "Booking status updated.", "success"


def complete_booked_participants(trek):
    for booking in trek.bookings:
        if booking.status == "Booked":
            booking.status = "Completed"


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
