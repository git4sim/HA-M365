"""M365 Config Entry Structure."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry

MS365ConfigEntry = ConfigEntry["MS365Data"]


@dataclass
class MS365ServiceData:
    """Runtime data of one bundled service (calendar, todo, ...)."""

    coordinator: Any = None
    sensors: Any = None
    platforms: list = field(default_factory=list)


@dataclass
class MS365Data:
    """Runtime data shared by all services of one Microsoft 365 account."""

    permissions: Any
    ha_account: Any
    personal_account: Any
    services: dict[str, MS365ServiceData]
    options: MappingProxyType[str, Any]


@dataclass
class MS365ServiceRuntimeData:
    """Per-service runtime view in the shape the service modules expect."""

    permissions: Any
    ha_account: Any
    personal_account: Any
    coordinator: Any
    sensors: Any
    options: MappingProxyType[str, Any]
