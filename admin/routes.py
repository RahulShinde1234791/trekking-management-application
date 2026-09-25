from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth.routes import role_required
from constants import DIFFICULTIES, TREK_STATUSES
from extensions import db
from models import Booking, StaffProfile, Trek, User
from utils import parse_int

from . import admin_bp


@admin_bp.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    stats = {
        "treks": Trek.query.count(),
        "trekkers": User.query.filter_by(role="trekker").count(),
        "staff": User.query.filter_by(role="staff").count(),
        "bookings": Booking.query.count(),
    }

    recent_bookings = (
        Booking.query
        .order_by(Booking.booking_date.desc())
        .limit(5)
        .all()
    )

    pending_staff = (
        User.query
        .filter_by(role="staff", status="pending")
        .order_by(User.created_at.desc())
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_bookings=recent_bookings,
        pending_staff=pending_staff,
    )


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
            status="active"
        ).first()

        if (
            not staff
            or not staff.staff_profile
            or staff.staff_profile.approval_status != "approved"
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


@admin_bp.route("/admin/treks")
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

    treks = (
        treks_query
        .order_by(Trek.start_date.asc().nullslast(), Trek.name.asc())
        .all()
    )

    staff_members = get_approved_staff()

    return render_template(
        "admin/treks.html",
        treks=treks,
        staff_members=staff_members,
        query=query,
    )


@admin_bp.route("/admin/treks/create", methods=["GET", "POST"])
@role_required("admin")
def create_trek():
    staff_members = get_approved_staff()

    if request.method == "POST":
        trek = build_trek_from_form(Trek())

        if trek is None:
            return render_template(
                "admin/trek_form.html",
                trek=None,
                staff_members=staff_members,
            )

        db.session.add(trek)
        db.session.commit()

        flash("Trek created successfully.", "success")
        return redirect(url_for("admin.admin_treks"))

    return render_template(
        "admin/trek_form.html",
        trek=None,
        staff_members=staff_members,
    )


@admin_bp.route("/admin/treks/<int:trek_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    staff_members = get_approved_staff()

    if request.method == "POST":
        updated_trek = build_trek_from_form(trek)

        if updated_trek is None:
            return render_template(
                "admin/trek_form.html",
                trek=trek,
                staff_members=staff_members,
            )

        db.session.commit()
        flash("Trek updated successfully.", "success")
        return redirect(url_for("admin.admin_treks"))

    return render_template(
        "admin/trek_form.html",
        trek=trek,
        staff_members=staff_members,
    )

@admin_bp.route("/admin/treks/<int:trek_id>/delete", methods=["POST"])
@role_required("admin")
def delete_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    db.session.delete(trek)
    db.session.commit()
    flash("Trek removed successfully.", "info")
    return redirect(url_for("admin.admin_treks"))

@admin_bp.route("/admin/treks/<int:trek_id>/assign", methods=["POST"])
@role_required("admin")
def assign_staff(trek_id):
    trek = Trek.query.get_or_404(trek_id)

    staff_id = parse_int(
        request.form.get("assigned_staff_id"),
        fallback=None,
    )

    if staff_id is None:
        trek.assigned_staff_id = None
    else:
        staff = User.query.filter_by(
            id=staff_id,
            role="staff",
            status="active",
        ).first()

        if not staff:
            flash("Please select an approved staff member.", "danger")
            return redirect(url_for("admin.admin_treks"))

        trek.assigned_staff_id = staff.id

    db.session.commit()

    flash("Staff assignment updated.", "success")
    return redirect(url_for("admin.admin_treks"))