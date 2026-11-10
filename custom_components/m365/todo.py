"""To Do platform (To Do service)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .classes.config_entry import MS365ConfigEntry
from .classes.service_entry import MS365ServiceEntry
from .const import SERVICE_TODO
from .services.todo.todo_integration import async_todo_integration_setup_entry as async_setup_todo


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MS365ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the todo platform for the enabled services."""
    services = entry.runtime_data.services
    if SERVICE_TODO in services:
        await async_setup_todo(hass, MS365ServiceEntry(entry, SERVICE_TODO), async_add_entities)
