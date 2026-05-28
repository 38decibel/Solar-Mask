"""Constants for the Solar Mask integration."""

DOMAIN = "solar_mask"

CONF_ZONES = "zones"
CONF_NAME = "name"
CONF_MASK_FILE = "mask_file"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"

# Update interval in minutes
UPDATE_INTERVAL = 5

# Resolution in degrees for daily sun/mask calculations
AZIMUTH_STEP = 1.0

ATTR_EFFECTIVE_ELEVATION = "effective_elevation"
ATTR_SUN_AZIMUTH = "sun_azimuth"
ATTR_SUN_ELEVATION = "sun_elevation"
ATTR_MASK_ELEVATION = "mask_elevation_at_azimuth"
