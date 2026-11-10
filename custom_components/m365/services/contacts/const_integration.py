"""Contact constants."""

import probatio

from homeassistant.const import Platform
import homeassistant.helpers.config_validation as cv

PLATFORMS: list[Platform] = []
DOMAIN = "m365"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_EMAIL = "email"
CONTACTS_DATA = "contacts"
ATTR_GIVEN_NAME = "given_name"
ATTR_SURNAME = "surname"

PERM_CONTACTS_READ = "Contacts.Read"

CONTACTS_SEARCH_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_GIVEN_NAME): cv.string,
        probatio.Optional(ATTR_SURNAME): cv.string,
        probatio.Optional(ATTR_EMAIL): cv.string,
    }
)
