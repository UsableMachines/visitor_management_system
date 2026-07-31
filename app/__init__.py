import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)

    # ── Core config ──────────────────────────────────────────────────
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///vms.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ── Session cookie hardening ─────────────────────────────────────
    app.config["SESSION_COOKIE_NAME"] = "visitor_management_system_session"
    app.config["SESSION_COOKIE_PATH"] = os.environ.get("SESSION_COOKIE_PATH", "/")
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get(
        "SESSION_COOKIE_SECURE", "false"
    ).lower() in ("true", "1", "yes")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # ── ProxyFix ─────────────────────────────────────────────────────
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ── Extensions ───────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    migrate.init_app(app, db)
    csrf.init_app(app)

    # ── Blueprints ───────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.visitors import visitors_bp
    from app.routes.hosts import hosts_bp
    from app.routes.watchlist import watchlist_bp
    from app.routes.badges import badges_bp
    from app.routes.audit import audit_bp
    from app.routes.admin import admin_bp
    from app.routes.api import api_bp
    from app.routes.getting_started import getting_started_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(visitors_bp)
    app.register_blueprint(hosts_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(badges_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(getting_started_bp)

    # ── User loader ──────────────────────────────────────────────────
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Create tables + seed ─────────────────────────────────────────
    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()
        _seed_defaults(app)

    return app


def _seed_defaults(app):
    """Create default roles, super-admin user, and a demo organization."""
    from app.models import Role, User, Organization

    if Role.query.first() is not None:
        return

    roles = ["super_admin", "org_admin", "front_desk", "security", "host"]
    for r in roles:
        db.session.add(Role(name=r, description=r.replace("_", " ").title()))
    db.session.commit()

    org = Organization(name="Default Organization", slug="default")
    db.session.add(org)
    db.session.commit()

    super_role = Role.query.filter_by(name="super_admin").first()
    admin = User(
        username="admin",
        email="admin@example.com",
        first_name="System",
        last_name="Admin",
        organization_id=org.id,
        role_id=super_role.id,
        is_active=True,
    )
    admin.set_password("admin")
    db.session.add(admin)
    db.session.commit()
    logger.info("Seeded default org, roles, and admin user.")
