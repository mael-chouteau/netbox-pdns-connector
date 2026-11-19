from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path(
        "",
        RedirectView.as_view(
            pattern_name="plugins:netbox_pdns_connector:status",
            permanent=False,
        ),
        name="home",
    ),
    path("status/", views.StatusView.as_view(), name="status"),
    path("zones/<int:zone_id>/", views.ZoneDetailView.as_view(), name="zone_detail"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
]