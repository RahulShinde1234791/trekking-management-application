from flask import Blueprint, flash, redirect, render_template, request, url_for

from auth.routes import get_current_user, is_valid_phone, role_required
from extensions import db
from models import Trek, Booking
from utils import update_booking_status
from . import staff_bp

def get_assigned_trek_or_404(trek_id):
    staff = get_current_user()
    return Trek.query.filter_by(
        id=trek_id,
        assigned_staff_id=staff.id
    ).first_or_404()

def complete_booked_participants(trek):
    for booking in trek.bookings:
        if booking.status == "Booked":
            booking.status = "Completed"

@staff_bp.route("/staff/dashboard")
@role_required("staff")
def staff_dashboard():
    staff = get_current_user()

    treks = (
        Trek.query
        .filter_by(assigned_staff_id=staff.id)
        .order_by(Trek.start_date.asc())
        .all()
    )

    return render_template("staff/dashboard.html", treks=treks)

@staff_bp.route("/staff/profile", methods=["GET", "POST"])
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
            profile.contact_details = request.form.get(
                "contact_details", ""
            ).strip()
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
        return redirect(url_for("staff.staff_profile"))

    return render_template("staff/profile.html", staff=staff)

@staff_bp.route("/staff/treks/<int:trek_id>")
@role_required("staff")
def staff_trek_detail(trek_id):
    trek = get_assigned_trek_or_404(trek_id)
    return render_template("staff/trek_detail.html", trek=trek)

@staff_bp.route("/staff/treks/<int:trek_id>/update", methods=["POST"])
@role_required("staff")
def update_staff_trek(trek_id):
    trek = get_assigned_trek_or_404(trek_id)

    try:
        available_slots = int(request.form.get("available_slots", "0"))
    except ValueError:
        flash("Available slots must be a number.", "danger")
        return redirect(
            url_for("staff.staff_trek_detail", trek_id=trek.id)
        )

    status = request.form.get("status", "").strip()

    if status not in ["Open", "Closed", "Ongoing", "Completed"]:
        flash(
            "Staff can update trek status only to Open, Closed, Ongoing, or Completed.",
            "danger",
        )
        return redirect(
            url_for("staff.staff_trek_detail", trek_id=trek.id)
        )

    if available_slots < 0:
        flash("Available slots cannot be negative.", "danger")
        return redirect(
            url_for("staff.staff_trek_detail", trek_id=trek.id)
        )

    trek.available_slots = available_slots
    trek.status = status

    if status == "Completed":
        complete_booked_participants(trek)

    db.session.commit()

    flash("Trek details updated.", "success")
    return redirect(
        url_for("staff.staff_trek_detail", trek_id=trek.id)
    )

@staff_bp.route("/staff/bookings/<int:booking_id>/status", methods=["POST"])
@role_required("staff")
def update_participant_status(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    get_assigned_trek_or_404(booking.trek_id)

    status = request.form.get("status", "").strip()

    if status not in ["Booked", "Cancelled", "Completed"]:
        flash("Invalid booking status.", "danger")
        return redirect(
            url_for("staff.staff_trek_detail", trek_id=booking.trek_id)
        )

    message, category = update_booking_status(booking, status)

    db.session.commit()

    flash(message, category)
    return redirect(
        url_for("staff.staff_trek_detail", trek_id=booking.trek_id)
    )