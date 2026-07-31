import logging
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import Visit, Visitor, VisitStatus, HostNotification

logger = logging.getLogger(__name__)
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return render_template("main/dashboard.html")
    return render_template("main/landing.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    try:
        org_id = current_user.organization_id
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        total_today = Visit.query.filter(
            Visit.organization_id == org_id,
            Visit.created_at >= today_start,
        ).count()
        checked_in = Visit.query.filter(
            Visit.organization_id == org_id,
            Visit.status == VisitStatus.CHECKED_IN,
        ).count()
        pre_registered = Visit.query.filter(
            Visit.organization_id == org_id,
            Visit.status == VisitStatus.PRE_REGISTERED,
        ).count()
        denied = Visit.query.filter(
            Visit.organization_id == org_id,
            Visit.status == VisitStatus.DENIED,
            Visit.created_at >= today_start,
        ).count()
        recent_visits = (
            Visit.query.filter_by(organization_id=org_id)
            .order_by(Visit.created_at.desc())
            .limit(10)
            .all()
        )
        total_visitors = Visitor.query.filter_by(organization_id=org_id).count()
    except Exception as exc:
        logger.exception("dashboard: query error — %s", exc)
        total_today = checked_in = pre_registered = denied = total_visitors = 0
        recent_visits = []

    return render_template(
        "main/dashboard.html",
        total_today=total_today,
        checked_in=checked_in,
        pre_registered=pre_registered,
        denied=denied,
        recent_visits=recent_visits,
        total_visitors=total_visitors,
    )


@main_bp.route("/notifications")
@login_required
def notifications():
    try:
        notifs = (
            HostNotification.query.filter_by(host_id=current_user.id)
            .order_by(HostNotification.created_at.desc())
            .limit(50)
            .all()
        )
    except Exception as exc:
        logger.exception("notifications: query error — %s", exc)
        notifs = []

    return render_template("main/notifications.html", notifications=notifs)


@main_bp.route("/api/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    try:
        HostNotification.query.filter_by(
            host_id=current_user.id, is_read=False
        ).update({"is_read": True})
        db.session.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        logger.exception("mark_notifications_read: error — %s", exc)
        db.session.rollback()
        return jsonify({"error": "Failed to mark notifications read"}), 500


@main_bp.route("/api/notifications/count")
@login_required
def notification_count():
    try:
        count = HostNotification.query.filter_by(
            host_id=current_user.id, is_read=False
        ).count()
        return jsonify({"count": count})
    except Exception as exc:
        logger.exception("notification_count: error — %s", exc)
        return jsonify({"count": 0})


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        try:
            current_user.first_name = request.form.get("first_name", "").strip()
            current_user.last_name = request.form.get("last_name", "").strip()
            current_user.phone = request.form.get("phone", "").strip()
            current_user.department = request.form.get("department", "").strip()
            db.session.commit()
            from flask import flash
            flash("Profile updated.", "success")
        except Exception as exc:
            logger.exception("profile: update error — %s", exc)
            db.session.rollback()
            from flask import flash
            flash("Failed to update profile.", "danger")
    return render_template("main/profile.html")


@main_bp.route("/toggle-theme", methods=["POST"])
@login_required
def toggle_theme():
    try:
        new_theme = request.json.get("theme", "light")
        if new_theme not in ("light", "dark"):
            new_theme = "light"
        current_user.theme = new_theme
        db.session.commit()
        return jsonify({"ok": True, "theme": new_theme})
    except Exception as exc:
        logger.exception("toggle_theme: error — %s", exc)
        db.session.rollback()
        return jsonify({"error": "Failed"}), 500
