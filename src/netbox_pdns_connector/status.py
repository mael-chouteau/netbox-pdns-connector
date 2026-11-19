"""Live PowerDNS status probe and zone parity vs netbox_dns."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .models import PowerDNSSyncConfig
from .pdns_client import PowerDNSClient, parity_status, rrset_counts, soa_serial_from_zone


@dataclass
class ServerStatus:
    label: str
    url: str
    reachable: bool = False
    latency_ms: float | None = None
    version: str = ""
    zone_count: int = 0
    error: str = ""
    client: PowerDNSClient | None = field(default=None, repr=False)


@dataclass
class ZoneParity:
    zone_id: int
    name: str
    netbox_serial: int | None = None
    primary_serial: int | None = None
    secondary_serial: int | None = None
    record_count: int = 0
    type_counts: dict[str, int] = field(default_factory=dict)
    status: str = "unreachable"  # in_sync | drift | unreachable | missing
    netbox_dns_url: str = ""
    detail_url: str = ""


@dataclass
class LiveStatus:
    servers: list[ServerStatus] = field(default_factory=list)
    zones: list[ZoneParity] = field(default_factory=list)
    configured: bool = False
    error: str = ""


def _netbox_dns_zone_url(zone_id: int) -> str:
    try:
        from django.urls import reverse

        return reverse("plugins:netbox_dns:zone", args=[zone_id])
    except Exception:
        return f"/plugins/netbox-dns/zones/{zone_id}/"


def _detail_url(zone_id: int) -> str:
    try:
        from django.urls import reverse

        return reverse("plugins:netbox_pdns_connector:zone_detail", args=[zone_id])
    except Exception:
        return f"/plugins/powerdns/zones/{zone_id}/"


def _active_netbox_zones(cfg: PowerDNSSyncConfig):
    from django.db.models import Count, Q
    from netbox_dns.models import Zone

    qs = Zone.objects.filter(status="active").annotate(
        active_record_count=Count("records", filter=Q(records__status="active")),
    )
    if cfg.view_id:
        qs = qs.filter(view_id=cfg.view_id)
    return qs.order_by("name")


def _record_type_counts(zone) -> dict[str, int]:
    from django.db.models import Count
    from netbox_dns.models import Record

    rows = (
        Record.objects.filter(zone=zone, status="active")
        .values("type")
        .annotate(c=Count("id"))
    )
    return {row["type"]: row["c"] for row in rows}


def probe_powerdns(cfg: PowerDNSSyncConfig, *, with_zone_parity: bool = True) -> LiveStatus:
    api_key = cfg.get_api_key()
    targets: list[tuple[str, str]] = []
    if cfg.primary_url:
        targets.append(("Primary", cfg.primary_url.strip()))
    if cfg.secondary_url:
        targets.append(("Secondary", cfg.secondary_url.strip()))

    if not targets:
        return LiveStatus(error="PowerDNS URLs are not configured")
    if not api_key:
        return LiveStatus(error="PowerDNS API key is not configured")

    live = LiveStatus(configured=True)
    clients: list[PowerDNSClient | None] = []

    for label, url in targets:
        st = ServerStatus(label=label, url=url)
        started = time.monotonic()
        try:
            client = PowerDNSClient(url, api_key, server_id=cfg.server_id)
            info = client.get_server()
            zones = client.list_zones()
            st.reachable = True
            st.latency_ms = round((time.monotonic() - started) * 1000, 1)
            st.version = str(info.get("version", ""))
            st.zone_count = len(zones)
            st.client = client
            clients.append(client)
        except Exception as exc:
            st.latency_ms = round((time.monotonic() - started) * 1000, 1)
            st.error = str(exc)[:500]
            clients.append(None)
        live.servers.append(st)

    try:
        if with_zone_parity:
            live.zones = _build_zone_parity(cfg, clients)
    except Exception as exc:
        live.error = (live.error + "; " if live.error else "") + f"Zone parity: {exc}"[:400]
    finally:
        for client in clients:
            if client is not None:
                client.close()
        for st in live.servers:
            st.client = None

    return live


def _build_zone_parity(
    cfg: PowerDNSSyncConfig,
    clients: list[PowerDNSClient | None],
) -> list[ZoneParity]:
    configured = len(clients)
    rows: list[ZoneParity] = []
    for zone in _active_netbox_zones(cfg):
        type_counts = _record_type_counts(zone)
        serials: list[int | None] = []
        for client in clients:
            if client is None:
                serials.append(None)
                continue
            try:
                serials.append(client.get_zone_soa_serial(zone.name))
            except Exception:
                serials.append(None)

        primary = serials[0] if len(serials) > 0 else None
        secondary = serials[1] if len(serials) > 1 else None
        nb_serial = zone.soa_serial
        try:
            nb_serial = int(nb_serial) if nb_serial is not None else None
        except (TypeError, ValueError):
            nb_serial = None

        rows.append(
            ZoneParity(
                zone_id=zone.pk,
                name=zone.name,
                netbox_serial=nb_serial,
                primary_serial=primary,
                secondary_serial=secondary,
                record_count=int(getattr(zone, "active_record_count", 0) or 0),
                type_counts=type_counts,
                status=parity_status(nb_serial, serials, configured_targets=configured),
                netbox_dns_url=_netbox_dns_zone_url(zone.pk),
                detail_url=_detail_url(zone.pk),
            )
        )
    return rows


def zone_detail_parity(cfg: PowerDNSSyncConfig, zone) -> dict[str, Any]:
    """Parity + record list context for a single netbox_dns zone."""
    api_key = cfg.get_api_key()
    targets = cfg.target_urls()
    serials: list[int | None] = []
    pdns_counts: list[dict[str, int]] = []
    errors: list[str] = []

    for url in targets:
        if not api_key:
            serials.append(None)
            pdns_counts.append({})
            errors.append("API key missing")
            continue
        try:
            with PowerDNSClient(url, api_key, server_id=cfg.server_id) as client:
                zjson = client.get_zone(zone.name)
                serials.append(soa_serial_from_zone(zjson))
                pdns_counts.append(rrset_counts(zjson))
        except Exception as exc:
            serials.append(None)
            pdns_counts.append({})
            errors.append(str(exc)[:200])

    nb_serial = zone.soa_serial
    try:
        nb_serial = int(nb_serial) if nb_serial is not None else None
    except (TypeError, ValueError):
        nb_serial = None

    from netbox_dns.models import Record

    records = list(
        Record.objects.filter(zone=zone, status="active").order_by("type", "name", "value")
    )
    type_counts = _record_type_counts(zone)

    return {
        "zone": zone,
        "netbox_serial": nb_serial,
        "primary_serial": serials[0] if serials else None,
        "secondary_serial": serials[1] if len(serials) > 1 else None,
        "status": parity_status(nb_serial, serials, configured_targets=len(targets)),
        "records": records,
        "type_counts": type_counts,
        "pdns_counts": pdns_counts,
        "errors": errors,
        "netbox_dns_url": _netbox_dns_zone_url(zone.pk),
    }
