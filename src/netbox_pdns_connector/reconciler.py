"""Reconcile active netbox_dns zones to PowerDNS targets."""

from __future__ import annotations

import logging
from typing import Any

from .models import PowerDNSSyncConfig
from .pdns_client import PowerDNSClient
from .rrset_convert import build_rrsets

logger = logging.getLogger(__name__)


def _active_zones(cfg: PowerDNSSyncConfig):
    from django.db.models import Prefetch
    from netbox_dns.models import Record, Zone

    # netbox_dns uses plain status strings (no ACTIVE_STATUS_LIST helper)
    qs = Zone.objects.filter(status="active")
    if cfg.view_id:
        qs = qs.filter(view_id=cfg.view_id)
    return qs.prefetch_related(
        Prefetch(
            "records",
            queryset=Record.objects.filter(status="active"),
            to_attr="_active_records",
        )
    )


def records_for_zone(zone) -> list:
    return getattr(zone, "_active_records", None) or list(
        zone.records.filter(status="active")
    )


def reconcile_config(cfg: PowerDNSSyncConfig) -> dict[str, Any]:
    """
    Push all active zones to each configured PowerDNS URL.

    Returns a summary dict with zones, rrsets, pushed, errors keys.
    """
    summary: dict[str, Any] = {
        "zones": 0,
        "rrsets": 0,
        "pushed": 0,
        "errors": 0,
        "messages": [],
    }

    api_key = cfg.get_api_key()
    targets = cfg.target_urls()
    if not targets:
        summary["messages"].append("No PowerDNS URLs configured")
        return summary
    if not api_key:
        summary["messages"].append("PowerDNS API key is not configured")
        summary["errors"] += 1
        return summary

    zones = list(_active_zones(cfg))
    summary["zones"] = len(zones)

    clients: list[PowerDNSClient] = []
    try:
        for url in targets:
            clients.append(
                PowerDNSClient(
                    url,
                    api_key,
                    server_id=cfg.server_id,
                )
            )

        for zone in zones:
            zone_name = zone.name
            default_ttl = zone.default_ttl or 3600
            records = records_for_zone(zone)
            rrsets = build_rrsets(zone_name, records, default_ttl=default_ttl)
            summary["rrsets"] += len(rrsets)

            if cfg.dry_run:
                logger.info("dry_run zone=%s rrsets=%s", zone_name, len(rrsets))
                summary["pushed"] += len(rrsets) * len(clients)
                continue

            for client in clients:
                try:
                    client.replace_zone(zone_name, rrsets)
                    summary["pushed"] += len(rrsets)
                except Exception as exc:
                    summary["errors"] += 1
                    msg = f"{zone_name} @ {client.api_root}: {exc}"
                    summary["messages"].append(msg[:500])
                    logger.exception("PowerDNS push failed: %s", msg)
    finally:
        for client in clients:
            client.close()

    return summary


def run_sync(cfg: PowerDNSSyncConfig | None = None) -> int:
    """Run reconciliation; return 0 on success else number of errors."""
    cfg = cfg or PowerDNSSyncConfig.get_solo()
    result = reconcile_config(cfg)
    return min(result.get("errors", 0), 255)