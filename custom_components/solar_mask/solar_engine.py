"""Solar mask computation engine.

Loads a horizon mask file (CSV or HOR format from Azimutis/PVsyst/PVGIS)
and provides sun visibility calculations for any location and datetime.

Mask file format (CSV):
    azimuth,elevation
    0,5.2
    10,8.1
    ...
    350,4.5

HOR format (PVsyst / Azimutis export) is also supported:
    Lines starting with '#' are comments.
    Data lines: <azimuth> <elevation>

IMPORTANT: _load_mask() does blocking I/O — always call load() via
hass.async_add_executor_job() from async context.
"""

from __future__ import annotations

import csv
import io
import logging
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


def _sun_position(lat: float, lon: float, dt: datetime) -> tuple[float, float]:
    """Compute solar azimuth and elevation (degrees) for a given UTC datetime.

    Uses the Spencer/Grena algorithm.
    Azimuth: 0=N, 90=E, 180=S, 270=W (meteorological convention).
    """
    jd = _datetime_to_julian(dt)
    T = (jd - 2451545.0) / 36525.0

    L0 = (280.46646 + 36000.76983 * T + 0.0003032 * T**2) % 360
    M = (357.52911 + 35999.05029 * T - 0.0001537 * T**2) % 360
    M_rad = math.radians(M)

    C = ((1.914602 - 0.004817 * T - 0.000014 * T**2) * math.sin(M_rad)
         + (0.019993 - 0.000101 * T) * math.sin(2 * M_rad)
         + 0.000289 * math.sin(3 * M_rad))

    sun_lon = L0 + C
    omega = 125.04 - 1934.136 * T
    apparent_lon = sun_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    apparent_lon_rad = math.radians(apparent_lon)

    epsilon0 = (23 + 26/60 + 21.448/3600
                - (46.8150/3600) * T
                - (0.00059/3600) * T**2
                + (0.001813/3600) * T**3)
    epsilon = epsilon0 + 0.00256 * math.cos(math.radians(omega))
    epsilon_rad = math.radians(epsilon)

    dec_rad = math.asin(math.sin(epsilon_rad) * math.sin(apparent_lon_rad))
    ra = math.atan2(
        math.cos(epsilon_rad) * math.sin(apparent_lon_rad),
        math.cos(apparent_lon_rad)
    )

    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
            + 0.000387933 * T**2 - T**3 / 38710000.0) % 360

    lha = math.radians((gmst + lon - math.degrees(ra)) % 360)
    lat_rad = math.radians(lat)

    sin_elev = (math.sin(lat_rad) * math.sin(dec_rad)
                + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(lha))
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))

    cos_az = ((math.sin(dec_rad) - math.sin(lat_rad) * sin_elev)
              / (math.cos(lat_rad) * math.cos(math.asin(max(-1.0, min(1.0, sin_elev)))) + 1e-10))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.acos(cos_az))
    if math.sin(lha) > 0:
        az = 360 - az

    return az, elevation


