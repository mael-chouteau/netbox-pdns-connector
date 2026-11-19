from django import forms
from netbox_dns.models import View
from utilities.forms.fields import DynamicModelChoiceField

from .models import PowerDNSSyncConfig


class PowerDNSSyncConfigForm(forms.ModelForm):
    api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "••••••••"}),
        label="PowerDNS API key",
        help_text="Leave blank to keep the current secret",
    )
    sync_interval = forms.IntegerField(
        min_value=1,
        max_value=10080,
        help_text="Minutes between automatic syncs (presets: 5 / 15 / 30 / 60)",
    )
    view = DynamicModelChoiceField(
        queryset=View.objects.all(),
        required=False,
        label="DNS view filter",
        help_text="Sync only zones in this view (empty = all views)",
    )

    class Meta:
        model = PowerDNSSyncConfig
        fields = (
            "primary_url",
            "secondary_url",
            "server_id",
            "view",
            "sync_enabled",
            "sync_interval",
            "realtime_sync",
            "dry_run",
        )

    def save(self, commit=True):
        obj = super().save(commit=False)
        api_key = self.cleaned_data.get("api_key")
        if api_key:
            obj.set_api_key(api_key)
        if commit:
            obj.save()
        return obj