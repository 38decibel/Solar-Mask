"""Device metadata shared by a zone's entities."""

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def solar_mask_device_info(zone_name: str) -> DeviceInfo:
    """Return stable device information for a Solar Mask zone."""
    return DeviceInfo(
        identifiers={(DOMAIN, zone_name.casefold())},
        name=zone_name,
        manufacturer="Solar Mask",
        model="Sun visibility zone",
    )
