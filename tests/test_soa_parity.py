"""Unit tests for SOA parsing and parity badges (no NetBox required)."""

from netbox_pdns_connector.pdns_client import (
    needs_zone_rebuild,
    parity_status,
    parse_soa_serial,
    rrset_counts,
    soa_from_rrsets,
    soa_serial_from_zone,
)


def test_parse_soa_serial():
    assert (
        parse_soa_serial("dns1.europe. hostmaster.dns.europe. 2026111901 43200 7200 2419200 3600")
        == 2026111901
    )
    assert parse_soa_serial("a b 42") == 42
    assert parse_soa_serial("") is None
    assert parse_soa_serial("only-two") is None
    assert parse_soa_serial("a b notint") is None


def test_soa_serial_from_zone_rrset():
    zone = {
        "rrsets": [
            {
                "name": "europe.",
                "type": "SOA",
                "records": [
                    {
                        "content": "dns1.europe. hostmaster.dns.europe. 99 1 1 1 1",
                        "disabled": False,
                    }
                ],
            }
        ]
    }
    assert soa_serial_from_zone(zone) == 99


def test_soa_serial_from_zone_top_level():
    assert soa_serial_from_zone({"serial": "12345", "rrsets": []}) == 12345
    assert soa_serial_from_zone(None) is None


def test_rrset_counts():
    zone = {
        "rrsets": [
            {"type": "A", "records": [{"content": "1.2.3.4"}, {"content": "1.2.3.5"}]},
            {"type": "NS", "records": [{"content": "ns1."}]},
        ]
    }
    c = rrset_counts(zone)
    assert c["rrsets"] == 2
    assert c["records"] == 3
    assert c["A"] == 2
    assert c["NS"] == 1


def test_parity_in_sync():
    assert parity_status(10, [10, 10], configured_targets=2) == "in_sync"
    assert parity_status(10, [10], configured_targets=1) == "in_sync"


def test_parity_drift_unreachable_missing():
    assert parity_status(10, [10, 11], configured_targets=2) == "drift"
    assert parity_status(10, [10, None], configured_targets=2) == "unreachable"
    assert parity_status(None, [1], configured_targets=1) == "missing"
    assert parity_status(10, [], configured_targets=0) == "unreachable"


def test_soa_from_rrsets_and_rebuild():
    rrsets = [
        {
            "name": "europe.",
            "type": "SOA",
            "records": [
                {"content": "dns1.europe. hostmaster.dns.europe. 1795131035 43200 7200 1 1"}
            ],
        }
    ]
    serial, content = soa_from_rrsets(rrsets)
    assert serial == 1795131035
    assert "1795131035" in (content or "")
    assert needs_zone_rebuild(2026112001, 1795131035) is True
    assert needs_zone_rebuild(100, 200) is False
    assert needs_zone_rebuild(None, 200) is False
