import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("extras", "0145_taggeditem_object_id_bigint"),
        # netbox-plugin-dns ships a squash, not 0001_initial
        ("netbox_dns", "0035_alter_dnsseckeytemplate_owner_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PowerDNSSyncConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("name", models.CharField(default="default", max_length=100, unique=True)),
                ("primary_url", models.CharField(blank=True, max_length=255)),
                ("secondary_url", models.CharField(blank=True, max_length=255)),
                ("server_id", models.CharField(default="localhost", max_length=100)),
                ("api_key_encrypted", models.TextField(blank=True)),
                ("sync_enabled", models.BooleanField(default=True)),
                ("sync_interval", models.PositiveIntegerField(default=15)),
                ("realtime_sync", models.BooleanField(default=True)),
                ("dry_run", models.BooleanField(default=False)),
                ("last_status", models.CharField(blank=True, choices=[("success", "Success"), ("error", "Error"), ("running", "Running"), ("", "Never run")], default="", max_length=20)),
                ("last_message", models.TextField(blank=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_duration_seconds", models.FloatField(blank=True, null=True)),
                ("last_stats_zones", models.PositiveIntegerField(default=0)),
                ("last_stats_rrsets", models.PositiveIntegerField(default=0)),
                ("last_stats_pushed", models.PositiveIntegerField(default=0)),
                ("last_stats_errors", models.PositiveIntegerField(default=0)),
                (
                    "view",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="+",
                        to="netbox_dns.view",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag"),
                ),
            ],
            options={
                "verbose_name": "PowerDNS sync configuration",
                "verbose_name_plural": "PowerDNS sync configurations",
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
    ]