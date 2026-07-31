import json
import logging
import os
import time

import requests
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from app import db
from app.models import Visit
from app.routes.helpers import log_audit

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__)

KINDO_API_URL = "https://api.kindo.ai/v1/agents/runs"
POLL_INTERVAL = 2
POLL_TIMEOUT = int(os.environ.get("APP_AGENT_POLL_TIMEOUT_SEC", "120"))


def _kindo_configured():
    return bool(os.environ.get("KINDO_API_TOKEN")) and bool(
        os.environ.get("KINDO_AGENT_ID")
    )


@api_bp.route("/kindo/status")
@login_required
def kindo_status():
    return jsonify({"configured": _kindo_configured()})


@api_bp.route("/kindo/analyze/<int:visit_id>", methods=["POST"])
@login_required
def kindo_analyze(visit_id):
    if not _kindo_configured():
        return jsonify({
            "error": "Kindo AI agent is not configured. Set KINDO_API_TOKEN and KINDO_AGENT_ID environment variables.",
            "configured": False,
        }), 422

    try:
        visit = Visit.query.filter_by(
            id=visit_id, organization_id=current_user.organization_id
        ).first()
    except Exception as exc:
        logger.exception("kindo_analyze: query error — %s", exc)
        return jsonify({"error": "Failed to load visit", "detail": str(exc)}), 500

    if visit is None:
        return jsonify({"error": "Visit not found"}), 404

    payload = {
        "operation": "analyze",
        "entity_id": str(visit.id),
        "input_data": {
            "description": "Visitor risk analysis and screening",
            "records": [
                {
                    "visitor_name": visit.visitor.full_name,
                    "visitor_email": visit.visitor.email or "",
                    "visitor_company": visit.visitor.company or "",
                    "visitor_id_type": visit.visitor.id_type or "",
                    "visitor_id_number": visit.visitor.id_number or "",
                    "host_name": visit.host.full_name if visit.host else "",
                    "purpose": visit.purpose or "",
                    "visit_code": visit.visit_code,
                    "watchlist_match_level": (
                        visit.watchlist_match_level.value
                        if visit.watchlist_match_level
                        else "none"
                    ),
                    "watchlist_details": visit.watchlist_details or "",
                }
            ],
            "context": {
                "organization": (
                    visit.organization.name if visit.organization else ""
                ),
                "policy": "standard visitor screening",
                "time_range": "current_visit",
            },
        },
        "options": {
            "detail_level": "detailed",
            "include_recommendations": True,
            "return_confidence": True,
        },
    }

    token = os.environ["KINDO_API_TOKEN"]
    agent_id = os.environ["KINDO_AGENT_ID"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = {
        "agent_id": agent_id,
        "inputs": [{"name": "request", "value": json.dumps(payload)}],
    }

    # Start the run
    try:
        resp = requests.post(KINDO_API_URL, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        run_data = resp.json()
        run_id = run_data.get("id") or run_data.get("run_id")
    except requests.RequestException as exc:
        logger.exception("kindo_analyze: API start error — %s", exc)
        return jsonify({"error": "Failed to start AI analysis", "detail": str(exc)}), 502

    if not run_id:
        return jsonify({"error": "No run ID returned from Kindo API"}), 502

    # Poll for completion
    status_url = f"{KINDO_API_URL}/{run_id}"
    start = time.time()
    result = None

    while time.time() - start < POLL_TIMEOUT:
        try:
            poll = requests.get(status_url, headers=headers, timeout=15)
            poll.raise_for_status()
            poll_data = poll.json()
            status = poll_data.get("status", "")

            if status in ("success", "completed", "done"):
                raw_output = poll_data.get("output") or poll_data.get("result", "")
                try:
                    if isinstance(raw_output, str):
                        result = json.loads(raw_output)
                    else:
                        result = raw_output
                except (json.JSONDecodeError, TypeError):
                    result = {
                        "status": "ok",
                        "summary": str(raw_output),
                        "score": 0.0,
                        "risk_level": "informational",
                        "findings": [],
                        "recommendations": [],
                        "confidence": 0.0,
                        "metadata": {
                            "agent_name": "visitor management system Kindo Enrichment Agent",
                            "schema_version": "1.0",
                        },
                    }
                break

            if status in ("failed", "error", "cancelled"):
                error_msg = poll_data.get("error") or poll_data.get("message", "Agent run failed")
                return jsonify({"error": str(error_msg)}), 502

        except requests.RequestException as exc:
            logger.warning("kindo_analyze: poll error — %s", exc)

        time.sleep(POLL_INTERVAL)

    if result is None:
        return jsonify({"error": "AI analysis timed out"}), 504

    # Save results to visit
    try:
        visit.ai_risk_score = result.get("score", 0.0)
        visit.ai_risk_level = result.get("risk_level", "informational")
        visit.ai_summary = result.get("summary", "")
        db.session.commit()
        log_audit(
            "ai_analysis", "visit", visit.id,
            f"AI analysis: risk={visit.ai_risk_level}, score={visit.ai_risk_score}",
            ip=request.remote_addr,
        )
    except Exception as exc:
        logger.exception("kindo_analyze: save error — %s", exc)
        db.session.rollback()

    return jsonify(result)


@api_bp.route("/dashboard/stats")
@login_required
def dashboard_stats():
    """Return dashboard stats as JSON for AJAX refresh."""
    from datetime import datetime, timezone
    from app.models import Visitor, VisitStatus

    try:
        org_id = current_user.organization_id
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return jsonify({
            "total_today": Visit.query.filter(
                Visit.organization_id == org_id,
                Visit.created_at >= today_start,
            ).count(),
            "checked_in": Visit.query.filter(
                Visit.organization_id == org_id,
                Visit.status == VisitStatus.CHECKED_IN,
            ).count(),
            "pre_registered": Visit.query.filter(
                Visit.organization_id == org_id,
                Visit.status == VisitStatus.PRE_REGISTERED,
            ).count(),
            "denied": Visit.query.filter(
                Visit.organization_id == org_id,
                Visit.status == VisitStatus.DENIED,
                Visit.created_at >= today_start,
            ).count(),
            "total_visitors": Visitor.query.filter_by(
                organization_id=org_id
            ).count(),
        })
    except Exception as exc:
        logger.exception("dashboard_stats: error — %s", exc)
        return jsonify({"error": "Failed to load stats"}), 500
