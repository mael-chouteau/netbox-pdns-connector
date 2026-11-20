# netbox-pdns-connector

[![CI](https://github.com/mael-chouteau/netbox-pdns-connector/actions/workflows/ci.yml/badge.svg)](https://github.com/mael-chouteau/netbox-pdns-connector/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/netbox-pdns-connector.svg)](https://pypi.org/project/netbox-pdns-connector/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![NetBox](https://img.shields.io/badge/NetBox-4.2%2B-green.svg)](https://github.com/netbox-community/netbox)

NetBox Community plugin that pushes **active** DNS zones and records from
[`netbox_dns`](https://github.com/sys4/netbox-plugin-dns) to one or two
**PowerDNS Authoritative** servers via the REST API v1.

This plugin is a **connector only**: it does **not** store zones or records.
Edit DNS data in **Plugins → DNS** (`netbox_dns`); this plugin syncs that data
to PowerDNS and shows live health / SOA serial parity.

Ideal for operators who already use NetBox + `netbox_dns` as the DNS source of
truth and want PowerDNS (single node or HA pair) as the serving plane.

## Features

| Area | What you get |
|------|----------------|
| **UI** | Plugins → PowerDNS → **Live Status** (API probe + zone SOA parity) + zone detail (read-only) + **Settings** |
| **Sync** | RQ job: *Sync now*, configurable interval, optional realtime on `netbox_dns` changes |
| **Targets** | Primary and optional secondary PowerDNS API URLs (shared API key supported) |
| **Push model** | Native zones; atomic RRset REPLACE; orphan RRset DELETE; `soa_edit_api=NONE` so NetBox owns SOA serials |
| **Safety** | Dry-run mode, Fernet-encrypted API key (Django `SECRET_KEY`), optional DNS view filter |

Compatible with **NetBox 4.2+** (tested on **4.7**). License: **Apache-2.0**.

## Requirements

- NetBox 4.2 or newer with **netbox-rq** running
- [`netbox-plugin-dns`](https://github.com/sys4/netbox-plugin-dns) installed and migrated
- PowerDNS Authoritative with **API** enabled (`api=yes`, `webserver=yes`)
- Python 3.11+

## Installation

```bash
/opt/netbox/venv/bin/pip install netbox-pdns-connector
```

Add to `/opt/netbox/local_requirements.txt` for upgrades:

```text
netbox-pdns-connector
```

In `configuration.py`:

```python
PLUGINS = [
    'netbox_dns',
    'netbox_pdns_connector',
]
```

```bash
sudo -u netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate netbox_pdns_connector
sudo systemctl restart netbox netbox-rq
```

1. Open **Plugins → PowerDNS → Settings**
2. Set primary (and optional secondary) API base URL, e.g. `http://dns1.example:8081`
3. Paste the PowerDNS API key (stored encrypted)
4. Optionally restrict sync to one `netbox_dns` **View**
5. Save, then **Live Status → Sync now**

The client appends `/api/v1`. Do **not** put a trailing slash on `/servers/localhost`
paths (PowerDNS returns 404).

## Configuration reference

| Setting | Description |
|---------|-------------|
| Primary / secondary URL | PowerDNS REST base (`http://host:8081`) |
| Server id | PowerDNS API server name (usually `localhost`) |
| API key | Shared secret; Fernet-encrypted at rest |
| View | Limit sync to one `netbox_dns` view (empty = all) |
| Sync interval | Minutes between automatic RQ runs |
| Realtime sync | Enqueue sync on zone/record save/delete |
| Dry run | Compute push without calling PowerDNS |

### PowerDNS side tips

- Restrict `webserver-allow-from` to your NetBox host
- Firewall API port (e.g. 8081) accordingly
- Zones are created as **Native** with `soa_edit` / `soa_edit_api` = **NONE** so NetBox SOA serials are preserved (PowerDNS `DEFAULT` would rewrite them to `YYYYMMDDNN`)
- For HA, point primary + secondary at both Authoritative nodes and use the same API key if your plugin config has a single key field

## Operations

- **Live Status**: server reachability, version, zone count, per-zone SOA parity (`in sync` / `drift` / `unreachable`)
- **Zone detail**: read-only list of active `netbox_dns` records + Sync now
- Edit records only under **Plugins → DNS**

### Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `404` on `/servers/localhost/` | Trailing slash — fixed in recent releases; upgrade the plugin |
| Persistent SOA **drift** | Zone still has `SOA-EDIT-API=DEFAULT`; Sync with 0.1.2+ recreates with `NONE` |
| Connection timeout | Firewall / `webserver-allow-from` does not include NetBox |

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -q
```

## Related projects

- [`netbox-plugin-dns`](https://github.com/sys4/netbox-plugin-dns) — DNS data model & IPAM DNSsync in NetBox

## License

Apache License 2.0 — see [LICENSE](LICENSE).
