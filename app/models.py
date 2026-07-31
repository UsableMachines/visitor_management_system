import enum
import uuid
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


# ── Enums ────────────────────────────────────────────────────────────
class VisitStatus(enum.Enum):
    PRE_REGISTERED = "pre_registered"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    DENIED = "denied"
    EXPIRED = "expired"


class BadgeStatus(enum.Enum):
    ACTIVE = "active"
    RETURNED = "returned"
    LOST = "lost"
    EXPIRED = "expired"


class WatchlistMatchLevel(enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXACT = "exact"


# ── Organization (tenant) ───────────────────────────────────────────
class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    address = db.Column(db.Text, default="")
    phone = db.Column(db.String(30), default="")
    logo_url = db.Column(db.String(500), default="")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    users = db.relationship("User", backref="organization", lazy="dynamic")
    visitors = db.relationship("Visitor", backref="organization", lazy="dynamic")
    visits = db.relationship("Visit", backref="organization", lazy="dynamic")
    watchlist_entries = db.relationship(
        "WatchlistEntry", backref="organization", lazy="dynamic"
    )


# ── Role ─────────────────────────────────────────────────────────────
class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), default="")
    users = db.relationship("User", backref="role", lazy="dynamic")


# ── User ─────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(100), default="")
    last_name = db.Column(db.String(100), default="")
    phone = db.Column(db.String(30), default="")
    department = db.Column(db.String(100), default="")
    is_active = db.Column(db.Boolean, default=True)
    theme = db.Column(db.String(10), default="light")
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False
    )
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    def has_role(self, *role_names):
        return self.role and self.role.name in role_names

    def can_manage_org(self):
        return self.has_role("super_admin", "org_admin")

    def can_manage_visitors(self):
        return self.has_role("super_admin", "org_admin", "front_desk", "security")

    def can_view_watchlist(self):
        return self.has_role("super_admin", "org_admin", "security")

    def can_view_audit(self):
        return self.has_role("super_admin", "org_admin", "security")


# ── Visitor ──────────────────────────────────────────────────────────
class Visitor(db.Model):
    __tablename__ = "visitors"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(200), default="")
    phone = db.Column(db.String(30), default="")
    company = db.Column(db.String(200), default="")
    photo_url = db.Column(db.String(500), default="")
    id_type = db.Column(db.String(50), default="")
    id_number = db.Column(db.String(100), default="")
    notes = db.Column(db.Text, default="")
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    visits = db.relationship("Visit", backref="visitor", lazy="dynamic")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


# ── Visit ────────────────────────────────────────────────────────────
class Visit(db.Model):
    __tablename__ = "visits"
    id = db.Column(db.Integer, primary_key=True)
    visit_code = db.Column(
        db.String(36), default=lambda: uuid.uuid4().hex[:8].upper(), unique=True
    )
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitors.id"), nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False
    )
    purpose = db.Column(db.String(300), default="")
    status = db.Column(db.Enum(VisitStatus), default=VisitStatus.PRE_REGISTERED)
    expected_arrival = db.Column(db.DateTime, nullable=True)
    checked_in_at = db.Column(db.DateTime, nullable=True)
    checked_out_at = db.Column(db.DateTime, nullable=True)
    watchlist_match_level = db.Column(
        db.Enum(WatchlistMatchLevel), default=WatchlistMatchLevel.NONE
    )
    watchlist_details = db.Column(db.Text, default="")
    ai_risk_score = db.Column(db.Float, nullable=True)
    ai_risk_level = db.Column(db.String(20), default="")
    ai_summary = db.Column(db.Text, default="")
    denied_reason = db.Column(db.String(300), default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    host = db.relationship("User", backref="hosted_visits")
    badge = db.relationship("Badge", backref="visit", uselist=False)


# ── Badge ────────────────────────────────────────────────────────────
class Badge(db.Model):
    __tablename__ = "badges"
    id = db.Column(db.Integer, primary_key=True)
    badge_number = db.Column(db.String(20), nullable=False)
    visit_id = db.Column(db.Integer, db.ForeignKey("visits.id"), nullable=False)
    status = db.Column(db.Enum(BadgeStatus), default=BadgeStatus.ACTIVE)
    issued_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    returned_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)


# ── Watchlist Entry ──────────────────────────────────────────────────
class WatchlistEntry(db.Model):
    __tablename__ = "watchlist_entries"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    reason = db.Column(db.Text, default="")
    severity = db.Column(db.String(20), default="high")
    email = db.Column(db.String(200), default="")
    id_number = db.Column(db.String(100), default="")
    is_active = db.Column(db.Boolean, default=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False
    )
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.relationship("User", backref="watchlist_entries_created")


# ── Audit Log ────────────────────────────────────────────────────────
class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), default="")
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, default="")
    ip_address = db.Column(db.String(50), default="")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user = db.relationship("User", backref="audit_logs")


# ── Host Notification ────────────────────────────────────────────────
class HostNotification(db.Model):
    __tablename__ = "host_notifications"
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visits.id"), nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    visit = db.relationship("Visit", backref="notifications")
    host = db.relationship("User", backref="notifications")
