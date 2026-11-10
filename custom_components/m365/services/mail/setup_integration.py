"""Do configuration setup."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from ...const import CONF_ENABLE_UPDATE
from .const_integration import CONF_ENTRY, DOMAIN, PLATFORMS, SUBENTRY_MAIL
from .coordinator_integration import MS365SensorCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_do_setup(hass: HomeAssistant, entry: ConfigEntry, account):
    """Run the setup after we have everything configured."""

    _LOGGER.debug("Sensor setup - start")
    coordinators, keys = await _async_setup_coordinators(
        hass,
        account,
        entry,
    )
    _LOGGER.debug("Email setup - finish")
    return coordinators, keys, PLATFORMS


async def _async_setup_coordinators(hass: HomeAssistant, account, entry: ConfigEntry):
    coordinators = []
    keys = []
    autoreply = True
    for subentry in entry.get_subentries_of_type(SUBENTRY_MAIL):
        email_coordinator = MS365SensorCoordinator(
            hass, entry, subentry, account, autoreply
        )
        await email_coordinator.async_config_entry_first_refresh()
        coordinators.append(email_coordinator)
        keys.append(email_coordinator.keys)
        autoreply = False
    return coordinators, keys


async def async_extra_platform_setup(hass: HomeAssistant, entry: ConfigEntry):
    """Create notify platform."""

    if entry.data[CONF_ENABLE_UPDATE]:
        hass.async_create_task(
            discovery.async_load_platform(
                hass,
                "notify",
                DOMAIN,
                {CONF_ENTRY: entry},
                {},
            )
        )
