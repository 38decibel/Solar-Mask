"""Sensor platform for Solar Mask integration.

Per zone:
  sensor.<zone>_sun_effective_elevation — analogue to sun.elevation, masked (°)
  sensor.<zone>_sun_start               — today's first sunlit moment (timestamp)
  sensor.<zone>_sun_end                 — today's last sunlit moment (timestamp)
  sensor.<zone>_sun_duration            — total sunlit minutes today
  sensor.<zone>_solar_diagram           — JSON series for ApexCharts-card diagram
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime, DEGREE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, CONF_MASK_FILE, CONF_LATITUDE, CONF_LONGITUDE, UPDATE_INTERVAL
from .solar_engine import SolarMask

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up sensors for all configured zones."""
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

        entities += [
            EffectiveElevationSensor(hass, zone_name, mask),
            SunStartSensor(hass, zone_name, mask),
            SunEndSensor(hass, zone_name, mask),
            SunDurationSensor(hass, zone_name, mask),
            SolarDiagramSensor(hass, zone_name, mask),
        ]

    async_add_entities(entities, update_before_add=True)


def _ha_timezone(hass: HomeAssistant) -> ZoneInfo:
    """Return HA timezone as a ZoneInfo (no blocking I/O)."""
    return ZoneInfo(hass.config.time_zone)


def _to_key(label: str) -> str:
    """Convert a series label to a safe attribute key."""
    return (label.lower()
            .replace("'", "").replace("'", "")
            .replace(" ", "_").replace(".", "")
            .replace("é", "e").replace("è", "e").replace("ê", "e")
            .replace("î", "i").replace("ô", "o")
            .replace("û", "u").replace("à", "a"))


def _utc_offset_hours(hass: HomeAssistant) -> float:
    """Return current UTC offset in hours for HA timezone (no blocking I/O)."""
    tz = _ha_timezone(hass)
    now_local = datetime.now(tz)
    return now_local.utcoffset().total_seconds() / 3600


