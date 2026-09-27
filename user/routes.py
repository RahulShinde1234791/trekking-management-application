from flask import Blueprint, flash, redirect, render_template, request, url_for

from auth.routes import get_current_user, is_valid_phone, role_required
from extensions import db
from models import Booking, Trek
from utils import update_booking_status

from . import user_bp

@user_bp.route("/user/dashboard")
@role_required("trekker")
def user_dashboard():
    user = get_current_user()

    open_treks = (
        Trek.query
        .filter_by(status="Open")
        .order_by(Trek.start_date.asc())
        .limit(5)
        .all()
    )

    bookings = (
        Booking.query
        .filter_by(user_id=user.id)
        .order_by(Booking.booking_date.desc())
        .all()
    )

    return render_template(
        "user/dashboard.html",
        open_treks=open_treks,
        bookings=bookings,
    )


@user_bp.route("/user/profile", methods=["GET", "POST"])
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
        return redirect(url_for("user.user_profile"))

    return render_template("user/profile.html", user=user)


@user_bp.route("/user/treks")
@role_required("trekker")
def user_treks():
    difficulty = request.args.get("difficulty", "").strip()
    location = request.args.get("location", "").strip()

    treks_query = Trek.query.filter_by(status="Open")

    if difficulty:
        treks_query = treks_query.filter(Trek.difficulty == difficulty)

    if location:
        treks_query = treks_query.filter(
            Trek.location.ilike(f"%{location}%")
        )

    treks = (
        treks_query
        .order_by(Trek.start_date.asc().nullslast(), Trek.name.asc())
        .all()
    )

    user_bookings = {
        booking.trek_id: booking
        for booking in Booking.query.filter_by(
            user_id=get_current_user().id
        ).all()
        if booking.status in ["Booked", "Completed"]
    }

    return render_template(
        "user/treks.html",
        treks=treks,
        difficulty=difficulty,
        location=location,
        user_bookings=user_bookings,
    )


@user_bp.route("/user/treks/<int:trek_id>/book", methods=["POST"])
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
        return redirect(url_for("user.user_treks"))

    if trek.status != "Open":
        flash("This trek is not open for booking.", "danger")
        return redirect(url_for("user.user_treks"))

    if trek.available_slots <= 0:
        flash("This trek is full.", "danger")
        return redirect(url_for("user.user_treks"))

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
    return redirect(url_for("user.user_history"))


@user_bp.route("/user/history")
@role_required("trekker")
def user_history():
    bookings = (
        Booking.query
        .filter_by(user_id=get_current_user().id)
        .order_by(Booking.booking_date.desc())
        .all()
    )

    return render_template("user/history.html", bookings=bookings)


@user_bp.route(
    "/user/bookings/<int:booking_id>/cancel",
    methods=["POST"],
)
@role_required("trekker")
def cancel_booking(booking_id):
    booking = Booking.query.filter_by(
        id=booking_id,
        user_id=get_current_user().id,
    ).first_or_404()

    if booking.status != "Booked":
        flash("Only booked treks can be cancelled.", "warning")
        return redirect(url_for("user.user_history"))

    message, category = update_booking_status(booking, "Cancelled")
    db.session.commit()

    flash(message, category)
    return redirect(url_for("user.user_history"))