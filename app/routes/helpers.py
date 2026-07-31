import logging
from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user

from app.models import AuditLog
from app import db

logger = logging.getLogger(__name__)


def role_required(*role_names):
    """Decorator that restricts access to users with specific roles."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not current_user.has_role(*role_names):
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("main.dashboard"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def log_audit(action, entity_type="", entity_id=None, details="",
              user=None, org_id=None, ip=""):
    """Write an audit log entry."""
    try:
        entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            user_id=user.id if user else (
                current_user.id if current_user and current_user.is_authenticated else None
            ),
            organization_id=org_id or (
                current_user.organization_id
                if current_user and current_user.is_authenticated
                else None
            ),
            ip_address=ip,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        logger.exception("Failed to write audit log: %s", exc)
        db.session.rollback()
