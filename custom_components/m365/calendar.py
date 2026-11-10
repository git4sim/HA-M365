"""Calendar platform (Calendar service)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .classes.config_entry import MS365ConfigEntry
from .classes.service_entry import MS365ServiceEntry
from .const import SERVICE_CALENDAR
from .services.calendar.calendar_integration import async_integration_setup_entry as async_setup_calendar


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MS365ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform for the enabled services."""
    services = entry.runtime_data.services
    if SERVICE_CALENDAR in services:
        await async_setup_calendar(hass, MS365ServiceEntry(entry, SERVICE_CALENDAR), async_add_entities)
