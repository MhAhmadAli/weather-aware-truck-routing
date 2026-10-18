from django.urls import re_path

from .views import PlanTripView

# The trailing slash is optional: Vercel serves the function at /api/plan without one.
urlpatterns = [re_path(r"^plan/?$", PlanTripView.as_view(), name="plan-trip")]
