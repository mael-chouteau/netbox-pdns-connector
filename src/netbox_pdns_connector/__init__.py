"""Push netbox_dns zones and records to PowerDNS Authoritative API v1."""

__version__ = "0.1.2"

try:
    from netbox.plugins import PluginConfig
except ImportError:  # Standalone / unit tests without NetBox
    config = None
else:

    class PowerDNSConnectorConfig(PluginConfig):
        name = "netbox_pdns_connector"
        verbose_name = "PowerDNS"
        description = "Synchronize netbox_dns zones to PowerDNS Authoritative servers"
        version = __version__
        author = "NetBox PowerDNS Connector contributors"
        author_email = "dev@localhost"
        base_url = "powerdns"
        min_version = "4.2"
        default_settings = {}
        required_settings = []

        def ready(self):
            super().ready()
            from . import (
                jobs,  # noqa: F401
                signals,  # noqa: F401
            )

    config = PowerDNSConnectorConfig