import pytest

from app import create_app
from models import User, Trek, Booking
from werkzeug.security import generate_password_hash
from extensions import db


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