import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template
from flask_wtf.csrf import CSRFProtect

from auth.routes import auth_bp, get_current_user, redirect_to_dashboard
from admin import admin_bp
from staff import staff_bp
from user.routes import user_bp
from extensions import db

csrf = CSRFProtect()

load_dotenv()

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trekking.db"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    else:
        app.config.update(test_config)

    csrf.init_app(app)
    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(user_bp)

    @app.context_processor
    def inject_current_user():
        return {"current_user": get_current_user()}

    @app.route("/")
    def home():
        if get_current_user():
            return redirect_to_dashboard(get_current_user())
        return render_template("home.html")

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("errors/404.html"), 404


    @app.errorhandler(403)
    def access_forbidden(error):
        return render_template("errors/403.html"), 403


    @app.errorhandler(500)
    def internal_server_error(error):
        return render_template("errors/500.html"), 500

    return app

app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
