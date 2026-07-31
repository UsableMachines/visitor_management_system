import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import (
    Visitor, Visit, VisitStatus, WatchlistEntry, WatchlistMatchLevel,
    HostNotification, User, Badge, BadgeStatus,
)
from app.routes.helpers import log_audit, role_required

logger = logging.getLogger(__name__)
visitors_bp = Blueprint("visitors", __name__)


def _screen_watchlist(visitor, org_id):
    """Check visitor against watchlist. Returns (match_level, details)."""
    try:
        entries = WatchlistEntry.query.filter_by(
            organization_id=org_id, is_active=True
        ).all()
    except Exception as exc:
        logger.exception("_screen_watchlist: query error — %s", exc)
        return WatchlistMatchLevel.NONE, ""

    v_first = visitor.first_name.lower().strip()
    v_last = visitor.last_name.lower().strip()
    v_email = (visitor.email or "").lower().strip()
    v_id = (visitor.id_number or "").lower().strip()

    best_match = WatchlistMatchLevel.NONE
    details_parts = []

    for entry in entries:
        e_first = entry.first_name.lower().strip()
        e_last = entry.last_name.lower().strip()
        e_email = (entry.email or "").lower().strip()
        e_id = (entry.id_number or "").lower().strip()

        if v_first == e_first and v_last == e_last:
            if v_id and e_id and v_id == e_id:
                return WatchlistMatchLevel.EXACT, (
                    f"Exact match: {entry.first_name} {entry.last_name} — {entry.reason}"
                )
            best_match = WatchlistMatchLevel.HIGH
            details_parts.append(
                f"Name match: {entry.first_name} {entry.last_name} — {entry.reason}"
            )
        elif v_last == e_last:
            if best_match.value < WatchlistMatchLevel.MEDIUM.value:
                best_match = WatchlistMatchLevel.MEDIUM
            details_parts.append(
                f"Last name match: {entry.last_name} — {entry.reason}"
            )
        elif v_email and e_email and v_email == e_email:
            if best_match.value < WatchlistMatchLevel.MEDIUM.value:
                best_match = WatchlistMatchLevel.MEDIUM
            details_parts.append(f"Email match: {entry.email} — {entry.reason}")

    return best_match, "; ".join(details_parts[:3])


