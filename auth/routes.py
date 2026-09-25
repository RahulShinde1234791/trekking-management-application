from functools import wraps

from flask import Blueprint, flash, redirect, session, url_for

from extensions import db
from models import User


auth_bp = Blueprint("auth", __name__)


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
                if (
                    user.status != "active"
                    or not profile
                    or profile.approval_status != "approved"
                ):
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