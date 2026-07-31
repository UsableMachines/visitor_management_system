import logging

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models import User, Role, Organization
from app.routes.helpers import role_required, log_audit

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
@login_required
@role_required("super_admin", "org_admin")
def admin_dashboard():
    try:
        if current_user.has_role("super_admin"):
            orgs = Organization.query.all()
            users = User.query.all()
        else:
            orgs = [current_user.organization]
            users = User.query.filter_by(
                organization_id=current_user.organization_id
            ).all()
        roles = Role.query.all()
    except Exception as exc:
        logger.exception("admin_dashboard: query error — %s", exc)
        orgs, users, roles = [], [], []

    return render_template(
        "admin/dashboard.html", orgs=orgs, users=users, roles=roles
    )


@admin_bp.route("/users")
@login_required
@role_required("super_admin", "org_admin")
def user_list():
    try:
        if current_user.has_role("super_admin"):
            users = User.query.order_by(User.username).all()
        else:
            users = User.query.filter_by(
                organization_id=current_user.organization_id
            ).order_by(User.username).all()
        roles = Role.query.all()
    except Exception as exc:
        logger.exception("user_list: query error — %s", exc)
        users, roles = [], []

    return render_template("admin/users.html", users=users, roles=roles)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("super_admin", "org_admin")
def user_edit(user_id):
    try:
        user = db.session.get(User, user_id)
    except Exception as exc:
        logger.exception("user_edit: query error — %s", exc)
        flash("Failed to load user.", "danger")
        return redirect(url_for("admin.user_list"))

    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("admin.user_list"))

    if not current_user.has_role("super_admin") and user.organization_id != current_user.organization_id:
        flash("Permission denied.", "danger")
        return redirect(url_for("admin.user_list"))

    try:
        roles = Role.query.all()
        orgs = (
            Organization.query.all()
            if current_user.has_role("super_admin")
            else [current_user.organization]
        )
    except Exception as exc:
        logger.exception("user_edit: roles/orgs query error — %s", exc)
        roles, orgs = [], []

    if request.method == "POST":
        try:
            user.first_name = request.form.get("first_name", "").strip()
            user.last_name = request.form.get("last_name", "").strip()
            user.email = request.form.get("email", "").strip()
            user.phone = request.form.get("phone", "").strip()
            user.department = request.form.get("department", "").strip()
            user.role_id = request.form.get("role_id", type=int) or user.role_id
            user.is_active = request.form.get("is_active") == "on"
            if current_user.has_role("super_admin"):
                org_id = request.form.get("organization_id", type=int)
                if org_id:
                    user.organization_id = org_id
            new_pw = request.form.get("new_password", "").strip()
            if new_pw:
                user.set_password(new_pw)
            db.session.commit()
            log_audit("user_edit", "user", user.id,
                      f"Edited user {user.username}", ip=request.remote_addr)
            flash("User updated.", "success")
            return redirect(url_for("admin.user_list"))
        except Exception as exc:
            logger.exception("user_edit: save error — %s", exc)
            db.session.rollback()
            flash("Failed to update user.", "danger")

    return render_template("admin/user_edit.html", user=user, roles=roles, orgs=orgs)


@admin_bp.route("/organizations")
@login_required
@role_required("super_admin")
def org_list():
    try:
        orgs = Organization.query.order_by(Organization.name).all()
    except Exception as exc:
        logger.exception("org_list: query error — %s", exc)
        orgs = []
    return render_template("admin/organizations.html", orgs=orgs)


@admin_bp.route("/organizations/new", methods=["GET", "POST"])
@login_required
@role_required("super_admin")
def org_new():
    if request.method == "POST":
        try:
            org = Organization(
                name=request.form.get("name", "").strip(),
                slug=request.form.get("slug", "").strip().lower().replace(" ", "-"),
                address=request.form.get("address", "").strip(),
                phone=request.form.get("phone", "").strip(),
            )
            db.session.add(org)
            db.session.commit()
            log_audit("org_created", "organization", org.id,
                      f"Created org {org.name}", ip=request.remote_addr)
            flash("Organization created.", "success")
            return redirect(url_for("admin.org_list"))
        except Exception as exc:
            logger.exception("org_new: save error — %s", exc)
            db.session.rollback()
            flash("Failed to create organization.", "danger")
    return render_template("admin/org_new.html")
