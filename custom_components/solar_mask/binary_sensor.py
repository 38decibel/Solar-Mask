"""Binary sensor platform for Solar Mask integration.

Per zone:
  binary_sensor.<zone>_sunlit
    ON  = sun is currently visible above the horizon mask
    OFF = zone is in shadow
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_MASK_FILE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    ATTR_EFFECTIVE_ELEVATION,
    ATTR_SUN_AZIMUTH,
    ATTR_SUN_ELEVATION,
    ATTR_MASK_ELEVATION,
    UPDATE_INTERVAL,
)
from .solar_engine import SolarMask

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up binary sensors for all configured zones."""
    if DOMAIN not in hass.data:
        return

    entities = []
    for zone_name, zone_cfg in hass.data[DOMAIN].items():
        mask = SolarMask(
            mask_file=zone_cfg[CONF_MASK_FILE],
            latitude=zone_cfg[CONF_LATITUDE],
            longitude=zone_cfg[CONF_LONGITUDE],
            name=zone_name,
        )
        # Blocking file I/O → executor
        await hass.async_add_executor_job(mask.load)
        entities.append(SolarMaskBinarySensor(hass, zone_name, mask))

    async_add_entities(entities, update_before_add=True)


class SolarMaskBinarySensor(BinarySensorEntity):
    """Binary sensor: is the zone currently sunlit?"""

    _attr_device_class = BinarySensorDeviceClass.LIGHT
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, zone_name: str, mask: SolarMask):
        self._zone_name = zone_name
        self._mask = mask
        self._attr_name = f"{zone_name} sunlit"
        self._attr_unique_id = f"solar_mask_{zone_name}_sunlit"
        self._attr_is_on = False
        self._eff_elev = 0.0
        self._sun_az = 0.0
        self._sun_elev = 0.0
        self._mask_elev = 0.0

    async def async_added_to_hass(self):
        self._update()
        async_track_time_interval(
            self.hass,
            self._async_interval_update,
            timedelta(minutes=UPDATE_INTERVAL),
        )

    async def _async_interval_update(self, now=None):
        self._update()
        self.async_write_ha_state()

    def _update(self):
        now_utc = datetime.now(tz=timezone.utc)
        eff, az, elev, mask_elev = self._mask.effective_elevation(now_utc)
        self._attr_is_on = eff > 0
        self._eff_elev = round(eff, 2)
        self._sun_az = round(az, 2)
        self._sun_elev = round(elev, 2)
        self._mask_elev = round(mask_elev, 2)

    @property
    def extra_state_attributes(self):
        return {
            ATTR_EFFECTIVE_ELEVATION: self._eff_elev,
            ATTR_SUN_AZIMUTH: self._sun_az,
            ATTR_SUN_ELEVATION: self._sun_elev,
            ATTR_MASK_ELEVATION: self._mask_elev,
            "zone": self._zone_name,
        }
