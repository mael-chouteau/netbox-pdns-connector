"""Convert netbox_dns record fields to PowerDNS RRset payloads (pure functions)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SUPPORTED_TYPES = frozenset({"A", "AAAA", "PTR", "CNAME", "MX", "TXT", "SRV", "NS", "SOA"})


def canonical_fqdn(name: str, zone_name: str) -> str:
    """Return an absolute DNS name with a trailing dot."""
    name = (name or "").strip()
    zone_name = (zone_name or "").strip().rstrip(".")
    if name in ("@", ""):
        fqdn = zone_name
    elif name.endswith("."):
        fqdn = name.rstrip(".")
    else:
        fqdn = f"{name}.{zone_name}" if zone_name else name
    return f"{fqdn.rstrip('.')}."


def format_txt_value(value: str) -> str:
    """Format TXT RDATA for PowerDNS (quoted string)."""
    value = value or ""
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value
    # PowerDNS accepts quoted TXT; escape backslashes and quotes
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    if any(c.isspace() for c in value) or not value:
        return f'"{escaped}"'
    if len(value) > 255:
        return f'"{escaped}"'
    return f'"{escaped}"'


def record_content(rr_type: str, value: str) -> str:
    """Map a netbox_dns record value to PowerDNS record content."""
    rr_type = (rr_type or "").upper()
    value = (value or "").strip()
    if rr_type in ("A", "AAAA"):
        return value
    if rr_type == "PTR":
        if value.endswith("."):
            return value
        return canonical_fqdn(value, "")
    if rr_type in ("CNAME", "NS"):
        return canonical_fqdn(value, "") if value not in ("@", "") else value
    if rr_type == "MX":
        parts = value.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            priority, host = parts[0], parts[1]
            host = canonical_fqdn(host, "") if not host.endswith(".") else host
            return f"{priority} {host}"
        host = canonical_fqdn(value, "") if not value.endswith(".") else value
        return f"10 {host}"
    if rr_type == "SRV":
        return value
    if rr_type == "TXT":
        return format_txt_value(value)
    if rr_type == "SOA":
        return value
    return value


@dataclass(frozen=True)
class SimpleRecord:
    """Minimal record stand-in for unit tests."""

    name: str
    type: str
    value: str
    ttl: int | None = None
    status: str = "active"


def build_rrsets(
    zone_name: str,
    records: list[Any],
    default_ttl: int = 3600,
) -> list[dict[str, Any]]:
    """
    Group records by (name, type) and build PowerDNS REPLACE rrsets.

    Records with unsupported types or non-active status are skipped.
    """
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    zone_canonical = canonical_fqdn("@", zone_name)

    for rec in records:
        status = getattr(rec, "status", "active")
        if status != "active":
            continue
        rr_type = str(getattr(rec, "type", "")).upper()
        if rr_type not in SUPPORTED_TYPES:
            continue
        rec_name = getattr(rec, "name", "@")
        fqdn = canonical_fqdn(rec_name, zone_name)
        ttl = getattr(rec, "ttl", None) or default_ttl
        content = record_content(rr_type, getattr(rec, "value", ""))
        key = (fqdn, rr_type)
        grouped.setdefault(key, [])
        entry = {"content": content, "disabled": False}
        if entry not in grouped[key]:
            grouped[key].append(entry)
        _ = ttl  # ttl is per-rrset; stored below

    rrsets: list[dict[str, Any]] = []
    for (fqdn, rr_type), pdns_records in sorted(grouped.items()):
        ttl = default_ttl
        for rec in records:
            if canonical_fqdn(getattr(rec, "name", "@"), zone_name) == fqdn:
                if str(getattr(rec, "type", "")).upper() == rr_type:
                    ttl = getattr(rec, "ttl", None) or default_ttl
                    break
        pdns_records = sorted(pdns_records, key=lambda r: r["content"])
        rrsets.append(
            {
                "name": fqdn,
                "type": rr_type,
                "ttl": int(ttl),
                "changetype": "REPLACE",
                "records": pdns_records,
            }
        )

    if not any(r["type"] == "SOA" for r in rrsets) and zone_canonical:
        pass  # SOA comes from netbox_dns managed records

    return rrsets


def rrsets_fingerprint(rrsets: list[dict[str, Any]]) -> str:
    """Stable JSON fingerprint for idempotence checks."""
    normalized = []
    for rs in sorted(rrsets, key=lambda x: (x["name"], x["type"])):
        records = sorted(rs.get("records", []), key=lambda r: r.get("content", ""))
        normalized.append(
            {
                "name": rs["name"],
                "type": rs["type"],
                "ttl": rs.get("ttl"),
                "records": records,
            }
        )
    return json.dumps(normalized, sort_keys=True)