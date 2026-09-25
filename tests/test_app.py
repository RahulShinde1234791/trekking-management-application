import pytest

from app import create_app
from models import User
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