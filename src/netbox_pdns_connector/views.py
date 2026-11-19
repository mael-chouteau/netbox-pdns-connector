from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from .forms import PowerDNSSyncConfigForm
from .jobs import SyncJob, schedule_from_config
from .models import PowerDNSSyncConfig
from .status import probe_powerdns, zone_detail_parity


class StatusView(PermissionRequiredMixin, TemplateView):
    template_name = "netbox_pdns_connector/status.html"
    permission_required = "netbox_pdns_connector.view_powerdnssyncconfig"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cfg = PowerDNSSyncConfig.get_solo()
        context.update(
            {
                "config": cfg,
                "live": probe_powerdns(cfg, with_zone_parity=True),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        cfg = PowerDNSSyncConfig.get_solo()
        action = request.POST.get("action")
        if action == "sync_now":
            SyncJob.enqueue(instance=cfg)
            messages.success(request, "PowerDNS sync job enqueued.")
        elif action == "test_connection":
            live = probe_powerdns(cfg, with_zone_parity=False)
            if live.error and not live.servers:
                messages.error(request, live.error)
            elif all(s.reachable for s in live.servers):
                parts = [
                    f"{s.label}: {s.version} ({s.zone_count} zones, {s.latency_ms} ms)"
                    for s in live.servers
                ]
                messages.success(request, "Connected — " + "; ".join(parts))
            else:
                for s in live.servers:
                    if not s.reachable:
                        messages.error(request, f"{s.label}: {s.error}")
        return redirect("plugins:netbox_pdns_connector:status")


class ZoneDetailView(PermissionRequiredMixin, View):
    permission_required = "netbox_pdns_connector.view_powerdnssyncconfig"
    template_name = "netbox_pdns_connector/zone_detail.html"

    def get(self, request, zone_id: int):
        from netbox_dns.models import Zone

        cfg = PowerDNSSyncConfig.get_solo()
        zone = get_object_or_404(Zone, pk=zone_id)
        if cfg.view_id and zone.view_id != cfg.view_id:
            messages.error(request, "Zone is outside the configured DNS view filter.")
            return redirect("plugins:netbox_pdns_connector:status")
        ctx = zone_detail_parity(cfg, zone)
        ctx["config"] = cfg
        return render(request, self.template_name, ctx)

    def post(self, request, zone_id: int):
        cfg = PowerDNSSyncConfig.get_solo()
        if request.POST.get("action") == "sync_now":
            SyncJob.enqueue(instance=cfg)
            messages.success(request, "PowerDNS sync job enqueued.")
        return redirect("plugins:netbox_pdns_connector:zone_detail", zone_id=zone_id)


class SettingsView(PermissionRequiredMixin, View):
    permission_required = "netbox_pdns_connector.change_powerdnssyncconfig"
    template_name = "netbox_pdns_connector/settings.html"

    def get(self, request):
        cfg = PowerDNSSyncConfig.get_solo()
        form = PowerDNSSyncConfigForm(instance=cfg)
        return render(
            request,
            self.template_name,
            {"form": form, "object": cfg, "interval_presets": (5, 15, 30, 60)},
        )

    def post(self, request):
        cfg = PowerDNSSyncConfig.get_solo()
        form = PowerDNSSyncConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            obj = form.save()
            messages.success(request, "Settings saved.")
            try:
                if obj.sync_enabled and obj.primary_url:
                    schedule_from_config(obj)
                    messages.info(
                        request,
                        f"Automatic sync scheduled every {obj.sync_interval} minutes.",
                    )
            except Exception as exc:
                messages.warning(request, f"Could not schedule sync job: {exc}")
            return redirect("plugins:netbox_pdns_connector:settings")
        return render(
            request,
            self.template_name,
            {"form": form, "object": cfg, "interval_presets": (5, 15, 30, 60)},
        )
