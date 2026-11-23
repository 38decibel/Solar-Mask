"""Config flow for Solar Mask."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MASK_DATA,
    CONF_NAME,
    DOMAIN,
)
from .solar_engine import parse_mask_data


class SolarMaskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Solar Mask zone."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Collect zone details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            mask_data = user_input[CONF_MASK_DATA].strip()

            if not name:
                errors[CONF_NAME] = "invalid_name"
            else:
                try:
                    parse_mask_data(mask_data)
                except ValueError:
                    errors[CONF_MASK_DATA] = "invalid_mask"
                else:
                    await self.async_set_unique_id(name.casefold())
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=name,
                        data={
                            CONF_NAME: name,
                            CONF_MASK_DATA: mask_data,
                            CONF_LATITUDE: user_input[CONF_LATITUDE],
                            CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_MASK_DATA): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): cv.latitude,
                vol.Optional(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): cv.longitude,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "mask_example": "azimuth,elevation; 0,3.5; 30,5.2"
            },
        )
