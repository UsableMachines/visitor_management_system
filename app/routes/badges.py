import logging

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models import Badge, BadgeStatus, Visit
from app.routes.helpers import role_required, log_audit

logger = logging.getLogger(__name__)
badges_bp = Blueprint("badges", __name__)


@badges_bp.route("/badges")
@login_required
def badge_list():
    try:
        status_filter = request.args.get("status", "").strip()
        query = (
            Badge.query
            .join(Visit)
            .filter(Visit.organization_id == current_user.organization_id)
        )
        if status_filter:
            try:
                status_enum = BadgeStatus(status_filter)
                query = query.filter(Badge.status == status_enum)
            except ValueError:
                pass
        page = request.args.get("page", 1, type=int)
        pagination = query.order_by(Badge.issued_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
    except Exception as exc:
        logger.exception("badge_list: query error — %s", exc)
        pagination = None

    return render_template(
        "badges/list.html",
        pagination=pagination,
        statuses=[s.value for s in BadgeStatus],
        current_status=status_filter,
    )


@badges_bp.route("/badges/<int:badge_id>/report-lost", methods=["POST"])
@login_required
@role_required("super_admin", "org_admin", "front_desk", "security")
def badge_report_lost(badge_id):
    try:
        badge = (
            Badge.query.join(Visit)
            .filter(
                Badge.id == badge_id,
                Visit.organization_id == current_user.organization_id,
            )
            .first()
        )
    except Exception as exc:
        logger.exception("badge_report_lost: query error — %s", exc)
        flash("Failed to update badge.", "danger")
        return redirect(url_for("badges.badge_list"))

    if badge is None:
        flash("Badge not found.", "warning")
        return redirect(url_for("badges.badge_list"))

    try:
        badge.status = BadgeStatus.LOST
        db.session.commit()
        log_audit(
            "badge_lost", "badge", badge.id,
            f"Badge {badge.badge_number} reported lost",
            ip=request.remote_addr,
        )
        flash(f"Badge {badge.badge_number} reported as lost.", "warning")
    except Exception as exc:
        logger.exception("badge_report_lost: save error — %s", exc)
        db.session.rollback()
        flash("Failed to update badge.", "danger")

    return redirect(url_for("badges.badge_list"))
