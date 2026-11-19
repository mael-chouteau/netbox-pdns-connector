"""httpx client for the PowerDNS Authoritative REST API v1."""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from .rrset_convert import canonical_fqdn


def parse_soa_serial(content: str | None) -> int | None:
    """Extract the serial integer from SOA RDATA (mname rname serial refresh …)."""
    if not content:
        return None
    parts = content.split()
    if len(parts) < 3:
        return None
    try:
        return int(parts[2])
    except (TypeError, ValueError):
        return None


def soa_serial_from_zone(zone: dict[str, Any] | None) -> int | None:
    """Return SOA serial from a PowerDNS zone JSON payload, if present."""
    if not zone:
        return None
    for rrset in zone.get("rrsets") or []:
        if rrset.get("type") != "SOA":
            continue
        records = rrset.get("records") or []
        if not records:
            continue
        return parse_soa_serial(records[0].get("content"))
    # Some PowerDNS versions expose serial at zone top-level
    serial = zone.get("serial")
    if serial is None:
        return None
    try:
        return int(serial)
    except (TypeError, ValueError):
        return None


def soa_from_rrsets(rrsets: list[dict[str, Any]]) -> tuple[int | None, str | None]:
    """Return (serial, content) for the SOA rrset in a REPLACE payload."""
    for rrset in rrsets:
        if rrset.get("type") != "SOA":
            continue
        records = rrset.get("records") or []
        if not records:
            return None, None
        content = records[0].get("content")
        return parse_soa_serial(content), content
    return None, None


def needs_zone_rebuild(existing_serial: int | None, desired_serial: int | None) -> bool:
    """True when PowerDNS would refuse to lower the SOA serial."""
    if desired_serial is None or existing_serial is None:
        return False
    return existing_serial > desired_serial


def rrset_counts(zone: dict[str, Any] | None) -> dict[str, int]:
    """Count RRsets and records by type from a PowerDNS zone payload."""
    counts: dict[str, int] = {"rrsets": 0, "records": 0}
    if not zone:
        return counts
    for rrset in zone.get("rrsets") or []:
        rr_type = str(rrset.get("type") or "")
        n = len(rrset.get("records") or [])
        counts["rrsets"] += 1
        counts["records"] += n
        if rr_type:
            counts[rr_type] = counts.get(rr_type, 0) + n
    return counts


def parity_status(
    netbox_serial: int | None,
    target_serials: list[int | None],
    *,
    configured_targets: int,
) -> str:
    """Compute parity: in_sync | drift | unreachable | missing."""
    if netbox_serial is None:
        return "missing"
    if configured_targets <= 0:
        return "unreachable"
    checked = target_serials[:configured_targets]
    if len(checked) < configured_targets or any(s is None for s in checked):
        return "unreachable"
    if any(s != netbox_serial for s in checked):
        return "drift"
    return "in_sync"


class PowerDNSClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        server_id: str = "localhost",
        timeout: float = 120.0,
        verify_ssl: bool = True,
    ):
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("PowerDNS base URL is required")
        if base_url.endswith("/api/v1"):
            api_root = base_url
        else:
            api_root = f"{base_url}/api/v1"
        self.api_root = api_root.rstrip("/")
        self.server_id = server_id or "localhost"
        self._client = httpx.Client(
            timeout=timeout,
            verify=verify_ssl,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PowerDNSClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _url(self, path: str = "") -> str:
        # PowerDNS returns 404 for trailing slash on /servers/{id}/
        base = f"{self.api_root}/servers/{urllib.parse.quote(self.server_id, safe='')}"
        path = (path or "").lstrip("/")
        return f"{base}/{path}" if path else base

    def get_server(self) -> dict[str, Any]:
        r = self._client.get(self._url(""))
        r.raise_for_status()
        return r.json()

    def list_zones(self) -> list[dict[str, Any]]:
        r = self._client.get(self._url("zones"))
        r.raise_for_status()
        return r.json()

    def get_zone(self, zone_name: str) -> dict[str, Any] | None:
        zid = urllib.parse.quote(canonical_fqdn("@", zone_name), safe="")
        r = self._client.get(self._url(f"zones/{zid}"))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def create_zone(
        self,
        zone_name: str,
        *,
        kind: str = "Native",
        soa_content: str | None = None,
    ) -> dict[str, Any]:
        fqdn = canonical_fqdn("@", zone_name)
        content = soa_content or "ns1.invalid. hostmaster.invalid. 1 10800 3600 604800 3600"
        serial = parse_soa_serial(content) or 1
        # soa_edit_api=NONE is required: DEFAULT rewrites serials to YYYYMMDDNN
        payload = {
            "name": fqdn,
            "kind": kind,
            "nameservers": [],
            "soa_edit": "NONE",
            "soa_edit_api": "NONE",
            "serial": serial,
            "rrsets": [
                {
                    "name": fqdn,
                    "type": "SOA",
                    "ttl": 3600,
                    "changetype": "REPLACE",
                    "records": [{"content": content, "disabled": False}],
                }
            ],
        }
        r = self._client.post(self._url("zones"), json=payload)
        r.raise_for_status()
        return r.json()

    def delete_zone(self, zone_name: str) -> None:
        zid = urllib.parse.quote(canonical_fqdn("@", zone_name), safe="")
        r = self._client.delete(self._url(f"zones/{zid}"))
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    def ensure_soa_edit_none(self, zone_name: str) -> None:
        """Disable SOA-EDIT-API on an existing zone (DEFAULT rewrites serials)."""
        zid = urllib.parse.quote(canonical_fqdn("@", zone_name), safe="")
        r = self._client.put(
            self._url(f"zones/{zid}"),
            json={"soa_edit": "NONE", "soa_edit_api": "NONE"},
        )
        r.raise_for_status()

    def ensure_native_zone(
        self,
        zone_name: str,
        *,
        soa_content: str | None = None,
    ) -> bool:
        """Create the zone if missing. Returns True if created."""
        if self.get_zone(zone_name) is not None:
            return False
        self.create_zone(zone_name, soa_content=soa_content)
        return True

    def patch_zone_rrsets(self, zone_name: str, rrsets: list[dict[str, Any]]) -> None:
        if not rrsets:
            return
        zid = urllib.parse.quote(canonical_fqdn("@", zone_name), safe="")
        payload = {"rrsets": rrsets}
        r = self._client.patch(self._url(f"zones/{zid}"), json=payload)
        r.raise_for_status()

    def replace_zone(self, zone_name: str, rrsets: list[dict[str, Any]]) -> None:
        """Ensure zone exists, REPLACE desired rrsets, DELETE orphans.

        PowerDNS DEFAULT soa_edit_api rewrites SOA to YYYYMMDDNN; we force NONE
        and recreate the zone when an existing serial is higher than NetBox.
        """
        desired_serial, desired_soa = soa_from_rrsets(rrsets)
        existing = self.get_zone(zone_name)
        existing_serial = soa_serial_from_zone(existing)

        if existing is not None and needs_zone_rebuild(existing_serial, desired_serial):
            self.delete_zone(zone_name)
            existing = None

        if existing is None:
            self.create_zone(zone_name, soa_content=desired_soa)
            existing = self.get_zone(zone_name) or {"rrsets": []}
        else:
            # Existing zones may still have SOA-EDIT-API=DEFAULT from older creates
            if (existing.get("soa_edit_api") or "").upper() not in ("NONE", ""):
                self.ensure_soa_edit_none(zone_name)

        desired = {(r["name"], r["type"]) for r in rrsets}
        deletes: list[dict[str, Any]] = []
        for old in existing.get("rrsets") or []:
            key = (old.get("name"), old.get("type"))
            # Leave DNSSEC / proprietary types alone if NetBox does not manage them
            if old.get("type") in ("RRSIG", "NSEC", "NSEC3", "DNSKEY", "CDS", "CDNSKEY"):
                continue
            if key not in desired:
                deletes.append(
                    {
                        "name": old["name"],
                        "type": old["type"],
                        "changetype": "DELETE",
                    }
                )

        self.patch_zone_rrsets(zone_name, list(rrsets) + deletes)

    def get_zone_soa_serial(self, zone_name: str) -> int | None:
        """Fetch zone and return SOA serial, or None if missing/unreachable."""
        return soa_serial_from_zone(self.get_zone(zone_name))

    def get_zone_rrset_counts(self, zone_name: str) -> dict[str, int]:
        return rrset_counts(self.get_zone(zone_name))