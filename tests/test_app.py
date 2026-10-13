import pytest

from app import create_app
from models import User, Trek, Booking
from werkzeug.security import generate_password_hash
from extensions import db
from utils import update_booking_status

@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
    })

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_404_page(client):
    response = client.get("/this-page-does-not-exist")

    assert response.status_code == 404
    assert b"Page Not Found" in response.data

def test_403_page(client, app):
    @app.route("/test-forbidden")
    def test_forbidden():
        from flask import abort
        abort(403)

    response = client.get("/test-forbidden")

    assert response.status_code == 403
    assert b"Access Forbidden" in response.data


def test_500_page(client, app):
    @app.route("/test-server-error")
    def test_server_error():
        raise RuntimeError("Intentional test error")

    app.config["PROPAGATE_EXCEPTIONS"] = False

    response = client.get("/test-server-error")

    assert response.status_code == 500
    assert b"Something Went Wrong" in response.data

def test_user_registration_hashes_password(client, app):
    response = client.post(
        "/register/user",
        data={
            "name": "Test User",
            "email": "testuser@example.com",
            "phone": "9876543210",
            "password": "testpassword123",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        user = User.query.filter_by(email="testuser@example.com").first()

        assert user is not None
        assert user.password_hash != "testpassword123"

def test_user_can_login_with_correct_password(client, app):
    with app.app_context():
        user = User(
            name="Login Test",
            email="login@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="active",
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    response = client.post(
        "/login",
        data={
            "email": "login@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 302

    with client.session_transaction() as session:
        assert session["user_id"] == user_id

def test_user_cannot_login_with_wrong_password(client, app):
    with app.app_context():
        user = User(
            name="Login Test",
            email="wrong-password@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="active",
        )
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/login",
        data={
            "email": "wrong-password@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as session:
        assert "user_id" not in session

def test_blacklisted_user_cannot_login(client, app):
    with app.app_context():
        user = User(
            name="Blacklisted User",
            email="blacklisted@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="blacklisted",
        )
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/login",
        data={
            "email": "blacklisted@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as session:
        assert "user_id" not in session


def test_deactivated_user_cannot_login(client, app):
    with app.app_context():
        user = User(
            name="Deactivated User",
            email="deactivated@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="deactivated",
        )
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/login",
        data={
            "email": "deactivated@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200

    with client.session_transaction() as session:
        assert "user_id" not in session

def test_admin_can_deactivate_trekker(client, app):
    # Create separate test accounts in the in-memory database.
    with app.app_context():
        admin = User(
            name="Test Admin",
            email="testadmin@example.com",
            password_hash=generate_password_hash("adminpassword"),
            role="admin",
            status="active",
        )
        trekker = User(
            name="Test Trekker",
            email="testtrekker@example.com",
            password_hash=generate_password_hash("trekkerpassword"),
            role="trekker",
            status="active",
        )

        db.session.add_all([admin, trekker])
        db.session.commit()

        admin_id = admin.id
        trekker_id = trekker.id

    # Simulate an authenticated admin session.
    with client.session_transaction() as session:
        session["user_id"] = admin_id

    # Request deactivation through the actual admin route.
    response = client.post(
        f"/admin/users/{trekker_id}/deactivate",
        follow_redirects=False,
    )

    assert response.status_code == 302

    # Confirm that the trekker was deactivated.
    with app.app_context():
        trekker = db.session.get(User, trekker_id)

        assert trekker is not None
        assert trekker.status == "deactivated"


def test_admin_cannot_reactivate_deactivated_trekker(client, app):
    with app.app_context():
        admin = User(
            name="Test Admin",
            email="reactivation-admin@example.com",
            password_hash=generate_password_hash("adminpassword"),
            role="admin",
            status="active",
        )
        trekker = User(
            name="Deactivated Trekker",
            email="permanent-test@example.com",
            password_hash=generate_password_hash("trekkerpassword"),
            role="trekker",
            status="deactivated",
        )

        db.session.add_all([admin, trekker])
        db.session.commit()

        admin_id = admin.id
        trekker_id = trekker.id

    with client.session_transaction() as session:
        session["user_id"] = admin_id

    response = client.post(
        f"/admin/users/{trekker_id}/activate",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        trekker = db.session.get(User, trekker_id)

        assert trekker is not None
        assert trekker.status == "deactivated"


def test_deactivating_trekker_preserves_booking_history(client, app):
    with app.app_context():
        admin = User(
            name="Test Admin",
            email="history-admin@example.com",
            password_hash=generate_password_hash("adminpassword"),
            role="admin",
            status="active",
        )

        trekker = User(
            name="History Test Trekker",
            email="history-trekker@example.com",
            password_hash=generate_password_hash("trekkerpassword"),
            role="trekker",
            status="active",
        )

        trek = Trek(
            name="History Test Trek",
            location="Test Location",
            difficulty="Easy",
            duration_days=2,
            available_slots=5,
            status="Open",
        )

        db.session.add_all([admin, trekker, trek])
        db.session.flush()

        booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Booked",
            payment_status="Paid",
        )
        db.session.add(booking)
        db.session.commit()

        admin_id = admin.id
        trekker_id = trekker.id
        booking_id = booking.id

    # Authenticate as the temporary admin.
    with client.session_transaction() as session:
        session["user_id"] = admin_id

    # Deactivate the trekker.
    response = client.post(
        f"/admin/users/{trekker_id}/deactivate",
        follow_redirects=False,
    )

    assert response.status_code == 302

    # Verify that the account and booking still exist.
    with app.app_context():
        trekker = db.session.get(User, trekker_id)
        booking = db.session.get(Booking, booking_id)

        assert trekker is not None
        assert trekker.status == "deactivated"

        assert booking is not None
        assert booking.user_id == trekker_id
        assert booking.status == "Booked"
        assert booking.payment_status == "Paid"


def test_admin_cannot_blacklist_deactivated_staff(client, app):
    with app.app_context():
        admin = User(
            name="Test Admin",
            email="staff-guard-admin@example.com",
            password_hash=generate_password_hash("adminpassword"),
            role="admin",
            status="active",
        )

        staff = User(
            name="Deactivated Staff",
            email="deactivated-staff@example.com",
            password_hash=generate_password_hash("staffpassword"),
            role="staff",
            status="deactivated",
        )

        db.session.add_all([admin, staff])
        db.session.commit()

        admin_id = admin.id
        staff_id = staff.id

    with client.session_transaction() as session:
        session["user_id"] = admin_id

    response = client.post(
        f"/admin/staff/{staff_id}/blacklist",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        staff = db.session.get(User, staff_id)

        assert staff is not None
        assert staff.status == "deactivated"

def test_completed_booking_does_not_prevent_new_booking(app):
    with app.app_context():
        trekker = User(
            name="Rebooking Test",
            email="rebooking@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="active",
        )

        trek = Trek(
            name="Rebooking Test Trek",
            location="Test Location",
            difficulty="Easy",
            duration_days=2,
            available_slots=5,
            status="Open",
        )

        db.session.add_all([trekker, trek])
        db.session.flush()

        completed_booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Completed",
            payment_status="Paid",
        )

        db.session.add(completed_booking)
        db.session.commit()

        new_booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Booked",
            payment_status="Pending",
        )

        db.session.add(new_booking)
        db.session.commit()

        bookings = Booking.query.filter_by(
            user_id=trekker.id,
            trek_id=trek.id,
        ).all()

        assert len(bookings) == 2
        assert {booking.status for booking in bookings} == {
            "Completed",
            "Booked",
        }

def test_duplicate_active_booking_is_rejected(app):
    with app.app_context():
        trekker = User(
            name="Duplicate Test",
            email="duplicate@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="active",
        )

        trek = Trek(
            name="Duplicate Test Trek",
            location="Test Location",
            difficulty="Easy",
            duration_days=2,
            available_slots=5,
            status="Open",
        )

        db.session.add_all([trekker, trek])
        db.session.flush()

        first_booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Booked",
            payment_status="Pending",
        )

        db.session.add(first_booking)
        db.session.commit()

        duplicate_booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Booked",
            payment_status="Pending",
        )

        db.session.add(duplicate_booking)

        with pytest.raises(Exception):
            db.session.commit()

        db.session.rollback()

        bookings = Booking.query.filter_by(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Booked",
        ).all()

        assert len(bookings) == 1

def test_completed_booking_status_cannot_be_changed(app):
    with app.app_context():
        trekker = User(
            name="Completed Test",
            email="completed@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="active",
        )

        trek = Trek(
            name="Completed Test Trek",
            location="Test Location",
            difficulty="Easy",
            duration_days=2,
            available_slots=5,
            status="Open",
        )

        db.session.add_all([trekker, trek])
        db.session.flush()

        booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Completed",
            payment_status="Paid",
        )

        db.session.add(booking)
        db.session.commit()

        message, category = update_booking_status(booking, "Cancelled")

        assert message == "Completed bookings cannot be changed."
        assert category == "danger"
        assert booking.status == "Completed"

def test_booking_status_transitions_update_slots_correctly(app):
    with app.app_context():
        trekker = User(
            name="Slot Test",
            email="slots@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="active",
        )

        trek = Trek(
            name="Slot Test Trek",
            location="Test Location",
            difficulty="Easy",
            duration_days=2,
            available_slots=4,
            status="Open",
        )

        db.session.add_all([trekker, trek])
        db.session.flush()

        booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Booked",
            payment_status="Pending",
        )

        db.session.add(booking)
        db.session.commit()

        message, category = update_booking_status(booking, "Cancelled")
        assert category == "success"
        assert booking.status == "Cancelled"
        assert trek.available_slots == 5

        message, category = update_booking_status(booking, "Booked")
        assert category == "success"
        assert booking.status == "Booked"
        assert trek.available_slots == 4

        message, category = update_booking_status(booking, "Completed")
        assert category == "success"
        assert booking.status == "Completed"
        assert trek.available_slots == 4

def test_cancelled_booking_allows_new_booking_through_route(client, app):
    with app.app_context():
        trekker = User(
            name="Route Rebooking Test",
            email="route-rebooking@example.com",
            password_hash=generate_password_hash("password123"),
            role="trekker",
            status="active",
        )

        trek = Trek(
            name="Route Rebooking Trek",
            location="Test Location",
            difficulty="Easy",
            duration_days=2,
            available_slots=4,
            status="Open",
        )

        db.session.add_all([trekker, trek])
        db.session.flush()

        previous_booking = Booking(
            user_id=trekker.id,
            trek_id=trek.id,
            status="Cancelled",
            payment_status="Pending",
        )

        db.session.add(previous_booking)
        db.session.commit()

        trekker_id = trekker.id
        trek_id = trek.id

    with client.session_transaction() as session:
        session["user_id"] = trekker_id

    response = client.post(
        f"/user/treks/{trek_id}/book",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        bookings = Booking.query.filter_by(
            user_id=trekker_id,
            trek_id=trek_id,
        ).all()

        trek = db.session.get(Trek, trek_id)

        assert len(bookings) == 2
        assert {booking.status for booking in bookings} == {
            "Cancelled",
            "Booked",
        }
        assert trek.available_slots == 3