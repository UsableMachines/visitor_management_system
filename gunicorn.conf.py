import multiprocessing
import os

bind = "0.0.0.0:" + os.environ.get("PORT", "5000")
workers = int(os.environ.get("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
timeout = int(os.environ.get("APP_GUNICORN_TIMEOUT", "120"))
accesslog = "-"
errorlog = "-"
loglevel = "info"
