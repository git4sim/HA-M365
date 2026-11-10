"""Mock config entry."""

from copy import deepcopy

from custom_components.m365.classes.service_entry import MS365ServiceEntry
from pytest_homeassistant.common import MockConfigEntry

from ..integration import MS365ConfigEntry


SERVICE = "todo"
ACCOUNT_KEYS = {
    "entity_name",
    "client_id",
    "environment_secret",
    "client_secret",
    "client_sec_variable",
    "alt_auth_method",
    "api_options",
    "shared_mailbox",
}


def to_unified_data(data, service=SERVICE):
    """Convert flat single-service entry data to the unified M365 layout."""
    if data is None or "services" in data:
        return data
    unified = {key: value for key, value in data.items() if key in ACCOUNT_KEYS}
    unified["services"] = {
        service: {key: value for key, value in data.items() if key not in ACCOUNT_KEYS}
    }
    return unified


def to_unified_options(options, service=SERVICE):
    """Convert flat single-service options to the unified M365 layout."""
    if not options:
        return options
    if service in options and len(options) == 1:
        return options
    return {service: dict(options)}


class MS365MockConfigEntry(MockConfigEntry):
    """Mock config entry with MS365 runtime_data."""

    def __init__(self, *args, **kwargs) -> None:
        """Initialise MS365MockConfigEntry."""
        self.runtime_data: MS365ConfigEntry = None
        kwargs["data"] = to_unified_data(kwargs.get("data"))
        kwargs["options"] = to_unified_options(kwargs.get("options"))
        super().__init__(*args, **kwargs)


def config_entry_setup(input_config_entry, base_attributes=None, api_option_attributes=None, delete_attributes=None):
    """Create config entry."""
    config_entry = deepcopy(input_config_entry)
    if base_attributes:
        for key, value in base_attributes.items():
            config_entry[key] = value
    if api_option_attributes:
        for key, value in api_option_attributes.items():
            config_entry["api_options"][key] = value
    if delete_attributes:
        for key in delete_attributes:
            del config_entry[key]
    return config_entry


def service_view(entry):
    """Return the per-service view of a unified config entry."""
    return MS365ServiceEntry(entry, SERVICE)
