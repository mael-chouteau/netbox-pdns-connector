# Changelog

## 0.1.3 — 2026-11-20

- Docs: remove Screenshots placeholder and opennebula from related projects; keep maintainer-only catalog notes out of the public repo.

## 0.1.2 — 2026-11-20

- Create/update zones with `soa_edit_api=NONE` (PowerDNS `DEFAULT` was rewriting serials to `YYYYMMDDNN`).
- If an existing PowerDNS SOA serial is still higher than NetBox, delete/recreate the zone then re-push.

## 0.1.1 — 2026-11-20

- Live Status: zone table with NetBox ↔ dns1/dns2 SOA serial parity badges.
- Read-only zone detail page listing active netbox_dns records (edit still in Plugins → DNS).
- Helpers for SOA serial parsing / RRset counts; fix trailing-slash 404 on `/servers/{id}`.

## 0.1.0 — 2026-11-19

- Initial release: netbox_dns → PowerDNS Native zone sync (primary + secondary).
- Live Status and Settings UI, RQ `SyncJob`, realtime signals, pytest RRset tests.