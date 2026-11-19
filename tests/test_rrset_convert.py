"""RRset conversion and idempotence tests."""

from netbox_pdns_connector.rrset_convert import (
    SimpleRecord,
    build_rrsets,
    canonical_fqdn,
    format_txt_value,
    record_content,
    rrsets_fingerprint,
)


def test_canonical_trailing_dot_apex():
    assert canonical_fqdn("@", "example.com") == "example.com."
    assert canonical_fqdn("www", "example.com") == "www.example.com."
    assert canonical_fqdn("www.example.com.", "example.com") == "www.example.com."


def test_txt_quoting():
    assert format_txt_value("hello") == '"hello"'
    assert format_txt_value('say "hi"') == '"say \\"hi\\""'
    assert format_txt_value('"already"') == '"already"'


def test_mx_priority():
    assert record_content("MX", "10 mail.example.com") == "10 mail.example.com."
    assert record_content("MX", "5 smtp.example.com.") == "5 smtp.example.com."


def test_build_rrsets_groups_and_sorts():
    records = [
        SimpleRecord("www", "A", "203.0.113.10", ttl=300),
        SimpleRecord("www", "A", "203.0.113.11", ttl=300),
        SimpleRecord("@", "TXT", "v=spf1 -all", ttl=60),
    ]
    rrsets = build_rrsets("example.com", records, default_ttl=3600)
    by_type = {(r["name"], r["type"]): r for r in rrsets}
    a_rrset = by_type[("www.example.com.", "A")]
    assert len(a_rrset["records"]) == 2
    assert a_rrset["ttl"] == 300
    txt = by_type[("example.com.", "TXT")]
    assert txt["records"][0]["content"].startswith('"')


def test_fingerprint_idempotent():
    records = [
        SimpleRecord("host", "AAAA", "2001:db8::1"),
        SimpleRecord("host", "A", "203.0.113.1"),
    ]
    first = build_rrsets("example.com", records)
    second = build_rrsets("example.com", list(reversed(records)))
    assert rrsets_fingerprint(first) == rrsets_fingerprint(second)


def test_inactive_records_skipped():
    records = [
        SimpleRecord("x", "A", "203.0.113.1", status="inactive"),
        SimpleRecord("y", "A", "203.0.113.2", status="active"),
    ]
    rrsets = build_rrsets("example.com", records)
    names = {r["name"] for r in rrsets}
    assert "x.example.com." not in names
    assert "y.example.com." in names