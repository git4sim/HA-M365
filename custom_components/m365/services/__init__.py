"""Registry of the Microsoft 365 services bundled in the integration.

Every service lives in its own package (``services/<name>``) whose module
layout mirrors the ``integration`` package of the upstream MS365-* repository
it was taken from:

    config_flow_integration  reconfigure/validate schema, options flow, subentries
    const_integration        constants (DOMAIN is the unified "m365")
    diagnostics_integration  service diagnostics
    permissions_integration  Permissions(BasePermissions) for the service
    schema_integration       CONFIG_SCHEMA_INTEGRATION and service schemas
    setup_integration        async_do_setup(hass, entry, account)
"""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType

from homeassistant.const import Platform

from ..const import (
    CONF_SHARED_MAILBOX,
    SERVICE_CALENDAR,
    SERVICE_CONTACTS,
    SERVICE_MAIL,
    SERVICE_TEAMS,
    SERVICE_TODO,
)
from .calendar import (
    config_flow_integration as calendar_config_flow,
    diagnostics_integration as calendar_diagnostics,
    permissions_integration as calendar_permissions,
    schema_integration as calendar_schema,
    setup_integration as calendar_setup,
)
from .contacts import (
    config_flow_integration as contacts_config_flow,
    diagnostics_integration as contacts_diagnostics,
    permissions_integration as contacts_permissions,
    schema_integration as contacts_schema,
    setup_integration as contacts_setup,
)
from .mail import (
    config_flow_integration as mail_config_flow,
    diagnostics_integration as mail_diagnostics,
    permissions_integration as mail_permissions,
    schema_integration as mail_schema,
    setup_integration as mail_setup,
)
from .teams import (
    config_flow_integration as teams_config_flow,
    diagnostics_integration as teams_diagnostics,
    permissions_integration as teams_permissions,
    schema_integration as teams_schema,
    setup_integration as teams_setup,
)
from .todo import (
    config_flow_integration as todo_config_flow,
    diagnostics_integration as todo_diagnostics,
    permissions_integration as todo_permissions,
    schema_integration as todo_schema,
    setup_integration as todo_setup,
)

# Settings that belong to the account rather than to a single service.
ACCOUNT_LEVEL_KEYS = {CONF_SHARED_MAILBOX}


@dataclass(frozen=True)
class ServiceDefinition:
    """Description of one bundled service."""

    name: str
    platforms: tuple[Platform, ...]
    setup: ModuleType
    config_flow: ModuleType
    schema: ModuleType
    permissions: ModuleType
    diagnostics: ModuleType
    has_options: bool = False
    supports_shared_mailbox: bool = False

    def config_schema(self) -> dict:
        """Return the service specific schema for initial setup."""
        return {
            key: value
            for key, value in self.schema.CONFIG_SCHEMA_INTEGRATION.items()
            if str(key) not in ACCOUNT_LEVEL_KEYS
        }

    def reconfigure_schema(self, service_data) -> dict:
        """Return the service specific schema for reconfiguration."""
        return {
            key: value
            for key, value in self.config_flow.integration_reconfigure_schema(
                service_data
            ).items()
            if str(key) not in ACCOUNT_LEVEL_KEYS
        }

    def validate(self, service_data) -> dict:
        """Validate the service specific settings."""
        return self.config_flow.integration_validate_schema(service_data)

    def requested_permissions(self, hass, service_data, token_backend) -> list[str]:
        """Return the Graph permissions this service needs."""
        return self.permissions.Permissions(
            hass, service_data, token_backend
        ).requested_permissions


SERVICE_DEFINITIONS: dict[str, ServiceDefinition] = {
    SERVICE_CALENDAR: ServiceDefinition(
        name=SERVICE_CALENDAR,
        platforms=(Platform.CALENDAR,),
        setup=calendar_setup,
        config_flow=calendar_config_flow,
        schema=calendar_schema,
        permissions=calendar_permissions,
        diagnostics=calendar_diagnostics,
        has_options=True,
        supports_shared_mailbox=True,
    ),
    SERVICE_TODO: ServiceDefinition(
        name=SERVICE_TODO,
        platforms=(Platform.TODO,),
        setup=todo_setup,
        config_flow=todo_config_flow,
        schema=todo_schema,
        permissions=todo_permissions,
        diagnostics=todo_diagnostics,
        has_options=True,
    ),
    SERVICE_MAIL: ServiceDefinition(
        name=SERVICE_MAIL,
        platforms=(Platform.SENSOR,),
        setup=mail_setup,
        config_flow=mail_config_flow,
        schema=mail_schema,
        permissions=mail_permissions,
        diagnostics=mail_diagnostics,
        supports_shared_mailbox=True,
    ),
    SERVICE_TEAMS: ServiceDefinition(
        name=SERVICE_TEAMS,
        platforms=(Platform.SENSOR,),
        setup=teams_setup,
        config_flow=teams_config_flow,
        schema=teams_schema,
        permissions=teams_permissions,
        diagnostics=teams_diagnostics,
        has_options=True,
    ),
    SERVICE_CONTACTS: ServiceDefinition(
        name=SERVICE_CONTACTS,
        platforms=(),
        setup=contacts_setup,
        config_flow=contacts_config_flow,
        schema=contacts_schema,
        permissions=contacts_permissions,
        diagnostics=contacts_diagnostics,
        supports_shared_mailbox=True,
    ),
}

ALL_PLATFORMS: list[Platform] = sorted(
    {platform for svc in SERVICE_DEFINITIONS.values() for platform in svc.platforms}
)


def platforms_for(services) -> list[Platform]:
    """Return the platforms needed by the given services."""
    return sorted(
        {
            platform
            for name in services
            if name in SERVICE_DEFINITIONS
            for platform in SERVICE_DEFINITIONS[name].platforms
        }
    )
