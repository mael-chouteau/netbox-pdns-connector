from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label="PowerDNS",
    icon_class="mdi mdi-dns",
    groups=(
        (
            "Sync",
            (
                PluginMenuItem(
                    link="plugins:netbox_pdns_connector:status",
                    link_text="Live Status",
                    permissions=["netbox_pdns_connector.view_powerdnssyncconfig"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_pdns_connector:settings",
                    link_text="Settings",
                    permissions=["netbox_pdns_connector.change_powerdnssyncconfig"],
                ),
            ),
        ),
    ),
)