import logging

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User
from app.routes.helpers import log_audit

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            user = User.query.filter_by(username=username).first()
        except Exception as exc:
            logger.exception("login: DB error — %s", exc)
            flash("An error occurred. Please try again.", "danger")
            return render_template("auth/login.html"), 500

        if user is None or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html")

        if not user.is_active:
            flash("Your account has been deactivated. Contact an administrator.", "warning")
            return render_template("auth/login.html")

        login_user(user, remember=request.form.get("remember"))
        log_audit("login", "user", user.id, f"User {user.username} logged in",
                  ip=request.remote_addr)
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    log_audit("logout", "user", current_user.id,
              f"User {current_user.username} logged out",
              ip=request.remote_addr)
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("auth/register.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("auth/register.html")

        try:
            existing = User.query.filter(
                (User.username == username) | (User.email == email)
            ).first()
        except Exception as exc:
            logger.exception("register: DB error — %s", exc)
            flash("An error occurred. Please try again.", "danger")
            return render_template("auth/register.html"), 500

        if existing:
            flash("Username or email already exists.", "danger")
            return render_template("auth/register.html")

        try:
            from app.models import Role, Organization
            default_org = Organization.query.first()
            host_role = Role.query.filter_by(name="host").first()
            user = User(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                organization_id=default_org.id,
                role_id=host_role.id,
                is_active=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            log_audit("register", "user", user.id, f"New user registered: {username}",
                      ip=request.remote_addr)
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as exc:
            logger.exception("register: save error — %s", exc)
            db.session.rollback()
            flash("An error occurred during registration.", "danger")
            return render_template("auth/register.html"), 500

    return render_template("auth/register.html")
