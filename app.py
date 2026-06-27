from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import Booking, StaffProfile, Trek, User


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config["SECRET_KEY"] = "dev-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trekking.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    @app.context_processor
    def inject_current_user():
        return {"current_user": get_current_user()}

    @app.route("/")
    def home():
        if get_current_user():
            return redirect_to_dashboard(get_current_user())
        return render_template("home.html")

    @app.route("/register/user", methods=["GET", "POST"])
    def register_user():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            password = request.form.get("password", "")

            if not name or not email or not password:
                flash("Name, email, and password are required.", "danger")
                return render_template("auth/register_user.html")

            if User.query.filter_by(email=email).first():
                flash("An account with this email already exists.", "danger")
                return render_template("auth/register_user.html")

            user = User(
                name=name,
                email=email,
                phone=phone,
                password_hash=generate_password_hash(password),
                role="trekker",
                status="active",
            )
            db.session.add(user)
            db.session.commit()

            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("auth/register_user.html")

    @app.route("/register/staff", methods=["GET", "POST"])
    def register_staff():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            contact_details = request.form.get("contact_details", "").strip()
            experience_years = request.form.get("experience_years", "0").strip()
            bio = request.form.get("bio", "").strip()
            password = request.form.get("password", "")

            if not name or not email or not password:
                flash("Name, email, and password are required.", "danger")
                return render_template("auth/register_staff.html")

            if User.query.filter_by(email=email).first():
                flash("An account with this email already exists.", "danger")
                return render_template("auth/register_staff.html")

            try:
                experience_value = max(0, int(experience_years or 0))
            except ValueError:
                flash("Experience must be a number.", "danger")
                return render_template("auth/register_staff.html")

            staff = User(
                name=name,
                email=email,
                phone=phone,
                password_hash=generate_password_hash(password),
                role="staff",
                status="pending",
            )
            staff.staff_profile = StaffProfile(
                contact_details=contact_details,
                experience_years=experience_value,
                approval_status="pending",
                bio=bio,
            )
            db.session.add(staff)
            db.session.commit()

            flash("Staff registration submitted. Admin approval is required before login.", "info")
            return redirect(url_for("login"))

        return render_template("auth/register_staff.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email).first()

            if not user or not check_password_hash(user.password_hash, password):
                flash("Invalid email or password.", "danger")
                return render_template("auth/login.html")

            if user.status == "blacklisted":
                flash("This account is blacklisted. Please contact the administrator.", "danger")
                return render_template("auth/login.html")

            if user.role == "staff":
                profile = user.staff_profile
                if user.status != "active" or not profile or profile.approval_status != "approved":
                    flash("Your staff account is waiting for admin approval.", "warning")
                    return render_template("auth/login.html")

            session.clear()
            session["user_id"] = user.id
            flash(f"Welcome, {user.name}.", "success")
            return redirect_to_dashboard(user)

        return render_template("auth/login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

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

    @app.route("/user/dashboard")
    @role_required("trekker")
    def user_dashboard():
        user = get_current_user()
        open_treks = Trek.query.filter_by(status="Open").order_by(Trek.start_date.asc()).all()
        bookings = Booking.query.filter_by(user_id=user.id).order_by(Booking.booking_date.desc()).all()
        return render_template("user/dashboard.html", open_treks=open_treks, bookings=bookings)

    return app


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if user.status == "blacklisted":
                session.clear()
                flash("This account is blacklisted.", "danger")
                return redirect(url_for("login"))
            if user.role not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect_to_dashboard(user)
            if user.role == "staff":
                profile = user.staff_profile
                if user.status != "active" or not profile or profile.approval_status != "approved":
                    session.clear()
                    flash("Staff access requires admin approval.", "warning")
                    return redirect(url_for("login"))
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


def redirect_to_dashboard(user):
    if user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if user.role == "staff":
        return redirect(url_for("staff_dashboard"))
    return redirect(url_for("user_dashboard"))


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
    status = request.form.get("status", "Pending").strip()
    assigned_staff_id = parse_int(request.form.get("assigned_staff_id"), fallback=None)

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
    app.run(debug=True)
