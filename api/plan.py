"""Vercel serverless entry point for POST /api/plan, served by the Django app."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", ".vercel.app")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
