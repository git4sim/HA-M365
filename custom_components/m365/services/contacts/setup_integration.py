"""Do configuration setup."""

import logging

import probatio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .const_integration import (
    ATTR_CONFIG_ENTRY_ID,
    CONTACTS_DATA,
    CONTACTS_SEARCH_SCHEMA,
    DOMAIN,
    PLATFORMS,
)
from .services_integration import ContactServices

_LOGGER = logging.getLogger(__name__)

SERVICE_CONTACTS_SEARCH = "contacts_search"


async def async_do_setup(hass: HomeAssistant, entry: ConfigEntry, account):
    """Run the setup after we have everything configured.

    Upstream registered the action per config entry, so with several accounts
    the account set up last silently answered every call. The action is now
    registered once and dispatches on ``config_entry_id``.
    """

    _LOGGER.debug("Contacts setup - start")
    services = hass.data.setdefault(DOMAIN, {}).setdefault(CONTACTS_DATA, {})
    services[entry.entry_id] = ContactServices(hass, account)

    def _remove_services() -> None:
        services.pop(entry.entry_id, None)

    entry.async_on_unload(_remove_services)
    async_register_services(hass)
    _LOGGER.debug("Contacts setup - finish")
    return None, None, PLATFORMS


def async_register_services(hass: HomeAssistant) -> None:
    """Register the contacts actions (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_CONTACTS_SEARCH):
        return

    async def _async_contacts_search(call: ServiceCall):
        services = hass.data.get(DOMAIN, {}).get(CONTACTS_DATA, {})
        if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
            service = services.get(entry_id)
        elif len(services) == 1:
            service = next(iter(services.values()))
        else:
            service = None
        if service is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="contacts_entry_required",
            )
        return await service.async_contacts_search(call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONTACTS_SEARCH,
        _async_contacts_search,
        CONTACTS_SEARCH_SCHEMA.extend(
            {probatio.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
        ),
        SupportsResponse.ONLY,
    )
