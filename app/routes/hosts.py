import logging

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user

from app.models import User

logger = logging.getLogger(__name__)
hosts_bp = Blueprint("hosts", __name__)


@hosts_bp.route("/hosts")
@login_required
def host_list():
    try:
        search = request.args.get("q", "").strip()
        query = User.query.filter_by(
            organization_id=current_user.organization_id, is_active=True
        )
        if search:
            like = f"%{search}%"
            query = query.filter(
                (User.first_name.ilike(like))
                | (User.last_name.ilike(like))
                | (User.email.ilike(like))
                | (User.department.ilike(like))
            )
        page = request.args.get("page", 1, type=int)
        pagination = query.order_by(User.last_name).paginate(
            page=page, per_page=20, error_out=False
        )
    except Exception as exc:
        logger.exception("host_list: query error — %s", exc)
        pagination = None

    return render_template("hosts/list.html", pagination=pagination, search=request.args.get("q", ""))
