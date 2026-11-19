"""Realtime sync triggers on netbox_dns changes."""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save

from .jobs import enqueue_realtime
from .models import PowerDNSSyncConfig

_CONNECTED = False


def _on_dns_change(sender, **kwargs) -> None:
    cfg = PowerDNSSyncConfig.get_solo()
    enqueue_realtime(cfg)


def connect_signals() -> None:
    global _CONNECTED
    if _CONNECTED:
        return
    try:
        from netbox_dns.models import Record, Zone
    except ImportError:
        return
    for model in (Record, Zone):
        post_save.connect(_on_dns_change, sender=model, dispatch_uid=f"pdns_save_{model.__name__}")
        post_delete.connect(_on_dns_change, sender=model, dispatch_uid=f"pdns_del_{model.__name__}")
    _CONNECTED = True


connect_signals()