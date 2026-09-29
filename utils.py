from models import StaffProfile, TrekkerProfile

def parse_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

def generate_staff_code():
    last_profile = (
        StaffProfile.query
        .order_by(StaffProfile.id.desc())
        .first()
    )

    next_number = 1 if last_profile is None else last_profile.id + 1

    return f"STF-{next_number:04d}"


def generate_trekker_code():
    last_profile = (
        TrekkerProfile.query
        .order_by(TrekkerProfile.id.desc())
        .first()
    )

    next_number = 1 if last_profile is None else last_profile.id + 1

    return f"TRK-{next_number:04d}"

def update_booking_status(booking, new_status):
    old_status = booking.status

    valid_statuses = {"Booked", "Cancelled", "Completed"}

    if new_status not in valid_statuses:
        return "Invalid booking status.", "danger"

    if old_status == new_status:
        return "Booking status unchanged.", "info"

    # Completed is a terminal state.
    if old_status == "Completed":
        return (
            "Completed bookings cannot be changed.",
            "danger",
        )

    # Cancelled -> Booked
    if old_status == "Cancelled" and new_status == "Booked":
        if booking.trek.status != "Open":
            return (
                "Cancelled bookings can be restored only when the trek is Open.",
                "danger",
            )

        if booking.trek.available_slots <= 0:
            return (
                "Cannot restore booking because the trek is full.",
                "danger",
            )

        booking.trek.available_slots -= 1

    # Booked -> Cancelled
    if old_status == "Booked" and new_status == "Cancelled":
        booking.trek.available_slots += 1

    # Cancelled -> Completed is not allowed.
    if old_status == "Cancelled" and new_status == "Completed":
        return (
            "Cancelled bookings cannot be marked as completed.",
            "danger",
        )

    booking.status = new_status
    return "Booking status updated.", "success"