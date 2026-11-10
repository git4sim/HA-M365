"""Permissions for the unified M365 integration."""

from copy import deepcopy

from homeassistant.core import HomeAssistant

from .classes.permissions import BasePermissions
from .classes.service_entry import build_service_data, enabled_services
from .const import PERM_BASE_PERMISSIONS
from .services import SERVICE_DEFINITIONS


class Permissions(BasePermissions):
    """Union of the Graph permissions required by all enabled services."""

    def __init__(self, hass: HomeAssistant, config, token_backend) -> None:
        """Initialise the class."""
        super().__init__(hass, config, token_backend)
        self._services = enabled_services(config)

    @property
    def requested_permissions(self):
        """Return the required scope."""
        if not self._requested_permissions:
            requested = deepcopy(PERM_BASE_PERMISSIONS)
            for name in self._services:
                service = SERVICE_DEFINITIONS[name]
                for permission in service.requested_permissions(
                    self._hass,
                    build_service_data(self._config, name),
                    self.ha_token_backend,
                ):
                    if permission not in requested:
                        requested.append(permission)
            self._requested_permissions = requested

        return self._requested_permissions