@visitors_bp.route("/visitors")
@login_required
def visitor_list():
    try:
        search = request.args.get("q", "").strip()
        query = Visitor.query.filter_by(organization_id=current_user.organization_id)
        if search:
            like = f"%{search}%"
            query = query.filter(
                (Visitor.first_name.ilike(like))
                | (Visitor.last_name.ilike(like))
                | (Visitor.email.ilike(like))
                | (Visitor.company.ilike(like))
            )
        page = request.args.get("page", 1, type=int)
        pagination = query.order_by(Visitor.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
    except Exception as exc:
        logger.exception("visitor_list: query error — %s", exc)
        flash("Failed to load visitors.", "danger")
        return render_template("visitors/list.html", pagination=None, search="")

    return render_template(
        "visitors/list.html", pagination=pagination, search=search
    )


@visitors_bp.route("/visitors/new", methods=["GET", "POST"])
@login_required
def visitor_new():
    if not current_user.can_manage_visitors():
        flash("You do not have permission to register visitors.", "danger")
        return redirect(url_for("visitors.visitor_list"))

    try:
        hosts = User.query.filter_by(
            organization_id=current_user.organization_id, is_active=True
        ).all()
    except Exception as exc:
        logger.exception("visitor_new: host query error — %s", exc)
        hosts = []

    if request.method == "POST":
        try:
            visitor = Visitor(
                first_name=request.form.get("first_name", "").strip(),
                last_name=request.form.get("last_name", "").strip(),
                email=request.form.get("email", "").strip(),
                phone=request.form.get("phone", "").strip(),
                company=request.form.get("company", "").strip(),
                id_type=request.form.get("id_type", "").strip(),
                id_number=request.form.get("id_number", "").strip(),
                notes=request.form.get("notes", "").strip(),
                organization_id=current_user.organization_id,
            )
            db.session.add(visitor)
            db.session.flush()

            host_id = request.form.get("host_id", type=int)
            purpose = request.form.get("purpose", "").strip()
            expected = request.form.get("expected_arrival", "").strip()

            match_level, match_details = _screen_watchlist(
                visitor, current_user.organization_id
            )

            visit = Visit(
                visitor_id=visitor.id,
                host_id=host_id or current_user.id,
                organization_id=current_user.organization_id,
                purpose=purpose,
                status=VisitStatus.PRE_REGISTERED,
                expected_arrival=(
                    datetime.fromisoformat(expected) if expected else None
                ),
                watchlist_match_level=match_level,
                watchlist_details=match_details,
            )
            db.session.add(visit)
            db.session.flush()

            # Notify host
            if host_id:
                notif = HostNotification(
                    visit_id=visit.id,
                    host_id=host_id,
                    message=(
                        f"Visitor {visitor.full_name} from {visitor.company or 'N/A'} "
                        f"has been pre-registered for your visit. Purpose: {purpose or 'N/A'}."
                    ),
                )
                db.session.add(notif)

            db.session.commit()
            log_audit(
                "visitor_registered", "visitor", visitor.id,
                f"Registered {visitor.full_name}",
                ip=request.remote_addr,
            )

            if match_level in (WatchlistMatchLevel.HIGH, WatchlistMatchLevel.EXACT):
                flash(
                    f"⚠ Watchlist alert: {match_level.value} match detected — {match_details}",
                    "danger",
                )

            flash("Visitor registered successfully.", "success")
            return redirect(url_for("visitors.visit_detail", visit_id=visit.id))

        except Exception as exc:
            logger.exception("visitor_new: save error — %s", exc)
            db.session.rollback()
            flash("Failed to register visitor.", "danger")

    return render_template("visitors/new.html", hosts=hosts)


@visitors_bp.route("/visits")
@login_required
def visit_list():
    try:
        status_filter = request.args.get("status", "").strip()
        query = Visit.query.filter_by(organization_id=current_user.organization_id)
        if status_filter:
            try:
                status_enum = VisitStatus(status_filter)
                query = query.filter(Visit.status == status_enum)
            except ValueError:
                pass
        page = request.args.get("page", 1, type=int)
        pagination = query.order_by(Visit.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
    except Exception as exc:
        logger.exception("visit_list: query error — %s", exc)
        flash("Failed to load visits.", "danger")
        return render_template("visitors/visits.html", pagination=None, statuses=[])

    return render_template(
        "visitors/visits.html",
        pagination=pagination,
        statuses=[s.value for s in VisitStatus],
        current_status=status_filter,
    )


@visitors_bp.route("/visits/<int:visit_id>")
@login_required
def visit_detail(visit_id):
    try:
        visit = Visit.query.filter_by(
            id=visit_id, organization_id=current_user.organization_id
        ).first()
    except Exception as exc:
        logger.exception("visit_detail: query error — %s", exc)
        flash("Failed to load visit.", "danger")
        return redirect(url_for("visitors.visit_list"))

    if visit is None:
        flash("Visit not found.", "warning")
        return redirect(url_for("visitors.visit_list"))

    return render_template("visitors/detail.html", visit=visit)


@visitors_bp.route("/visits/<int:visit_id>/checkin", methods=["POST"])
@login_required
def visit_checkin(visit_id):
    if not current_user.can_manage_visitors():
        flash("Permission denied.", "danger")
        return redirect(url_for("visitors.visit_list"))

    try:
        visit = Visit.query.filter_by(
            id=visit_id, organization_id=current_user.organization_id
        ).first()
    except Exception as exc:
        logger.exception("visit_checkin: query error — %s", exc)
        flash("Failed to load visit.", "danger")
        return redirect(url_for("visitors.visit_list"))

    if visit is None:
        flash("Visit not found.", "warning")
        return redirect(url_for("visitors.visit_list"))

    if visit.watchlist_match_level in (WatchlistMatchLevel.HIGH, WatchlistMatchLevel.EXACT):
        flash("Cannot check in — visitor has a high/exact watchlist match. Review required.", "danger")
        return redirect(url_for("visitors.visit_detail", visit_id=visit.id))

    try:
        visit.status = VisitStatus.CHECKED_IN
        visit.checked_in_at = datetime.now(timezone.utc)

        # Issue badge
        badge_number = f"V-{uuid.uuid4().hex[:6].upper()}"
        badge = Badge(
            badge_number=badge_number,
            visit_id=visit.id,
            status=BadgeStatus.ACTIVE,
        )
        db.session.add(badge)

        # Notify host
        notif = HostNotification(
            visit_id=visit.id,
            host_id=visit.host_id,
            message=f"Your visitor {visit.visitor.full_name} has checked in. Badge: {badge_number}.",
        )
        db.session.add(notif)

        db.session.commit()
        log_audit("visitor_checkin", "visit", visit.id,
                  f"Checked in {visit.visitor.full_name}, badge {badge_number}",
                  ip=request.remote_addr)
        flash(f"Visitor checked in. Badge: {badge_number}", "success")
    except Exception as exc:
        logger.exception("visit_checkin: save error — %s", exc)
        db.session.rollback()
        flash("Failed to check in visitor.", "danger")

    return redirect(url_for("visitors.visit_detail", visit_id=visit.id))


@visitors_bp.route("/visits/<int:visit_id>/checkout", methods=["POST"])
@login_required
def visit_checkout(visit_id):
    if not current_user.can_manage_visitors():
        flash("Permission denied.", "danger")
        return redirect(url_for("visitors.visit_list"))

    try:
        visit = Visit.query.filter_by(
            id=visit_id, organization_id=current_user.organization_id
        ).first()
    except Exception as exc:
        logger.exception("visit_checkout: query error — %s", exc)
        flash("Failed to load visit.", "danger")
        return redirect(url_for("visitors.visit_list"))

    if visit is None:
        flash("Visit not found.", "warning")
        return redirect(url_for("visitors.visit_list"))

    try:
        visit.status = VisitStatus.CHECKED_OUT
        visit.checked_out_at = datetime.now(timezone.utc)

        if visit.badge:
            visit.badge.status = BadgeStatus.RETURNED
            visit.badge.returned_at = datetime.now(timezone.utc)

        db.session.commit()
        log_audit("visitor_checkout", "visit", visit.id,
                  f"Checked out {visit.visitor.full_name}",
                  ip=request.remote_addr)
        flash("Visitor checked out successfully.", "success")
    except Exception as exc:
        logger.exception("visit_checkout: save error — %s", exc)
        db.session.rollback()
        flash("Failed to check out visitor.", "danger")

    return redirect(url_for("visitors.visit_detail", visit_id=visit.id))


@visitors_bp.route("/visits/<int:visit_id>/deny", methods=["POST"])
@login_required
def visit_deny(visit_id):
    if not current_user.can_manage_visitors():
        flash("Permission denied.", "danger")
        return redirect(url_for("visitors.visit_list"))

    try:
        visit = Visit.query.filter_by(
            id=visit_id, organization_id=current_user.organization_id
        ).first()
    except Exception as exc:
        logger.exception("visit_deny: query error — %s", exc)
        flash("Failed to load visit.", "danger")
        return redirect(url_for("visitors.visit_list"))

    if visit is None:
        flash("Visit not found.", "warning")
        return redirect(url_for("visitors.visit_list"))

    try:
        visit.status = VisitStatus.DENIED
        visit.denied_reason = request.form.get("reason", "").strip()
        db.session.commit()
        log_audit("visitor_denied", "visit", visit.id,
                  f"Denied {visit.visitor.full_name}: {visit.denied_reason}",
                  ip=request.remote_addr)
        flash("Visitor entry denied.", "warning")
    except Exception as exc:
        logger.exception("visit_deny: save error — %s", exc)
        db.session.rollback()
        flash("Failed to deny visitor.", "danger")

    return redirect(url_for("visitors.visit_detail", visit_id=visit.id))
