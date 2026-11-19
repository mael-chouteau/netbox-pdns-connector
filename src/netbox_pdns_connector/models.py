"""Django models for the PowerDNS connector plugin."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from netbox.models.features import JobsMixin

from .crypto_util import decrypt_secret, encrypt_secret

LAST_STATUS_CHOICES = (
    ("success", "Success"),
    ("error", "Error"),
    ("running", "Running"),
    ("", "Never run"),
)


class PowerDNSSyncConfig(JobsMixin, NetBoxModel):
    """Singleton configuration for netbox_dns → PowerDNS synchronization."""

    name = models.CharField(max_length=100, default="default", unique=True)

    primary_url = models.CharField(
        max_length=255,
        blank=True,
        help_text="PowerDNS API base URL for the primary server (no trailing path)",
    )
    secondary_url = models.CharField(
        max_length=255,
        blank=True,
        help_text="PowerDNS API base URL for the secondary server (optional)",
    )
    server_id = models.CharField(
        max_length=100,
        default="localhost",
        help_text="PowerDNS server id in the API (often localhost)",
    )
    api_key_encrypted = models.TextField(blank=True)

    view = models.ForeignKey(
        to="netbox_dns.View",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
        help_text="Only sync zones in this DNS view (all views if empty)",
    )

    sync_enabled = models.BooleanField(default=True)
    sync_interval = models.PositiveIntegerField(
        default=15,
        help_text="Minutes between automatic sync runs",
    )
    realtime_sync = models.BooleanField(
        default=True,
        help_text="Enqueue sync when netbox_dns zones or records change",
    )
    dry_run = models.BooleanField(default=False)

    last_status = models.CharField(
        max_length=20, choices=LAST_STATUS_CHOICES, blank=True, default=""
    )
    last_message = models.TextField(blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_duration_seconds = models.FloatField(null=True, blank=True)
    last_stats_zones = models.PositiveIntegerField(default=0)
    last_stats_rrsets = models.PositiveIntegerField(default=0)
    last_stats_pushed = models.PositiveIntegerField(default=0)
    last_stats_errors = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "PowerDNS sync configuration"
        verbose_name_plural = "PowerDNS sync configurations"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_pdns_connector:status")

    @classmethod
    def get_solo(cls) -> PowerDNSSyncConfig:
        obj, _ = cls.objects.get_or_create(name="default")
        return obj

    def set_api_key(self, plaintext: str) -> None:
        if plaintext:
            self.api_key_encrypted = encrypt_secret(plaintext)

    def get_api_key(self) -> str:
        return decrypt_secret(self.api_key_encrypted)

    def target_urls(self) -> list[str]:
        urls = []
        if self.primary_url:
            urls.append(self.primary_url.strip())
        if self.secondary_url:
            urls.append(self.secondary_url.strip())
        return urls