# Visitor Management System

A complete web application for managing visitor registration, host notification, badge issuance, watchlist screening, AI-powered risk analysis, and audit logging with multi-tenancy and role-based access control (RBAC).

## Features

- **Visitor Registration** — Register visitors with ID verification, host assignment, and automated watchlist screening
- **Host Notification** — Automatic notifications to hosts when visitors are registered, check in, or check out
- **Badge Issuance** — Automated badge generation at check-in with tracking for active, returned, and lost badges
- **Watchlist Screening** — Real-time screening against organization watchlists with severity-based blocking
- **AI Risk Analysis** — Kindo AI agent integration for visitor risk scoring and security recommendations
- **Audit Logging** — Complete audit trail of all system actions for compliance
- **Multi-Tenancy** — Organization-isolated data with support for multiple tenants
- **RBAC** — Five roles: Super Admin, Org Admin, Front Desk, Security, Host

## Quick Start

1. Copy `.env.example` to `.env` and configure
2. `pip install -r requirements.txt`
3. `python wsgi.py`
4. Login with `admin` / `admin` (change password immediately)

## Default Credentials

| Username | Password | Role |
|----------|----------|------|
| admin | admin | Super Admin |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| SECRET_KEY | Yes | Flask secret key |
| DATABASE_URL | No | Database URI (default: SQLite) |
| KINDO_API_TOKEN | For AI | Kindo API bearer token |
| KINDO_AGENT_ID | For AI | Kindo enrichment agent ID |
| SESSION_COOKIE_PATH | No | Cookie path (default: /) |
| PORT | No | Server port (default: 5000) |

## Tech Stack

- Python 3.12 / Flask 3.1
- SQLAlchemy ORM with Flask-Migrate
- Flask-Login for authentication
- Gunicorn for production serving
- Kindo AI agent for risk analysis
