"""Background sync job (RQ) for the PowerDNS connector."""

from __future__ import annotations

import time

from django.utils import timezone
from netbox.jobs import JobRunner

from .models import PowerDNSSyncConfig
from .reconciler import reconcile_config


class SyncJob(JobRunner):
    class Meta:
        name = "PowerDNS Sync"

    def run(self, *args, **kwargs):
        cfg = PowerDNSSyncConfig.get_solo()
        started = time.monotonic()
        try:
            result = reconcile_config(cfg)
            duration = time.monotonic() - started
            errors = int(result.get("errors", 0))
            status = "success" if errors == 0 else "error"
            message = "; ".join(result.get("messages", [])[:5])[:2000]
            if not message and status == "success":
                message = (
                    f"Synced {result.get('zones', 0)} zones, "
                    f"{result.get('rrsets', 0)} rrsets, "
                    f"pushed {result.get('pushed', 0)}"
                )
            PowerDNSSyncConfig.objects.filter(pk=cfg.pk).update(
                last_status=status,
                last_message=message,
                last_run_at=timezone.now(),
                last_duration_seconds=duration,
                last_stats_zones=result.get("zones", 0),
                last_stats_rrsets=result.get("rrsets", 0),
                last_stats_pushed=result.get("pushed", 0),
                last_stats_errors=errors,
            )
            if errors:
                self.logger.error("PowerDNS sync finished with %s error(s)", errors)
            else:
                self.logger.info(
                    "PowerDNS sync completed in %.1fs result=%s", duration, result
                )
            if cfg.sync_enabled and cfg.sync_interval:
                SyncJob.enqueue_once(instance=cfg, interval=int(cfg.sync_interval))
        except Exception as exc:
            duration = time.monotonic() - started
            PowerDNSSyncConfig.objects.filter(pk=cfg.pk).update(
                last_status="error",
                last_message=str(exc)[:2000],
                last_run_at=timezone.now(),
                last_duration_seconds=duration,
                last_stats_errors=1,
            )
            self.logger.error("PowerDNS sync failed: %s", exc)
            raise


def schedule_from_config(cfg: PowerDNSSyncConfig | None = None) -> None:
    cfg = cfg or PowerDNSSyncConfig.get_solo()
    if cfg.sync_enabled and cfg.sync_interval and cfg.primary_url:
        SyncJob.enqueue_once(instance=cfg, interval=int(cfg.sync_interval))


def enqueue_realtime(cfg: PowerDNSSyncConfig | None = None) -> None:
    """Debounced enqueue after netbox_dns changes."""
    cfg = cfg or PowerDNSSyncConfig.get_solo()
    if not cfg.realtime_sync or not cfg.sync_enabled:
        return
    if not cfg.primary_url or not cfg.get_api_key():
        return
    SyncJob.enqueue_once(instance=cfg, interval=1)