def _datetime_to_julian(dt: datetime) -> float:
    """Convert a UTC datetime to Julian Day Number."""
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = (dt.day + (153 * m + 2) // 5 + 365 * y + y // 4
           - y // 100 + y // 400 - 32045)
    return jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0


class SolarMask:
    """Represents a horizon mask and provides sun visibility computations.

    Usage in async HA context:
        mask = SolarMask(...)
        await hass.async_add_executor_job(mask.load)
    """

    def __init__(self, mask_file: str, latitude: float, longitude: float, name: str = ""):
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self._mask_file = mask_file
        self._azimuths: list[float] = []
        self._elevations: list[float] = []

    def load(self) -> None:
        """Load the mask file synchronously. Always call via executor_job."""
        self._load_mask()

    def _load_mask(self) -> None:
        """Parse CSV or HOR horizon mask file."""
        path = Path(self._mask_file)
        azimuths: list[float] = []
        elevations: list[float] = []

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            lines = [l.strip() for l in content.splitlines() if l.strip()]
            data_lines = [l for l in lines if not l.startswith("#")]

            if not data_lines:
                raise ValueError("Mask file contains no data")

            first = data_lines[0]
            if "," in first:
                # CSV format
                reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
                for row in reader:
                    keys = list(row.keys())
                    try:
                        az = float(row.get("azimuth", row.get("Azimuth", row[keys[0]])))
                        el = float(row.get("elevation", row.get("Elevation", row[keys[1]])))
                        azimuths.append(az % 360)
                        elevations.append(el)
                    except (ValueError, KeyError):
                        continue
            else:
                # HOR / space-separated format
                for line in data_lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            azimuths.append(float(parts[0]) % 360)
                            elevations.append(float(parts[1]))
                        except ValueError:
                            continue

            if not azimuths:
                raise ValueError("No valid azimuth/elevation pairs found")

            paired = sorted(zip(azimuths, elevations), key=lambda x: x[0])
            self._azimuths = [p[0] for p in paired]
            self._elevations = [p[1] for p in paired]

            _LOGGER.info(
                "[solar_mask] Zone '%s': loaded %d mask points from %s",
                self.name, len(self._azimuths), self._mask_file,
            )

        except Exception as e:
            _LOGGER.error("[solar_mask] Failed to load mask for '%s': %s", self.name, e)
            self._azimuths = [0.0, 360.0]
            self._elevations = [0.0, 0.0]

    def mask_elevation_at(self, azimuth: float) -> float:
        """Linear interpolation of mask elevation at given azimuth (with 360° wraparound)."""
        az = azimuth % 360
        xs = self._azimuths
        ys = self._elevations
        n = len(xs)

        if n == 0:
            return 0.0
        if n == 1:
            return ys[0]

        if az <= xs[0] or az >= xs[-1]:
            x0, y0 = xs[-1], ys[-1]
            x1, y1 = xs[0] + 360.0, ys[0]
            t = az if az >= xs[-1] else az + 360.0
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (t - x0) / (x1 - x0)

        lo, hi = 0, n - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if xs[mid] <= az:
                lo = mid
            else:
                hi = mid

        x0, y0 = xs[lo], ys[lo]
        x1, y1 = xs[hi], ys[hi]
        if x1 == x0:
            return y0
        return y0 + (y1 - y0) * (az - x0) / (x1 - x0)

    def effective_elevation(self, dt: datetime) -> tuple[float, float, float, float]:
        """Return (effective_elevation, sun_azimuth, sun_elevation, mask_elevation).

        effective_elevation > 0 means the sun is visible above the mask.
        """
        az, elev = _sun_position(self.latitude, self.longitude, dt)
        mask_elev = self.mask_elevation_at(az)
        return elev - mask_elev, az, elev, mask_elev

    def is_sunlit(self, dt: datetime) -> bool:
        """True if the sun is above the horizon mask at the given UTC datetime."""
        eff, _, _, _ = self.effective_elevation(dt)
        return eff > 0

    def compute_daily_windows(self, day: date, utc_offset_hours: float = 0.0) -> dict:
        """Compute sunlit windows for a full day (blocking, run via executor).

        Returns:
            sun_start: local datetime of first sunlit moment, or None
            sun_end:   local datetime of last sunlit moment, or None
            duration_minutes: total sunlit minutes
            windows: list of (start, end) local datetime tuples
        """
        tz_offset = timedelta(hours=utc_offset_hours)
        step_minutes = 5
        samples: list[tuple[datetime, bool]] = []

        for minute in range(0, 24 * 60, step_minutes):
            h, m = divmod(minute, 60)
            local_naive = datetime(day.year, day.month, day.day, h, m)
            utc_dt = datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc) - tz_offset
            eff, _, _, _ = self.effective_elevation(utc_dt)
            samples.append((local_naive, eff > 0))

        windows: list[tuple[datetime, datetime]] = []
        in_sun = False
        window_start: datetime | None = None
        duration = 0

        for local_dt, lit in samples:
            if lit and not in_sun:
                window_start = local_dt
                in_sun = True
            elif not lit and in_sun:
                windows.append((window_start, local_dt))  # type: ignore[arg-type]
                in_sun = False
            if lit:
                duration += step_minutes

        if in_sun and window_start:
            windows.append((window_start, samples[-1][0]))

        return {
            "sun_start": windows[0][0] if windows else None,
            "sun_end": windows[-1][1] if windows else None,
            "duration_minutes": duration,
            "windows": windows,
        }
