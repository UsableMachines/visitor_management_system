import logging

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models import WatchlistEntry
from app.routes.helpers import role_required, log_audit

logger = logging.getLogger(__name__)
watchlist_bp = Blueprint("watchlist", __name__)


@watchlist_bp.route("/watchlist")
@login_required
@role_required("super_admin", "org_admin", "security")
def watchlist_list():
    try:
        search = request.args.get("q", "").strip()
        query = WatchlistEntry.query.filter_by(
            organization_id=current_user.organization_id
        )
        if search:
            like = f"%{search}%"
            query = query.filter(
                (WatchlistEntry.first_name.ilike(like))
                | (WatchlistEntry.last_name.ilike(like))
                | (WatchlistEntry.reason.ilike(like))
            )
        page = request.args.get("page", 1, type=int)
        pagination = query.order_by(WatchlistEntry.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
    except Exception as exc:
        logger.exception("watchlist_list: query error — %s", exc)
        pagination = None

    return render_template(
        "watchlist/list.html", pagination=pagination, search=request.args.get("q", "")
    )


@watchlist_bp.route("/watchlist/new", methods=["GET", "POST"])
@login_required
@role_required("super_admin", "org_admin", "security")
def watchlist_new():
    if request.method == "POST":
        try:
            entry = WatchlistEntry(
                first_name=request.form.get("first_name", "").strip(),
                last_name=request.form.get("last_name", "").strip(),
                email=request.form.get("email", "").strip(),
                id_number=request.form.get("id_number", "").strip(),
                reason=request.form.get("reason", "").strip(),
                severity=request.form.get("severity", "high"),
                organization_id=current_user.organization_id,
                created_by_id=current_user.id,
            )
            db.session.add(entry)
            db.session.commit()
            log_audit(
                "watchlist_add", "watchlist", entry.id,
                f"Added {entry.first_name} {entry.last_name}",
                ip=request.remote_addr,
            )
            flash("Watchlist entry added.", "success")
            return redirect(url_for("watchlist.watchlist_list"))
        except Exception as exc:
            logger.exception("watchlist_new: save error — %s", exc)
            db.session.rollback()
            flash("Failed to add watchlist entry.", "danger")

    return render_template("watchlist/new.html")


@watchlist_bp.route("/watchlist/<int:entry_id>/toggle", methods=["POST"])
@login_required
@role_required("super_admin", "org_admin", "security")
def watchlist_toggle(entry_id):
    try:
        entry = WatchlistEntry.query.filter_by(
            id=entry_id, organization_id=current_user.organization_id
        ).first()
    except Exception as exc:
        logger.exception("watchlist_toggle: query error — %s", exc)
        flash("Failed to update entry.", "danger")
        return redirect(url_for("watchlist.watchlist_list"))

    if entry is None:
        flash("Entry not found.", "warning")
        return redirect(url_for("watchlist.watchlist_list"))

    try:
        entry.is_active = not entry.is_active
        db.session.commit()
        status = "activated" if entry.is_active else "deactivated"
        log_audit(
            f"watchlist_{status}", "watchlist", entry.id,
            f"{status.title()} {entry.first_name} {entry.last_name}",
            ip=request.remote_addr,
        )
        flash(f"Entry {status}.", "success")
    except Exception as exc:
        logger.exception("watchlist_toggle: save error — %s", exc)
        db.session.rollback()
        flash("Failed to update entry.", "danger")

    return redirect(url_for("watchlist.watchlist_list"))
