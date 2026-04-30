import os

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from .database import db
from .routes import accounts, auth, providers, rate_cards, sessions, usage, users


def create_app(config=None):
    app = Flask(__name__)

    # 預設使用 SQLite，可透過環境變數覆蓋
    app.config.setdefault(
        "SQLALCHEMY_DATABASE_URI",
        os.environ.get("DATABASE_URL", "sqlite:///everywifi.db"),
    )
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)

    if config:
        app.config.update(config)

    db.init_app(app)

    app.register_blueprint(users.bp)
    app.register_blueprint(accounts.bp)
    app.register_blueprint(rate_cards.bp)
    app.register_blueprint(providers.bp)
    app.register_blueprint(sessions.bp)
    app.register_blueprint(usage.bp)
    app.register_blueprint(auth.bp)

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        return jsonify({"error": e.name, "message": e.description}), e.code

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    app = create_app()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=5000)