class _BaseSolarSensor(SensorEntity):
    """Base class for solar mask sensors."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, zone_name: str, mask: SolarMask):
        self._zone_name = zone_name
        self._mask = mask
        self._hass = hass

    async def async_added_to_hass(self):
        await self._async_do_update()
        async_track_time_interval(
            self.hass,
            self._async_interval_update,
            timedelta(minutes=UPDATE_INTERVAL),
        )

    async def _async_interval_update(self, now=None):
        await self._async_do_update()
        self.async_write_ha_state()

    async def _async_do_update(self):
        raise NotImplementedError


class EffectiveElevationSensor(_BaseSolarSensor):
    """Effective solar elevation = sun elevation − mask elevation at current azimuth."""

    _attr_native_unit_of_measurement = DEGREE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weather-sunny"

    def __init__(self, hass, zone_name, mask):
        super().__init__(hass, zone_name, mask)
        self._attr_name = f"{zone_name} sun effective elevation"
        self._attr_unique_id = f"solar_mask_{zone_name}_sun_effective_elevation"
        self._attr_native_value = None

    async def _async_do_update(self):
        now_utc = datetime.now(tz=timezone.utc)
        eff, az, elev, mask_elev = self._mask.effective_elevation(now_utc)
        self._attr_native_value = round(eff, 2)
        self._attr_extra_state_attributes = {
            "sun_azimuth": round(az, 2),
            "sun_elevation": round(elev, 2),
            "mask_elevation": round(mask_elev, 2),
            "zone": self._zone_name,
        }


class _DailyCacheMixin:
    """Mixin that recomputes daily windows once per day via executor."""

    _last_computed_day: date | None = None
    _daily_cache: dict

    async def _refresh_daily_cache(self):
        today = datetime.now().date()
        if today != self._last_computed_day:
            utc_off = _utc_offset_hours(self._hass)
            self._daily_cache = await self._hass.async_add_executor_job(
                self._mask.compute_daily_windows, today, utc_off
            )
            self._last_computed_day = today


class SunStartSensor(_DailyCacheMixin, _BaseSolarSensor):
    """Time of first sunlit moment today."""

    _attr_icon = "mdi:weather-sunset-up"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hass, zone_name, mask):
        _BaseSolarSensor.__init__(self, hass, zone_name, mask)
        self._attr_name = f"{zone_name} sun start"
        self._attr_unique_id = f"solar_mask_{zone_name}_sun_start"
        self._attr_native_value = None
        self._daily_cache = {}

    async def _async_do_update(self):
        await self._refresh_daily_cache()
        start = self._daily_cache.get("sun_start")
        if start:
            tz = _ha_timezone(self._hass)
            self._attr_native_value = start.replace(tzinfo=tz)
        else:
            self._attr_native_value = None


class SunEndSensor(_DailyCacheMixin, _BaseSolarSensor):
    """Time of last sunlit moment today."""

    _attr_icon = "mdi:weather-sunset-down"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hass, zone_name, mask):
        _BaseSolarSensor.__init__(self, hass, zone_name, mask)
        self._attr_name = f"{zone_name} sun end"
        self._attr_unique_id = f"solar_mask_{zone_name}_sun_end"
        self._attr_native_value = None
        self._daily_cache = {}

    async def _async_do_update(self):
        await self._refresh_daily_cache()
        end = self._daily_cache.get("sun_end")
        if end:
            tz = _ha_timezone(self._hass)
            self._attr_native_value = end.replace(tzinfo=tz)
        else:
            self._attr_native_value = None


class SunDurationSensor(_DailyCacheMixin, _BaseSolarSensor):
    """Total sunlit minutes today."""

    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:sun-clock"

    def __init__(self, hass, zone_name, mask):
        _BaseSolarSensor.__init__(self, hass, zone_name, mask)
        self._attr_name = f"{zone_name} sun duration"
        self._attr_unique_id = f"solar_mask_{zone_name}_sun_duration"
        self._attr_native_value = 0
        self._daily_cache = {}

    async def _async_do_update(self):
        await self._refresh_daily_cache()
        self._attr_native_value = self._daily_cache.get("duration_minutes", 0)
        self._attr_extra_state_attributes = {
            "windows": [
                {"start": w[0].strftime("%H:%M"), "end": w[1].strftime("%H:%M")}
                for w in self._daily_cache.get("windows", [])
            ],
            "zone": self._zone_name,
        }


# ---------------------------------------------------------------------------
# Diagram sensor
# ---------------------------------------------------------------------------

def _compute_sun_path(mask: "SolarMask", day: date, lat: float, lon: float) -> list[dict]:
    """Compute sun azimuth/elevation pairs for a full day (5-min steps, daylight only)."""
    from .solar_engine import _sun_position
    points = []
    for minute in range(0, 24 * 60, 5):
        h, m = divmod(minute, 60)
        utc_dt = datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)
        az, elev = _sun_position(lat, lon, utc_dt)
        if elev > -1:  # include slightly below horizon for curve continuity
            points.append({"x": round(az, 1), "y": round(elev, 1)})
    return points


def _compute_diagram_data(mask: "SolarMask") -> dict:
    """Build all series for the solar diagram (blocking — run via executor)."""
    from datetime import date
    import calendar

    lat = mask.latitude
    lon = mask.longitude
    today = date.today()
    year = today.year

    # Representative days
    days = {
        "Solstice été": date(year, 6, 21),
        "Équinoxe mars": date(year, 3, 20),
        "Équinoxe sept.": date(year, 9, 23),
        "Solstice hiver": date(year, 12, 21),
        "Aujourd'hui": today,
    }

    series = {}
    for label, day in days.items():
        series[label] = _compute_sun_path(mask, day, lat, lon)

    # Mask series: list of {x: azimuth, y: mask_elevation}
    mask_points = [
        {"x": round(az, 1), "y": round(el, 1)}
        for az, el in zip(mask._azimuths, mask._elevations)
    ]
    # Close the polygon at y=0 for area fill
    if mask_points:
        mask_points = (
            [{"x": 0.0, "y": 0.0}]
            + mask_points
            + [{"x": 360.0, "y": mask_points[-1]["y"]}, {"x": 360.0, "y": 0.0}]
        )

    return {"sun_paths": series, "mask": mask_points}


class SolarDiagramSensor(_BaseSolarSensor):
    """Sensor exposing solar diagram data as attributes for ApexCharts-card."""

    _attr_icon = "mdi:chart-bell-curve"
    _attr_entity_registry_enabled_default = True

    def __init__(self, hass, zone_name, mask):
        super().__init__(hass, zone_name, mask)
        self._attr_name = f"{zone_name} solar diagram"
        self._attr_unique_id = f"solar_mask_{zone_name}_solar_diagram"
        self._attr_native_value = "ok"
        self._diagram_data: dict = {}
        self._last_diagram_day: date | None = None

    async def _async_do_update(self):
        today = datetime.now().date()
        # Recompute daily (today's path changes every day)
        if today != self._last_diagram_day:
            self._diagram_data = await self._hass.async_add_executor_job(
                _compute_diagram_data, self._mask
            )
            self._last_diagram_day = today

        self._attr_extra_state_attributes = {
            "mask": self._diagram_data.get("mask", []),
            **{
                f"path_{_to_key(label)}": pts
                for label, pts in self._diagram_data.get("sun_paths", {}).items()
            },
        }
