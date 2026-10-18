"""Patch 10: Celery worker, explicitly started by an operator."""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("phone_discover")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
