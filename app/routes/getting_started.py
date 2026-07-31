import logging

from flask import Blueprint, render_template

logger = logging.getLogger(__name__)
getting_started_bp = Blueprint("getting_started", __name__)


@getting_started_bp.route("/getting-started")
def getting_started():
    return render_template("getting_started.html")
