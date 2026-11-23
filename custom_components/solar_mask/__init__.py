"""Solar Mask - Custom integration for sun visibility through shading obstacles.

Provides sun-aware entities per named zone, each with its own horizon mask file.
"""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform

from .const import DOMAIN, CONF_ZONES, CONF_NAME, CONF_MASK_FILE, CONF_LATITUDE, CONF_LONGITUDE

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CARD_URL = "/solar_mask/solar-mask-card.js"

ZONE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_MASK_FILE): cv.string,
    vol.Optional(CONF_LATITUDE): cv.latitude,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.All(cv.ensure_list, [ZONE_SCHEMA])
}, extra=vol.ALLOW_EXTRA)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a zone configured through the Home Assistant UI."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a configured zone."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Solar Mask and register its dashboard card."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_URL,
                str(Path(__file__).parent / "www" / "solar-mask-card.js"),
                cache_headers=False,
            )
        ]
    )
    add_extra_js_url(hass, CARD_URL)

    if DOMAIN not in config:
        return True

    zones = config[DOMAIN]
    hass.data[DOMAIN] = {}

    for zone_cfg in zones:
        name = zone_cfg[CONF_NAME]
        mask_file = zone_cfg[CONF_MASK_FILE]
        latitude = zone_cfg.get(CONF_LATITUDE, hass.config.latitude)
        longitude = zone_cfg.get(CONF_LONGITUDE, hass.config.longitude)

        # Path.exists() is blocking I/O → executor
        file_exists = await hass.async_add_executor_job(Path(mask_file).exists)
        if not file_exists:
            _LOGGER.error(
                "[solar_mask] Mask file not found for zone '%s': %s", name, mask_file
            )
            continue

        hass.data[DOMAIN][name] = {
            CONF_NAME: name,
            CONF_MASK_FILE: mask_file,
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
        }
        _LOGGER.info("[solar_mask] Zone '%s' registered (mask: %s)", name, mask_file)

    if not hass.data[DOMAIN]:
        _LOGGER.warning("[solar_mask] No valid zones configured.")
        return True

    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True
