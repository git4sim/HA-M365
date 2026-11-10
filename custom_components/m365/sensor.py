"""Sensor platform (Mail and Teams services)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .classes.config_entry import MS365ConfigEntry
from .classes.service_entry import MS365ServiceEntry
from .const import SERVICE_MAIL, SERVICE_TEAMS
from .services.mail.sensor_integration import async_integration_setup_entry as async_setup_mail
from .services.teams.sensor_integration import async_integration_setup_entry as async_setup_teams


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MS365ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform for the enabled services."""
    services = entry.runtime_data.services
    if SERVICE_MAIL in services:
        await async_setup_mail(hass, MS365ServiceEntry(entry, SERVICE_MAIL), async_add_entities)
    if SERVICE_TEAMS in services:
        await async_setup_teams(hass, MS365ServiceEntry(entry, SERVICE_TEAMS), async_add_entities)
