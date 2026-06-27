from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
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
        return render_template("admin/dashboard.html", stats=None, recent_bookings=[], pending_staff=[])

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


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
