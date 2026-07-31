import logging

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.models import AuditLog
from app.routes.helpers import role_required

logger = logging.getLogger(__name__)
audit_bp = Blueprint("audit", __name__)


@audit_bp.route("/audit")
@login_required
@role_required("super_admin", "org_admin", "security")
def audit_list():
    try:
        action_filter = request.args.get("action", "").strip()
        query = AuditLog.query.filter_by(
            organization_id=current_user.organization_id
        )
        if action_filter:
            query = query.filter(AuditLog.action == action_filter)

        page = request.args.get("page", 1, type=int)
        pagination = query.order_by(AuditLog.created_at.desc()).paginate(
            page=page, per_page=30, error_out=False
        )

        actions = (
            db.session.query(AuditLog.action)
            .filter_by(organization_id=current_user.organization_id)
            .distinct()
            .all()
        )
        action_list = sorted([a[0] for a in actions])
    except Exception as exc:
        logger.exception("audit_list: query error — %s", exc)
        pagination = None
        action_list = []

    from app import db  # noqa: already imported above via models
    return render_template(
        "audit/list.html",
        pagination=pagination,
        actions=action_list,
        current_action=action_filter,
    )
