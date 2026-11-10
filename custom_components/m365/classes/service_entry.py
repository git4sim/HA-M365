"""Per-service view of the shared M365 config entry.

The service packages (calendar, todo, mail, teams, contacts) originate from the
individual MS365-* integrations, each of which owned a whole config entry. In
the unified integration one config entry represents one Microsoft 365 account
and holds the settings of every enabled service:

    entry.data    = {<account settings>, "services": {"calendar": {...}, ...}}
    entry.options = {"calendar": {...}, "todo": {...}, "teams": {...}}

``MS365ServiceEntry`` presents a config entry to a service in the shape the
service was written for (flat ``data``, its own ``options`` and
``runtime_data``), so the service code can stay close to upstream and future
upstream fixes remain easy to port. Everything else is forwarded to the real
config entry, which is available as ``config_entry``.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry

from ..const import CONF_SERVICES
from .config_entry import MS365Data, MS365ServiceRuntimeData


def build_service_data(data: dict, service: str) -> dict:
    """Return flat service data: account settings plus the service settings."""
    flat = {key: value for key, value in data.items() if key != CONF_SERVICES}
    flat |= data.get(CONF_SERVICES, {}).get(service) or {}
    return flat


def enabled_services(data) -> list[str]:
    """Return the services enabled in config entry data."""
    return list((data.get(CONF_SERVICES) or {}).keys())


class MS365ServiceEntry:
    """Config entry as seen by a single service."""

    def __init__(self, entry: ConfigEntry, service: str) -> None:
        """Initialise the view."""
        object.__setattr__(self, "_entry", entry)
        object.__setattr__(self, "_service", service)

    @property
    def config_entry(self) -> ConfigEntry:
        """Return the real config entry."""
        return self._entry

    @property
    def service(self) -> str:
        """Return the service name."""
        return self._service

    @property
    def data(self) -> MappingProxyType[str, Any]:
        """Return account settings merged with this service's settings."""
        return MappingProxyType(build_service_data(self._entry.data, self._service))

    @property
    def options(self) -> MappingProxyType[str, Any]:
        """Return this service's options."""
        return MappingProxyType(dict(self._entry.options.get(self._service) or {}))

    @property
    def runtime_data(self) -> MS365ServiceRuntimeData | None:
        """Return the runtime data in the per-service shape."""
        runtime: MS365Data | None = getattr(self._entry, "runtime_data", None)
        if not isinstance(runtime, MS365Data):
            return None
        service_data = runtime.services.get(self._service)
        return MS365ServiceRuntimeData(
            permissions=runtime.permissions,
            ha_account=runtime.ha_account,
            personal_account=runtime.personal_account,
            coordinator=service_data.coordinator if service_data else None,
            sensors=service_data.sensors if service_data else None,
            options=self.options,
        )

    def __getattr__(self, name: str) -> Any:
        """Forward everything else to the real config entry."""
        return getattr(self._entry, name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Prevent services from silently writing to the view."""
        raise AttributeError(
            f"MS365ServiceEntry is read-only, cannot set '{name}'; "
            "use hass.config_entries.async_update_entry on config_entry"
        )

    def __repr__(self) -> str:
        """Return a representation for logs."""
        return f"<MS365ServiceEntry {self._service} of {self._entry!r}>"
