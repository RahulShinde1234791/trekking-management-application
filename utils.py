def parse_int(value, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

def update_booking_status(booking, new_status):
    old_status = booking.status

    if old_status == new_status:
        return "Booking status unchanged.", "info"

    if new_status == "Booked" and old_status == "Cancelled":
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

    if new_status == "Cancelled" and old_status == "Booked":
        booking.trek.available_slots += 1

    booking.status = new_status
    return "Booking status updated.", "success"